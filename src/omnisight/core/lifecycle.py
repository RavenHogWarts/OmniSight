"""启动与退出编排（02 文档 §5）。

相对 02 文档 §5.1 的步骤表有两处**顺序调整**，理由写在这里以免被当成疏漏：

1. **路径与日志提前到最前面。** 文档把单实例锁排在第 2 步、路径第 3 步，但基于
   锁文件的 ``InstanceLock`` 需要先有目录，且"配置解析失败"这类错误必须能被记录
   下来。路径解析是纯函数、无副作用，提前没有代价。
2. **``detect()`` 在加锁之前。** 探测无副作用，而第二实例被挡住时也需要知道
   自己在什么环境上——这条信息要进日志。

``shutdown()`` 必须幂等：注销与强杀可能让它被并发调用两次（02 文档 §5.2）。
"""

from __future__ import annotations

import logging
import signal
import threading
import webbrowser
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .. import adapters
from ..adapters.ports import AdapterOptions, AdapterSet, Capabilities, CaptureUnavailable
from ..capture.coordinator import CaptureCoordinator
from ..capture.foreground import ForegroundMonitor
from ..capture.keyboard import KeyboardCapture
from ..capture.queue import EventQueue
from ..presentation import security
from ..presentation.stream import StreamHub
from ..presentation.web import AppContext, WebServer, create_app
from ..services import Services
from ..services import categories as category_rules
from ..storage import capability as capability_table
from ..storage.database import Database, SchemaTooNewError
from ..storage.migrations import migrate
from ..storage.repositories.apps import AppDirectory, AppRegistry
from ..storage.repositories.keys import KeyRepository
from ..storage.repositories.usage import UsageRepository
from ..storage.writer import StorageWriter
from . import logging as log_setup
from . import paths
from .bus import EventBus
from .clock import SystemClock, resolve_timezone, timezone_label
from .config import Config, ConfigError
from .config import load as load_config

logger = logging.getLogger(__name__)

EXIT_OK = 0
EXIT_STARTUP_FAILED = 1
EXIT_ALREADY_RUNNING = 2


class StartupAborted(Exception):
    """启动无法继续。``exit_code`` 决定进程退出码，``notify`` 决定是否弹框告知。"""

    def __init__(self, title: str, message: str, exit_code: int, *, notify: bool = True) -> None:
        super().__init__(f"{title}: {message}")
        self.title = title
        self.message = message
        self.exit_code = exit_code
        self.notify = notify


@dataclass(slots=True)
class CaptureBundle:
    """一次运行的采集管道。

    装配放在 lifecycle 而不是 ``capture/`` 里，是因为它要同时认识 ``storage``（写线程、
    仓储）与 ``adapters``（端口实现），而 ``capture/`` 在分层上位于 ``storage/`` 之下——
    让它反向导入 ``storage.writer`` 会把依赖方向搞反（02 文档 §1）。
    """

    bus: EventBus
    queue: EventQueue
    coordinator: CaptureCoordinator
    writer: StorageWriter
    registry: AppRegistry
    keys: KeyRepository
    usage: UsageRepository
    keyboard: KeyboardCapture | None = None
    foreground: ForegroundMonitor | None = None
    keyboard_source: object | None = None

    def snapshot(self) -> dict[str, object]:
        """``/api/v1/status`` 的 ``capture`` 段（05 文档 §7）。"""
        foreground = (
            self.foreground.snapshot()
            if self.foreground is not None
            else {"running": False, "backend": "none"}
        )
        keyboard = (
            self.keyboard.snapshot()
            if self.keyboard is not None
            else {"running": False, "backend": "none"}
        )
        writer = self.writer.snapshot()
        return {
            "foreground": foreground,
            "keyboard": keyboard,
            "writer": writer,
            "paused": bool(self.keyboard.paused) if self.keyboard else False,
            "queue_depth": writer["queue_depth"],
            "dropped_events": writer["dropped_events"],
        }


@dataclass(slots=True)
class Runtime:
    """一次运行的全部活动对象。"""

    app_root: Path
    data_dir: Path
    config: Config
    capabilities: Capabilities
    adapter_set: AdapterSet
    database: Database
    token: str
    started_at: str
    schema_version: int
    capture: CaptureBundle | None = None
    services: Services | None = None
    context: AppContext | None = None
    stream: StreamHub | None = None
    web: WebServer | None = None
    tray: object | None = None


class Lifecycle:
    """编排启动与退出。一个实例只跑一次。"""

    def __init__(self, *, autostart_invocation: bool = False) -> None:
        self.autostart_invocation = autostart_invocation
        self.runtime: Runtime | None = None
        self.clock = SystemClock()
        self._shutdown_lock = threading.Lock()
        self._shutdown_done = False

    # ── 启动 ────────────────────────────────────────────────────────────
    def start(self) -> int:
        app_root = paths.app_root()
        log_setup.configure(paths.ensure_dir(paths.logs_dir(app_root)))
        logger.info("OmniSight 启动，数据根目录 %s", app_root)
        for key, value in paths.describe().items():
            logger.info("  path.%s = %s", key, value)

        environment = adapters.detect()
        logger.info(
            "探测到平台 %s（支持级别 %s，%s）",
            environment.platform_id,
            environment.tier,
            environment.os_version or "版本未知",
        )
        logger.info("  环境能力 = %s", environment.to_dict())

        notifier = _bootstrap_notifier(app_root)
        try:
            return self._start_inner(app_root, environment)
        except StartupAborted as exc:
            logger.error("启动中止：%s", exc)
            if exc.notify:
                notifier.error(exc.title, exc.message)
            self.shutdown()
            return exc.exit_code

    def _start_inner(self, app_root: Path, environment: Capabilities) -> int:
        config = self._load_config(app_root)

        # 平台的会话结束信号（Windows 的 WM_ENDSESSION）必须能走到 shutdown()，否则
        # 注销/关机时当前会话与队列里的事件一起丢掉。
        options = AdapterOptions(
            keyboard_backend=config.capture.keyboard_backend,
            record_window_titles=config.privacy.record_window_titles,
            on_session_end=self.shutdown,
        )
        adapter_set = adapters.build(environment, app_root=app_root, options=options)
        logger.info("已实现能力 = %s", adapter_set.capabilities.to_dict())

        data_dir = paths.ensure_dir(paths.data_dir(app_root, config.storage.data_dir))

        if not adapter_set.instance_lock.acquire():
            self._handle_second_instance(adapter_set, config, data_dir)
            return EXIT_ALREADY_RUNNING

        database, schema_version = self._open_database(data_dir, config)

        # 采集在数据库就绪且单实例锁到手之后才启动——注册 Raw Input 是抢占系统资源，
        # 绝不能发生在"我可能是第二个实例"的阶段（02 文档 §5.1）。
        capture = self._start_capture(config, adapter_set, database)
        capabilities = adapters.reconcile(
            adapter_set.capabilities,
            keyboard=capture.keyboard_source,
            foreground_running=capture.foreground is not None and capture.foreground.running,
            idle_available=adapter_set.idle is not None,
            titles_recorded=config.privacy.record_window_titles,
        )
        logger.info("有效能力 = %s", capabilities.to_dict())
        for notice in capabilities.degraded:
            logger.warning("能力降级 [%s] %s —— %s", notice.code, notice.title, notice.detail)

        runtime = Runtime(
            app_root=app_root,
            data_dir=data_dir,
            config=config,
            capabilities=capabilities,
            adapter_set=adapter_set,
            database=database,
            token=security.new_token(),
            started_at=self.clock.now().isoformat(timespec="seconds"),
            schema_version=schema_version,
            capture=capture,
        )
        self.runtime = runtime

        # 能力快照要记的是**启动之后**的事实，因此排在 reconcile 之后。
        self._record_capability(database, capabilities, config)
        capture.writer.set_capability_provider(lambda: _capability_row(capabilities, config))

        self._build_services(runtime)
        self._start_web(runtime)
        self._install_signal_handlers()
        adapter_set.notifier.clear()
        self._run_tray(runtime)
        return EXIT_OK

    def _start_capture(
        self, config: Config, adapter_set: AdapterSet, database: Database
    ) -> CaptureBundle:
        """装配并启动采集管道。**任何一环失败都不允许让程序起不来**（10 文档 §6）。

        键盘采集失败时屏幕时间统计必须照常工作，反之亦然。这是对现状的改进：
        KeyTrace 的 ``RawInputKeyboardListener.start()`` 失败时直接 ``raise``，
        整个程序就起不来了。
        """
        tz = resolve_timezone(config.ui.timezone)
        # 生命周期与写入线程必须用**同一个**时区算日期桶：两者都 upsert
        # capture_capability 的同一行，用不同时区会在跨零点前后各写一行、或更新错那一天。
        # 配置里没写 ui.timezone 时 resolve_timezone 返回系统时区，行为与之前一致。
        self.clock = SystemClock(tz)
        bus = EventBus()
        queue = EventQueue()
        coordinator = CaptureCoordinator(
            boundary_window_seconds=config.capture.foreground_poll_seconds
        )
        registry = AppRegistry(database, adapter_set.capabilities.platform_id)
        writer = StorageWriter(
            database,
            queue,
            tz=tz,
            store_raw=config.capture.store_raw_key_events,
            registry=registry,
            clock=self.clock,
            checkpoint_interval_seconds=config.storage.checkpoint_interval_seconds,
            bus=bus,
        )
        writer.start()

        bundle = CaptureBundle(
            bus=bus,
            queue=queue,
            coordinator=coordinator,
            writer=writer,
            registry=registry,
            keys=KeyRepository(database),
            usage=UsageRepository(database),
        )

        if adapter_set.foreground is not None:
            monitor = ForegroundMonitor(
                adapter_set.foreground,
                coordinator,
                queue,
                registry.resolve,
                idle_source=adapter_set.idle,
                poll_seconds=config.capture.foreground_poll_seconds,
                idle_threshold_seconds=config.capture.idle_threshold_seconds,
                session_flush_seconds=config.capture.session_flush_seconds,
                excluded=frozenset(config.privacy.excluded_processes),
                clock=self.clock,
                paused=config.capture.paused,
                bus=bus,
            )
            monitor.start()
            bundle.foreground = monitor
            logger.info("前台监控已启动（轮询 %ss）", config.capture.foreground_poll_seconds)

        if adapter_set.keyboard is not None:
            capture = KeyboardCapture(
                adapter_set.keyboard,
                coordinator,
                queue,
                bus=bus,
                realtime_stream=config.privacy.realtime_stream,
                paused=config.capture.paused,
            )
            try:
                capture.start()
            except CaptureUnavailable as exc:
                # 明确记下来，reconcile() 会把它变成用户看得见的降级说明。
                logger.error("键盘采集不可用：%s", exc)
            else:
                bundle.keyboard = capture
                bundle.keyboard_source = adapter_set.keyboard
                logger.info("键盘采集已启动，后端 %s", capture.backend_name)
        if config.capture.paused:
            logger.warning("配置里 capture.paused = true，本次运行不会记录任何数据")
        return bundle

    # ── 启动的各步骤 ────────────────────────────────────────────────────
    def _load_config(self, app_root: Path) -> Config:
        path = paths.config_path(app_root)
        try:
            config, warnings = load_config(path)
        except ConfigError as exc:
            field_hint = f"（字段 {exc.field_path}）" if exc.field_path else ""
            raise StartupAborted(
                "配置文件有误",
                f"{exc}{field_hint}\n\n文件位置：{path}\n"
                "已保留你的文件不做修改，请修正后重新启动。",
                EXIT_STARTUP_FAILED,
            ) from exc
        for warning in warnings:
            logger.warning("配置：%s", warning)
        return config

    def _open_database(self, data_dir: Path, config: Config) -> tuple[Database, int]:
        database = Database(paths.database_path(data_dir))
        if database.path.exists() and not database.quick_check():
            quarantined = _quarantine_corrupt_database(database.path)
            raise StartupAborted(
                "数据库损坏",
                f"已把损坏的文件改名为 {quarantined.name}，下次启动会新建空库。\n"
                f"历史备份见 {data_dir / 'backup'}。",
                EXIT_STARTUP_FAILED,
            )
        try:
            version = migrate(database)
        except SchemaTooNewError as exc:
            raise StartupAborted("需要升级程序", str(exc), EXIT_STARTUP_FAILED) from exc
        except Exception as exc:
            raise StartupAborted(
                "数据库初始化失败",
                f"{exc}\n\n数据库位置：{database.path}",
                EXIT_STARTUP_FAILED,
            ) from exc
        logger.info("数据库就绪 %s（schema v%s）", database.path, version)
        self._record_timezone(database, config)
        return database, version

    def _record_timezone(self, database: Database, config: Config) -> None:
        """首次建库时记下日期桶所用的时区（03 文档 §3.2）。"""
        if database.meta_get("timezone"):
            return
        database.meta_set("timezone", timezone_label(resolve_timezone(config.ui.timezone)))

    def _record_capability(
        self, database: Database, capabilities: Capabilities, config: Config
    ) -> None:
        """记下"这天的数据是在什么条件下采到的"（03 文档 §2.8）。

        与写入线程每批刷新的是**同一行**，取值也来自同一个函数——两处各算一遍必然漂移，
        而这张表的全部价值就在于它能解释历史数据，写错了比不写更糟。
        """
        now = self.clock.now()
        with database.transaction() as conn:
            capability_table.upsert(
                conn,
                day_bucket=capability_table.day_bucket(now),
                now=now,
                **_capability_row(capabilities, config),
            )

    def _handle_second_instance(
        self, adapter_set: AdapterSet, config: Config, data_dir: Path
    ) -> None:
        """已有实例在跑。**不静默退出**——用户点了图标却什么都没发生会以为程序坏了。"""
        logger.info("检测到已运行的实例，尝试唤起它")
        if adapter_set.instance_lock.notify_existing():
            return
        runtime_info = security.read_runtime_file(data_dir) or {}
        port = runtime_info.get("port") or config.server.port
        token = runtime_info.get("token")
        url = f"http://127.0.0.1:{port}/"
        if isinstance(token, str) and token:
            url = f"{url}?token={token}"
        webbrowser.open(url)

    def _build_services(self, runtime: Runtime) -> None:
        """装配服务层与表现层上下文（02 文档 §1 的分层）。

        ``on_config_change`` 让设置接口改完配置后，表现层与运行时看到的是同一份新配置——
        少了这个回调，用户改完设置刷新页面还会看到旧值，而设置接口已经回报"已生效"。
        """
        context = AppContext(
            config=runtime.config,
            database=runtime.database,
            capabilities=runtime.capabilities,
            token=runtime.token,
            started_at=runtime.started_at,
            data_dir=runtime.data_dir,
            schema_version=runtime.schema_version,
            paused=runtime.config.capture.paused,
            capture=runtime.capture,
        )

        def on_config_change(new_config: Config) -> None:
            runtime.config = new_config
            context.config = new_config
            context.paused = new_config.capture.paused

        services = Services.build(
            database=runtime.database,
            config=runtime.config,
            capabilities=runtime.capabilities,
            config_path=paths.config_path(runtime.app_root),
            clock=self.clock,
            capture=runtime.capture,
            adapters=runtime.adapter_set,
            on_config_change=on_config_change,
        )
        context.services = services
        bus = runtime.capture.bus if runtime.capture is not None else None
        runtime.stream = StreamHub(bus, context) if bus is not None else None
        context.stream = runtime.stream
        runtime.services = services
        runtime.context = context
        self._refresh_categories(runtime)

    def _refresh_categories(self, runtime: Runtime) -> None:
        """给还没被用户改过的应用补自动分类。

        分类规则会随版本更新，而已入库的行不会自己变。只改
        ``category_source = 'auto'`` 的行——用户的选择优先于规则。
        """
        try:
            changed = AppDirectory(runtime.database).apply_auto_categories(
                category_rules.categorize
            )
        except Exception:  # pragma: no cover - 分类刷新失败不影响启动
            logger.debug("刷新自动分类失败", exc_info=True)
            return
        if changed:
            logger.info("按最新规则更新了 %s 个应用的自动分类", changed)

    def _start_web(self, runtime: Runtime) -> None:
        context = runtime.context
        if context is None:  # pragma: no cover - _build_services 必在此之前调用
            raise StartupAborted("内部错误", "服务层未装配", EXIT_STARTUP_FAILED)
        app = create_app(context)
        try:
            server = WebServer(app, runtime.config.server.host, runtime.config.server.port)
        except OSError as exc:
            raise StartupAborted(
                "端口被占用",
                f"{runtime.config.server.host}:{runtime.config.server.port} 无法绑定（{exc}）。\n\n"
                "可能是 OmniSight 的另一个实例、或旧版 TimeLens / KeyTrace 仍在运行。\n"
                f"如需换端口，请修改 {paths.config_path(runtime.app_root)} 里的 server.port。",
                EXIT_STARTUP_FAILED,
            ) from exc
        server.start()
        runtime.web = server
        security.write_runtime_file(runtime.data_dir, port=server.port, token=runtime.token)
        logger.info("仪表盘地址 %s", runtime.config.dashboard_url(runtime.token))

    def _run_tray(self, runtime: Runtime) -> None:
        from ..tray import TrayIcon

        autostart = runtime.adapter_set.autostart
        asset = _icon_asset()
        tray = TrayIcon(
            dashboard_url=lambda: runtime.config.dashboard_url(runtime.token),
            on_quit=self.shutdown,
            autostart_state=(autostart.is_enabled if autostart else None),
            on_toggle_autostart=(autostart.set_enabled if autostart else None),
            open_data_dir=lambda: webbrowser.open(runtime.data_dir.as_uri()),
            asset=asset,
            available=runtime.capabilities.tray,
        )
        runtime.tray = tray
        if not runtime.capabilities.tray:
            # 没有托盘时这是用户唯一能看到访问地址的地方（10 文档 §5.1）。
            print(f"OmniSight 正在运行：{runtime.config.dashboard_url(runtime.token)}")
        tray.run()

    def _install_signal_handlers(self) -> None:
        """把平台各异的关闭信号统一收敛到 :meth:`shutdown`（02 文档 §5.2）。"""
        for name in ("SIGINT", "SIGTERM", "SIGBREAK"):
            sig = getattr(signal, name, None)
            if sig is None:
                continue
            try:
                signal.signal(sig, lambda *_args: self.shutdown())
            except (ValueError, OSError):  # pragma: no cover - 非主线程或不支持
                logger.debug("无法注册信号 %s", name)

    # ── 退出 ────────────────────────────────────────────────────────────
    def shutdown(self) -> None:
        """幂等停机。每一步失败都不允许打断后续清理。"""
        with self._shutdown_lock:
            if self._shutdown_done:
                return
            self._shutdown_done = True

        logger.info("开始停机")
        runtime = self.runtime
        if runtime is None:
            return

        # 顺序是有讲究的：先停采集（不再有新事件），再结束当前前台会话（它本身会产生
        # 最后一条事件），最后才让写线程 drain。反过来做会丢掉最后一段会话。
        capture = runtime.capture
        if capture is not None:
            if capture.keyboard is not None:
                _guard("停止键盘采集", capture.keyboard.stop)
            if capture.foreground is not None:
                _guard("停止前台监控", capture.foreground.stop)
            _guard("落盘剩余事件", lambda: capture.writer.stop(timeout=5.0))
        if runtime.stream is not None:
            _guard("停止实时推送", runtime.stream.stop)
        if runtime.web is not None:
            _guard("停止 Web 服务", runtime.web.stop)
        _guard("移除 runtime.json", lambda: security.remove_runtime_file(runtime.data_dir))
        _guard("WAL checkpoint", lambda: runtime.database.checkpoint("TRUNCATE"))
        _guard("关闭数据库", runtime.database.close)
        _guard("释放单实例锁", runtime.adapter_set.instance_lock.release)
        if runtime.tray is not None:
            _guard("停止托盘", runtime.tray.stop)
        logger.info("已停机")


def _guard(what: str, action) -> None:
    try:
        action()
    except Exception:
        logger.exception("停机步骤失败：%s", what)


def _capability_row(capabilities: Capabilities, config: Config) -> dict[str, object]:
    """``capture_capability`` 的一行（不含日期与时刻）。

    ``titles_recorded`` 取"能力允许 ∧ 用户开启"的合取：只有配置打开而平台拿不到标题时
    这一天并没有标题，反过来也一样。
    """
    return {
        "platform_id": capabilities.platform_id,
        "keyboard_backend": capabilities.keyboard_backend,
        "foreground_available": capabilities.foreground,
        "titles_recorded": capabilities.window_titles and config.privacy.record_window_titles,
        "key_position_stable": capabilities.key_position_stable,
    }


def _bootstrap_notifier(app_root: Path):
    """启动最早期就要能报错，此时适配器还没装配好。"""
    from ..adapters.generic.notifier import FileNotifier

    return FileNotifier(app_root)


def _icon_asset() -> Path | None:
    """图标既可能在仓库 ``assets/``（开发），也可能在打包后的资源目录。"""
    candidates = (
        paths.exe_dir() / "assets" / "omnisight.png",
        paths.resource_dir() / "presentation" / "static" / "assets" / "omnisight.png",
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _quarantine_corrupt_database(path: Path) -> Path:
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    target = path.with_name(f"{path.name}.corrupt-{stamp}")
    path.rename(target)
    logger.error("数据库损坏，已隔离为 %s", target)
    return target
