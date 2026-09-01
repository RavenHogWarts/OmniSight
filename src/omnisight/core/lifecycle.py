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
from ..adapters.ports import AdapterSet, Capabilities
from ..presentation import security
from ..presentation.web import AppContext, WebServer, create_app
from ..storage import capability as capability_table
from ..storage.database import Database, SchemaTooNewError
from ..storage.migrations import migrate
from . import logging as log_setup
from . import paths
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

        adapter_set = adapters.build(environment, app_root=app_root)
        capabilities = adapter_set.capabilities
        logger.info("有效能力 = %s", capabilities.to_dict())
        for notice in capabilities.degraded:
            logger.warning("能力降级 [%s] %s —— %s", notice.code, notice.title, notice.detail)

        data_dir = paths.ensure_dir(paths.data_dir(app_root, config.storage.data_dir))

        if not adapter_set.instance_lock.acquire():
            self._handle_second_instance(adapter_set, config, data_dir)
            return EXIT_ALREADY_RUNNING

        database, schema_version = self._open_database(data_dir, config)
        self._record_capability(database, capabilities, config)

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
        )
        self.runtime = runtime

        # M1 起在这里启动写线程与采集线程；M0 只有 Web 与托盘。
        self._start_web(runtime)
        self._install_signal_handlers()
        adapter_set.notifier.clear()
        self._run_tray(runtime)
        return EXIT_OK

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
        now = self.clock.now()
        with database.transaction() as conn:
            capability_table.upsert(
                conn,
                day_bucket=capability_table.day_bucket(now),
                platform_id=capabilities.platform_id,
                keyboard_backend=capabilities.keyboard_backend,
                foreground_available=capabilities.foreground,
                titles_recorded=capabilities.window_titles and config.privacy.record_window_titles,
                key_position_stable=capabilities.key_position_stable,
                now=now,
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

    def _start_web(self, runtime: Runtime) -> None:
        context = AppContext(
            config=runtime.config,
            database=runtime.database,
            capabilities=runtime.capabilities,
            token=runtime.token,
            started_at=runtime.started_at,
            data_dir=runtime.data_dir,
            schema_version=runtime.schema_version,
            paused=runtime.config.capture.paused,
        )
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

        # M1 起在这里停采集、结束当前会话、drain 写队列。
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
