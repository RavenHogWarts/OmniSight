"""前台会话采集（← TimeLens ``monitor.py:AppMonitor``），04 文档 §2。

三处改动，都有明确理由：

1. **不再直接写库。** 会话入队，落盘由写入线程负责（02 文档 §3.1）。
2. **通过 ``ForegroundSource`` 端口取前台**，因此本文件里没有一个进程名、没有一次
   平台判断。系统外壳过滤是适配器的事（那份名单天生平台特定），**用户排除列表**
   是这里的事（与平台无关）。
3. **空闲期的探测节奏加密。** 旧代码判定空闲后每 60 秒才复查一次，用户回来后最多
   60 秒不产生会话。改为空闲期间按轮询间隔（1 秒）复查——``GetLastInputInfo`` 很便宜，
   而这 60 秒的盲区是实打实的时长丢失。

**会话在四种情况下结束**（04 文档 §2.3）：应用切换、心跳落盘（同一应用持续 ≥10s）、
进入空闲、程序退出。心跳落盘的意义是抗强杀：用户在一个应用里连续工作 3 小时，不切分
的话进程被杀就丢 3 小时，每 10 秒切一段最坏只丢 10 秒。
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass

from ..adapters.ports import UNKNOWN_APP_ID, AppIdentity, ForegroundSource, IdleSource
from ..core.bus import EventBus
from ..core.clock import Clock, SystemClock
from .coordinator import CaptureCoordinator
from .models import EndReason, UsageSession
from .queue import EventQueue

logger = logging.getLogger(__name__)

#: 亚秒会话不落盘：快速 Alt+Tab 穿过若干窗口会产生一串无统计价值的碎片
#: （04 文档 §2.4）。丢弃的是**会话**，不是**按键**——期间的按键仍归给该应用。
MIN_SESSION_MS = 1000

#: 空闲检查间隔。活跃时 60 秒一次足够（判定阈值是 30 分钟）；空闲期间改用轮询间隔。
IDLE_CHECK_SECONDS = 60.0

#: 前台应用切换事件（SSE 的 ``foreground`` 事件源，05 文档 §7）。载荷只有 ``app_id``；
#: 展示名由服务层解析——推送里带上名字等于让采集层认识"展示"这件事。
TOPIC_FOREGROUND_CHANGED = "foreground_changed"

#: 应用身份解析器：``AppIdentity`` → ``app_id``。
#:
#: **为什么由前台线程调用而不是交给写入线程**：Coordinator 必须在按键抬起的那一刻
#: 就能给出一个具体的 ``app_id``（04 文档 §4.1），因此解析不能延后。实现上它只在
#: 遇到**从未见过的应用**时才真的写一行（此后命中内存缓存），一次安装总共几十次，
#: 且发生在 1 秒一次的冷路径上——按键热路径依然零数据库访问。
ResolveApp = Callable[[AppIdentity], int]


@dataclass(slots=True)
class _Current:
    app_id: int
    identity: AppIdentity
    window_title: str
    start_ts_ns: int
    #: 本次**访问**的起点。心跳落盘会开新段但不改它（04 文档 §2.3）。
    visit_start_ts_ns: int


@dataclass(slots=True)
class ForegroundStats:
    polls: int = 0
    sessions: int = 0
    dropped_short: int = 0
    idle_truncations: int = 0
    switches: int = 0
    #: 完整的"访问"数（不含心跳切段），即 ``session_count`` 的口径。
    visits: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "polls": self.polls,
            "sessions": self.sessions,
            "dropped_short": self.dropped_short,
            "idle_truncations": self.idle_truncations,
            "switches": self.switches,
            "visits": self.visits,
        }


class ForegroundMonitor:
    """1 秒轮询前台窗口，切分会话并维护 Coordinator 的归因状态。"""

    def __init__(
        self,
        source: ForegroundSource,
        coordinator: CaptureCoordinator,
        queue: EventQueue,
        resolve_app: ResolveApp,
        *,
        idle_source: IdleSource | None = None,
        poll_seconds: float = 1.0,
        idle_threshold_seconds: float = 1800.0,
        session_flush_seconds: float = 10.0,
        excluded: frozenset[str] = frozenset(),
        clock: Clock | None = None,
        paused: bool = False,
        bus: EventBus | None = None,
    ) -> None:
        self._source = source
        self._coordinator = coordinator
        self._queue = queue
        self._resolve_app = resolve_app
        self._idle_source = idle_source
        self._poll_seconds = poll_seconds
        self._idle_threshold_seconds = idle_threshold_seconds
        self._session_flush_ns = int(session_flush_seconds * 1_000_000_000)
        self._excluded = excluded
        self._clock = clock or SystemClock()
        self._paused = paused
        self._bus = bus

        self._current: _Current | None = None
        self._is_idle = False
        self._last_idle_check_mono = 0.0
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.stats = ForegroundStats()

    # ── 生命周期 ────────────────────────────────────────────────────────
    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    @property
    def paused(self) -> bool:
        return self._paused

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="foreground", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 3.0) -> None:
        """停止并把当前会话入队——否则最后一段（最多 10 秒）会丢。"""
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=timeout)
        self._flush(self._clock.time_ns(), reason="shutdown")
        self._coordinator.clear()

    def pause(self) -> None:
        self._paused = True
        self._flush(self._clock.time_ns(), reason="shutdown")
        self._coordinator.set_foreground(None)

    def resume(self) -> None:
        self._paused = False

    # ── 运行期可改的设置（``PATCH /api/v1/settings`` 会调它们）─────────────
    def set_excluded(self, excluded: frozenset[str]) -> None:
        """运行期更新用户排除列表。"""
        self._excluded = excluded

    def set_idle_threshold_seconds(self, seconds: float) -> None:
        self._idle_threshold_seconds = seconds

    def set_poll_seconds(self, seconds: float) -> None:
        """下一轮生效：循环每次迭代都读这个值。"""
        self._poll_seconds = seconds

    def set_session_flush_seconds(self, seconds: float) -> None:
        self._session_flush_ns = int(seconds * 1_000_000_000)

    #: ``/api/v1/status`` 里 ``capture.foreground.backend`` 的取值（05 文档 §7）。
    #:
    #: 写死 ``"polling"`` 而不是 ``type(self._source).__name__``：后者会把
    #: ``WindowsForegroundSource`` 这种**带平台名的字符串**送进接口，而前端被明确
    #: 禁止按平台字符串分支（07 文档 §10）——留一个现成的把柄不如不留。轮询是三个
    #: 平台共同的机制，平台本身已由 ``platform.id`` 上报。
    BACKEND_NAME = "polling"

    def snapshot(self) -> dict[str, object]:
        current = self._current
        return {
            "running": self.running,
            "backend": self.BACKEND_NAME,
            "paused": self._paused,
            "idle": self._is_idle,
            "current_app_id": current.app_id if current else UNKNOWN_APP_ID,
            **self.stats.as_dict(),
        }

    # ── 轮询 ────────────────────────────────────────────────────────────
    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:
                # 一次探测失败绝不能让采集线程死掉——它是常驻的。
                logger.exception("前台监控循环异常，继续运行")
            self._stop.wait(self._poll_seconds)

    def tick(self) -> None:
        """走一遍探测。**公开是为了可测**：测试直接驱动它，不必等真实的 sleep。"""
        self.stats.polls += 1
        now_ns = self._clock.time_ns()
        mono = self._clock.monotonic_ns() / 1_000_000_000

        if self._paused:
            return
        if self._check_idle(now_ns, mono):
            return

        info = self._source.current()
        if info is None:
            # 无前台窗口 / 系统外壳 / 探测失败：结束会话，按键归到未知。
            self._flush(now_ns, reason="no_foreground")
            self._coordinator.set_foreground(None)
            return

        identity = info.identity
        if identity.app_key in self._excluded:
            # 用户排除：不产生会话，期间按键归 app_id = 0 而**不丢弃**——键盘总量
            # 必须守恒，否则"各应用按键之和 < 总按键数"的差额无法解释（04 文档 §2.2）。
            self._flush(now_ns, reason="excluded")
            self._coordinator.set_foreground(None)
            return

        app_id = self._resolve_app(identity)
        current = self._current
        if current is None or current.app_id != app_id:
            self._flush(now_ns, reason="switch")
            self.stats.switches += 1
            self._begin(app_id, identity, info.window_title, now_ns)
            self._announce(app_id)
        else:
            # 同一应用：刷新标题与身份（exe 路径可能这次才拿到），必要时心跳落盘。
            current.window_title = info.window_title
            current.identity = identity
            if now_ns - current.start_ts_ns >= self._session_flush_ns:
                visit_start = current.visit_start_ts_ns
                self._flush(now_ns, reason="heartbeat")
                # 心跳落盘只是把同一次访问切开以抗强杀，**访问起点不变**——
                # 否则"最长一次使用"永远等于心跳间隔，"使用次数"会翻几百倍。
                self._begin(app_id, identity, info.window_title, now_ns, visit_start=visit_start)
        self._coordinator.set_foreground(app_id)

    def _check_idle(self, now_ns: int, mono: float) -> bool:
        """返回 ``True`` 表示当前处于空闲，本轮不做前台探测。"""
        if self._idle_source is None:
            return False
        # 空闲期间按轮询间隔复查，活跃期间 60 秒一次。
        interval = self._poll_seconds if self._is_idle else IDLE_CHECK_SECONDS
        if mono - self._last_idle_check_mono < interval:
            return self._is_idle
        self._last_idle_check_mono = mono

        idle_seconds = self._idle_source.idle_seconds()
        was_idle = self._is_idle
        self._is_idle = idle_seconds >= self._idle_threshold_seconds
        self._coordinator.set_idle(self._is_idle)
        if self._is_idle and not was_idle:
            # 会话实际结束于"最后一次输入 + 阈值"，而不是我们发现空闲的时刻。不回溯的话
            # "挂机 8 小时"会被记成 8 小时使用（04 文档 §2.3）。
            active_until = now_ns - int((idle_seconds - self._idle_threshold_seconds) * 1e9)
            self.stats.idle_truncations += 1
            self._flush(max(active_until, 0), idle_trimmed=True, reason="idle")
            self._coordinator.set_foreground(None)
        return self._is_idle

    # ── 会话切分 ────────────────────────────────────────────────────────
    def _begin(
        self,
        app_id: int,
        identity: AppIdentity,
        title: str,
        start_ts_ns: int,
        *,
        visit_start: int | None = None,
    ) -> None:
        self._current = _Current(
            app_id=app_id,
            identity=identity,
            window_title=title,
            start_ts_ns=start_ts_ns,
            visit_start_ts_ns=visit_start if visit_start is not None else start_ts_ns,
        )

    def _announce(self, app_id: int) -> None:
        if self._bus is not None:
            self._bus.publish(TOPIC_FOREGROUND_CHANGED, app_id)

    def _flush(
        self, end_ts_ns: int, *, idle_trimmed: bool = False, reason: EndReason = "switch"
    ) -> None:
        current, self._current = self._current, None
        if current is None:
            return
        # 墙钟被回拨过（NTP、用户改时间）时不产生负时长。段长最多 10 秒，因此一次
        # 跳变最多影响一段。
        end_ts_ns = max(end_ts_ns, current.start_ts_ns)
        duration_ms = (end_ts_ns - current.start_ts_ns) // 1_000_000
        if duration_ms < MIN_SESSION_MS:
            self.stats.dropped_short += 1
            return
        self.stats.sessions += 1
        if current.visit_start_ts_ns == current.start_ts_ns:
            self.stats.visits += 1
        self._queue.put(
            UsageSession(
                app_id=current.app_id,
                start_ts_ns=current.start_ts_ns,
                end_ts_ns=end_ts_ns,
                duration_ms=duration_ms,
                window_title=current.window_title,
                idle_trimmed=idle_trimmed,
                end_reason=reason,
                visit_start_ts_ns=current.visit_start_ts_ns,
            )
        )


__all__ = [
    "IDLE_CHECK_SECONDS",
    "MIN_SESSION_MS",
    "TOPIC_FOREGROUND_CHANGED",
    "ForegroundMonitor",
    "ForegroundStats",
    "ResolveApp",
]
