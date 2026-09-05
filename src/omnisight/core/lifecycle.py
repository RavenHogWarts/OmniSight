"""启动与退出编排（02 文档 §5）。

相对 02 文档 §5.1 的步骤表有两处**顺序调整**，理由写在这里以免被当成疏漏：

1. **路径与日志提前到最前面。** 文档把单实例锁排在第 2 步、路径第 3 步，但基于
   锁文件的 ``InstanceLock`` 需要先有目录，且"配置解析失败"这类错误必须能被记录
   下来。路径解析是纯函数、无副作用，提前没有代价。
2. **``detect()`` 在加锁之前。** 探测无副作用，而第二实例被挡住时也需要知道
   自己在什么环境上——这条信息要进日志。

``shutdown()`` 必须幂等：注销与强杀可能让它被并发调用两次（02 文档 §5.2）。

``--takeover``（托盘「以管理员身份重启」拉起的新实例会带上它）在加锁那一步多等一会儿：
提权后的进程与正在停机的旧进程必然有一段重叠，而"第二个实例"与"接班的实例"在锁面前
长得一模一样。等待的上限有限，超时就当作普通的第二实例处理——绝不允许两个记录器同时
往一个库里写（10 文档 §5.2）。
"""

from __future__ import annotations

import logging
import signal
import threading
import time
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .. import __version__, adapters
from ..adapters.ports import (
    AdapterOptions,
    AdapterSet,
    Capabilities,
    CaptureUnavailable,
    ElevationControl,
)
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
from . import paths, relaunch
from .bus import EventBus
from .clock import SystemClock, resolve_timezone, timezone_label
from .config import Config, ConfigError
from .config import load as load_config
from .crash import install as install_crash_handler

logger = logging.getLogger(__name__)

EXIT_OK = 0
EXIT_STARTUP_FAILED = 1
EXIT_ALREADY_RUNNING = 2

#: ``--takeover`` 时等旧实例交出单实例锁的上限。旧实例停机要落盘剩余事件（写线程
#: ``stop(timeout=5.0)``）再做一次 WAL checkpoint，几秒是正常的，15 秒是"它其实没在退"。
TAKEOVER_WAIT_SECONDS = 15.0
TAKEOVER_POLL_SECONDS = 0.25

#: 重启时"看接班实例还活着吗"的观察窗口（18 文档 批 5）。命令行拼错、DLL 缺失这类死法在
#: 几百毫秒内就体现为进程退出，而"它已经在等锁了"与"它已经死了"只有这个信号能分开。
RESTART_PROBE_SECONDS = 0.6
#: 停机前留给 HTTP 响应出门的时间。**必须先应答再停机**：浏览器只看到连接被切断时，
#: "正在重启"与"它崩了"是分不开的，而这两件事该给用户看的东西完全不同。
SHUTDOWN_DELAY_SECONDS = 0.4


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


@dataclass(frozen=True, slots=True)
class SystemActions:
    """交给表现层的进程级动作（18 文档 批 5）。

    表现层只拿到这三个可调用对象，拿不到 :class:`Lifecycle` 本身——否则一个 API 处理函数
    就能碰到装配过程里的每一样东西。三个动作的**唯一实现**在下面那个类里，托盘与设置页
    因此是同一条路径的两个入口（与暂停那一项同一个道理，10 文档 §5）。
    """

    #: 起接班实例并安排停机。False = 没起来，本实例照常运行。
    restart: Callable[[], bool]
    #: 停机。响应发出去之后才真的停。
    quit: Callable[[], None]
    #: 打开数据目录（``"data"``）或日志目录（``"logs"``）。
    reveal: Callable[[str], bool]


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

    def __init__(self, *, autostart_invocation: bool = False, takeover: bool = False) -> None:
        self.autostart_invocation = autostart_invocation
        #: 由提权重启拉起：加锁前多等一会儿，让正在停机的旧实例先退干净。
        self.takeover = takeover
        #: 已经拉起了接班实例。停机时**不要**删 runtime.json：那是它继承令牌的唯一
        #: 来源，而它通常还没起来（见 :meth:`_release_runtime_file`）。
        self._successor_pending = False
        self.runtime: Runtime | None = None
        self.clock = SystemClock()
        # 崩溃报告里那行"在什么系统上崩的"的来源。探测完成后填上；在那之前崩溃
        # 报告如实写"平台未探测"，而不是让核心层自己去读 sys.platform（core/ 不许
        # 判断平台——tools/check_platform_leaks.py 会拦）。
        self._environment: Capabilities | None = None
        self._shutdown_lock = threading.Lock()
        self._shutdown_done = False

    def _environment_label(self) -> str:
        """给崩溃报告的一行平台描述。惰性求值，见 :mod:`omnisight.core.crash`。"""
        environment = self._environment
        if environment is None:
            return ""
        return f"{environment.platform_id} {environment.os_version or '版本未知'}"

    # ── 启动 ────────────────────────────────────────────────────────────
    def start(self) -> int:
        app_root = paths.app_root()
        log_setup.configure(paths.ensure_dir(paths.logs_dir(app_root)))
        # 崩溃钩子紧跟日志装配：在这之前抛出的异常还有 Python 默认的 stderr 兜底，
        # 在这之后的（``--noconsole`` 下 stderr 可能是 None）会静默消失（10 文档 §8）。
        install_crash_handler(
            paths.logs_dir(app_root), version=__version__, environment=self._environment_label
        )
        logger.info("OmniSight %s 启动，数据根目录 %s", __version__, app_root)
        for key, value in paths.describe().items():
            logger.info("  path.%s = %s", key, value)

        environment = adapters.detect()
        self._environment = environment
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

        token = self._claim_session(data_dir, adapter_set)
        if token is None:
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
            token=token,
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
    def _claim_session(self, data_dir: Path, adapter_set: AdapterSet) -> str | None:
        """把本次运行的令牌抓在手里，然后拿单实例锁。

        @returns 令牌；``None`` 表示锁没拿到（已经有一个实例在跑）

        **两件事的顺序是这个方法存在的唯一理由。** 接班实例要继承的那份令牌存在
        ``runtime.json`` 里，而"等锁"等到的正是旧实例停机结束的那一刻——读令牌排在等锁之后，
        看到的就是旧实例最后一刻的状态，而不是它交班时的状态。

        症状：重启之后每一个已经打开的页面在下一次请求时 401（"缺少或无效的访问令牌"），
        而"继承令牌"这件事存在的全部理由就是消灭它。这条路上先后踩了两脚，两脚的症状一样：
        第一版把读放在了等锁之后；第二版顺序对了，但旧实例仍然在停机时删掉那个文件，而它
        删得比接班实例的解释器起得来还早——真正的修法在 :meth:`_release_runtime_file`。
        """
        token = self._session_token(data_dir)
        if not self._acquire_instance_lock(adapter_set):
            return None
        return token

    def _session_token(self, data_dir: Path) -> str:
        """本次运行的访问令牌。

        **接班实例继承上一个实例的令牌**（18 文档 批 5）。否则"重新启动"会让每一个已经打开
        的标签页在几秒后集体 401，而它们无从获得新令牌——用户得回托盘重开一遍，那正是重启
        这个功能要省掉的一步。继承的来源是 ``runtime.json``：那个文件本来就存着令牌、本来就
        只有当前用户可读（``security.write_runtime_file`` 收紧过权限），因此这不扩大任何暴露面
        （08 文档 §3.3 已说明同机进程不在对策范围内）。旧实例拉起接班实例后**不会**删掉
        它（:meth:`_release_runtime_file`），因此这里读不到只意味着异常情况：上一次是崩溃
        退出，或者文件被清理工具带走了。

        代价说清楚：**接班路径上令牌不轮换**。冷启动仍然每次新生成一个，因此"关掉再开"能换掉
        令牌；只有重启与提权重启这两条接班路径会沿用。

        **调用时机有硬要求**，见 :meth:`_claim_session`：必须在等单实例锁**之前**读。
        """
        if not self.takeover:
            return security.new_token()
        previous = security.read_runtime_file(data_dir) or {}
        token = previous.get("token")
        if isinstance(token, str) and token:
            logger.info("接班启动：沿用上一个实例的访问令牌，已打开的页面不必重新交接")
            return token
        logger.info("接班启动，但读不到上一个实例的令牌，改用新令牌")
        return security.new_token()

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

    def _acquire_instance_lock(self, adapter_set: AdapterSet) -> bool:
        """拿单实例锁。``--takeover`` 时容许旧实例还没退完，等它一会儿。

        提权重启的两个进程必然有一段重叠：旧实例是在 UAC 得到确认**之后**才开始停机的
        （反过来做的话，用户点「否」就只剩一个已经退出的程序）。于是新实例这里必然会
        先扑空一次。

        等待的是锁而不是"旧进程的 PID"，因为 :meth:`shutdown` 里**释放锁排在停 Web
        之后**：锁一到手，端口也必定已经放开了。这个顺序是这条握手能成立的前提，改
        ``shutdown()`` 的步骤顺序时要一并考虑。

        超时就当普通的第二实例处理（打开已有实例的页面后退出）。宁可"提权没生效"，
        也不能出现两个记录器同时往一个库里写。
        """
        lock = adapter_set.instance_lock
        if lock.acquire():
            return True
        if not self.takeover:
            return False
        logger.info("接管模式：等旧实例交出单实例锁（最多 %ss）", TAKEOVER_WAIT_SECONDS)
        deadline = time.monotonic() + TAKEOVER_WAIT_SECONDS
        while time.monotonic() < deadline:
            time.sleep(TAKEOVER_POLL_SECONDS)
            if lock.acquire():
                logger.info("旧实例已退出，接管成功")
                return True
        logger.warning(
            "旧实例在 %ss 内没有退出，本实例不启动——绝不让两个实例同时写同一个库",
            TAKEOVER_WAIT_SECONDS,
        )
        return False

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
            # 从设置页暂停时托盘图标也要跟着变灰：两个入口改的是同一件事，
            # 状态却分别显示在两处，不同步就等于其中一处在撒谎（08 文档 §5）。
            tray = runtime.tray
            if tray is not None:
                try:
                    tray.set_paused(new_config.capture.paused)
                except Exception:  # pragma: no cover - 托盘已被系统回收
                    logger.debug("同步托盘暂停状态失败", exc_info=True)
            # 设置页与仪表盘现在是**两个标签页**（18 文档 批 1）：改完设置得让另一边知道，
            # 否则"周起始日改了、仪表盘还按旧的切周"这种错既不报错也看不出来。推的是"变了"
            # 而不是新配置本身——与 invalidate 同一个口径，前端自己决定重读哪些偏好。
            stream = runtime.stream
            if stream is not None:
                try:
                    stream.publish_settings()
                except Exception:  # pragma: no cover - 广播失败不该影响写配置
                    logger.debug("广播设置变更失败", exc_info=True)

        services = Services.build(
            database=runtime.database,
            config=runtime.config,
            capabilities=runtime.capabilities,
            config_path=paths.config_path(runtime.app_root),
            clock=self.clock,
            capture=runtime.capture,
            adapters=runtime.adapter_set,
            on_config_change=on_config_change,
            bus=runtime.capture.bus if runtime.capture is not None else None,
            data_dir=runtime.data_dir,
        )
        context.services = services
        # 进程级动作（18 文档 批 5）。表现层拿到的是三个可调用对象，不是 Lifecycle 本身。
        context.system = SystemActions(
            restart=self.restart, quit=self.stop_soon, reveal=self.reveal
        )
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

        elevation = runtime.adapter_set.elevation
        asset = _icon_asset()
        tray = TrayIcon(
            dashboard_url=lambda: runtime.config.dashboard_url(runtime.token),
            # 托盘不再自己 ``webbrowser.open``：管理员模式下"怎么打开"是一个有讲究的
            # 决定（见 :meth:`_open_external`），而那不是一层 pystray 封装该知道的事。
            open_dashboard=lambda: self._open_external(
                runtime, runtime.config.dashboard_url(runtime.token)
            ),
            on_quit=self.shutdown,
            # 设置页（18 文档 批 1）。**带令牌**：新标签页拿不到 sessionStorage 里那一份，
            # 而托盘拉起的浏览器窗口更是拿不到（页面收下之后会从地址栏抹掉它）。
            open_settings=lambda: self._open_external(
                runtime, runtime.config.settings_url(runtime.token)
            ),
            # 重新启动（18 文档 批 5）。与设置页那个按钮是同一条路径。
            on_restart=self.restart,
            # 暂停走的是**设置服务**，不是直接去掐采集组件：只有走服务才会一并
            # 写回 config.json（重启后仍是暂停的）并清查询缓存。托盘与设置页
            # 因此是同一条路径的两个入口，不可能出现两处状态不一致。
            paused_state=lambda: runtime.config.capture.paused,
            on_toggle_pause=lambda paused: self._set_paused(runtime, paused),
            # 端口为 None 的平台（macOS / Linux 尚未实现）不显示那一项。
            elevation_state=(
                (lambda: _elevation_state(elevation)) if elevation is not None else None
            ),
            on_elevate=(lambda: self._elevate(runtime)) if elevation is not None else None,
            open_data_dir=lambda: self._open_external(runtime, runtime.data_dir.as_uri()),
            open_logs_dir=lambda: self._open_external(
                runtime, paths.ensure_dir(paths.logs_dir(runtime.app_root)).as_uri()
            ),
            asset=asset,
            available=runtime.capabilities.tray,
        )
        runtime.tray = tray
        if not runtime.capabilities.tray:
            # 没有托盘时这是用户唯一能看到访问地址的地方（10 文档 §5.1）。
            print(f"OmniSight 正在运行：{runtime.config.dashboard_url(runtime.token)}")
        tray.run()

    def _set_paused(self, runtime: Runtime, paused: bool) -> None:
        """托盘的暂停开关。服务层不可用时退回直接掐采集组件——用户点了暂停，
        绝不能因为服务装配出了问题就"看起来暂停了但还在记录"。
        """
        services = runtime.services
        if services is None:  # pragma: no cover - 托盘运行时服务必已装配
            capture = runtime.capture
            if capture is not None:
                for component in (capture.keyboard, capture.foreground):
                    if component is not None:
                        component.pause() if paused else component.resume()
            return
        services.settings.patch({"capture.paused": paused})
        logger.info("托盘%s采集", "暂停" if paused else "恢复")

    def _elevate(self, runtime: Runtime) -> None:
        """托盘的「以管理员身份重启」（10 文档 §5.2）。

        顺序不能反：**先等 UAC 有结果，再停机**。反过来做的话，用户在确认框上点「否」
        就只剩下一个已经退出的程序——而他要表达的只是"算了，别提权"。

        新实例带 ``--takeover`` 启动，会等本实例把单实例锁与端口放掉再继续
        （见 :meth:`_acquire_instance_lock`）。

        线程上下文：本回调跑在托盘的消息循环线程上（pystray 的菜单项是同步派发的），
        而 UAC 确认框是模态的——确认框在屏幕上的那几秒托盘不响应右键，采集线程照常
        工作。确认之后的 :meth:`shutdown` 与托盘「退出」走的是同一条路径。
        """
        elevation = runtime.adapter_set.elevation
        if elevation is None:  # pragma: no cover - 端口缺失时托盘不显示那一项
            return
        try:
            started = elevation.relaunch_elevated()
        except Exception:
            logger.exception("请求以管理员身份重启失败")
            return
        if not started:
            logger.info("提权没有发生（用户取消或系统拒绝），继续以普通权限运行")
            return
        logger.info("管理员模式的新实例已在启动，本实例开始停机")
        self._successor_pending = True
        self.shutdown()

    def _open_external(self, runtime: Runtime, target: str) -> None:
        """打开浏览器或文件管理器。

        管理员模式下尽量**降权**打开：子进程默认继承父进程的令牌，于是从提权的
        OmniSight 里打开的程序会跟着拿到管理员权限。目录能可靠降权（走 explorer.exe）；
        URL 目前不能，端口会如实返回 False，这里退回常规打开——**打不开是最坏的结果**，
        那是用户唯一的入口。取舍与代价见 ``adapters/windows/elevation.py`` 的
        ``open_unelevated`` 与 10 文档 §5.2。
        """
        elevation = runtime.adapter_set.elevation
        if elevation is not None:
            try:
                if elevation.is_elevated() and elevation.open_unelevated(target):
                    return
            except Exception:
                logger.exception("降权打开 %s 失败，退回默认方式", target)
        webbrowser.open(target)

    # ── 进程级动作（18 文档 批 5）──────────────────────────────────────
    def restart(self) -> bool:
        """重新启动：**先起接班实例，确认它活着，再停机**。

        顺序不能反。先停机再启动，新实例起不来时用户就只剩一个消失的托盘图标——而他要的
        只是让改动生效。因此这里先拉起来、观察一小会儿，才安排停机；起不来就如实返回
        False，本实例什么都不改。

        接班实例带 ``--takeover``：它会等本实例交出单实例锁与端口
        （:meth:`_acquire_instance_lock`），并沿用 ``runtime.json`` 里的令牌
        （:meth:`_session_token`），因此已经打开的页面在重启后不必重新交接令牌。

        托盘与设置页共用这一条路径。返回值只对设置页有意义（它要把失败说给用户听）。
        """
        process = relaunch.spawn()
        if process is None:
            return False
        time.sleep(RESTART_PROBE_SECONDS)
        code = process.poll()
        if code is not None:
            logger.error("接班实例启动后立刻退出（退出码 %s），本实例继续运行", code)
            return False
        logger.info("接班实例已在启动，本实例开始停机")
        self._successor_pending = True
        self.stop_soon()
        return True

    def stop_soon(self) -> None:
        """把停机排到当前响应之后（18 文档 批 5）。

        调用方可能是 HTTP 处理线程：在那里同步 ``shutdown()`` 会先关掉 Web 服务器，于是
        响应永远出不了门，而浏览器看到的是一次连接中断——它分不清"在重启"和"崩了"。
        """
        threading.Thread(target=self._delayed_shutdown, name="shutdown-soon", daemon=True).start()

    def _delayed_shutdown(self) -> None:
        time.sleep(SHUTDOWN_DELAY_SECONDS)
        self.shutdown()

    def reveal(self, target: str) -> bool:
        """打开数据目录或日志目录。托盘那两项与设置页「数据」段是同一条路径。

        浏览器里的页面开不了文件管理器，而后端本来就要为"管理员模式下降权打开"负责
        （:meth:`_open_external`）——因此这件事只能在这一侧做，也只该做一次。
        """
        runtime = self.runtime
        if runtime is None:  # pragma: no cover - 装配完成前不会有人调它
            return False
        if target == "logs":
            uri = paths.ensure_dir(paths.logs_dir(runtime.app_root)).as_uri()
        else:
            uri = runtime.data_dir.as_uri()
        self._open_external(runtime, uri)
        return True

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
        self._release_runtime_file(runtime.data_dir)
        _guard("WAL checkpoint", lambda: runtime.database.checkpoint("TRUNCATE"))
        _guard("关闭数据库", runtime.database.close)
        _guard("释放单实例锁", runtime.adapter_set.instance_lock.release)
        if runtime.tray is not None:
            _guard("停止托盘", runtime.tray.stop)
        logger.info("已停机")

    def _release_runtime_file(self, data_dir: Path) -> None:
        """停机时处理 ``runtime.json``：**拉起过接班实例就留给它**。

        接班实例靠这个文件继承令牌（:meth:`_session_token`），而它此刻几乎肯定还没起来：
        onefile 的引导器要先把归档解到临时目录，实测 1 秒上下，而本实例从"开始停机"到
        "已停机"只用几百毫秒。删掉它，接班实例就只能换一个新令牌，于是重启后每一个已经
        打开的页面在下一次请求时 401——那正是继承令牌要消灭的症状（2026-09-06 现场日志：
        旧实例 01:08:11,570 写下"已停机"，接班实例的第一行日志是 01:08:11,609，相差 39
        毫秒；那一晚三次重启全部退化成新令牌）。

        留下它的代价只有一种形态："文件里的端口刚刚关掉"。而这个文件只在单实例锁被占着时
        才会被人读（:meth:`_handle_second_instance`），那时锁的主人正是接班实例，而它启动
        时已经用自己的端口与令牌覆盖过这份文件（见 :meth:`_start_web` 末尾）。
        """
        if self._successor_pending:
            logger.info("留下 runtime.json 给接班实例继承令牌")
            return
        _guard("移除 runtime.json", lambda: security.remove_runtime_file(data_dir))


def _guard(what: str, action) -> None:
    try:
        action()
    except Exception:
        logger.exception("停机步骤失败：%s", what)


def _elevation_state(control: ElevationControl) -> str:
    """把提权端口的状态压成托盘要显示的三档之一（10 文档 §5.2）。

    ``elevated`` 已在管理员模式；``available`` 可以提权；``unavailable`` 提不了
    （当前账户不是管理员——提权会换成另一个账户，数据目录随之改变）。

    收敛在这里而不是托盘里：托盘只该把状态翻译成一行字，而"什么算能提权"是平台语义。
    读状态永不抛异常——菜单每次右键都要画一遍，一个异常会毁掉整个菜单。
    """
    try:
        if control.is_elevated():
            return "elevated"
        return "available" if control.can_elevate() else "unavailable"
    except Exception:
        logger.exception("读取提权状态失败，按不可提权处理")
        return "unavailable"


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
