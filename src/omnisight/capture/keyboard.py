"""按键采集编排（← KeyTrace ``monitor.py:KeyboardTracker``），04 文档 §3.3、§3.4。

与旧实现的**根本区别**：``_release`` 不再同步写数据库。旧代码的调用链是
``_read_keyboard → callback → on_raw_input → _release → record_event``，而
``record_event`` 一次执行 5 条 SQL 并 commit——整条链都跑在 Raw Input 的消息泵线程上。
WAL 模式下一次事务仍可能因 checkpoint 或磁盘抖动阻塞几十毫秒，期间消息队列积压，
重则丢事件、轻则让整机输入产生可感知延迟（02 文档 §3.1）。

现在回调只做纯内存操作：查表、记时间、算时长、读一个引用、入队。微秒级。

本文件**完全不知道**自己拿到的是哪个后端。"长按算一次"是产品语义而非平台细节，
因此去重规则统一在这里做，三个平台自动一致；适配器只负责忠实上报按下/抬起。

热路径上不加锁：只有后端线程会调 ``_on_raw``，``dict`` 的读写与 ``pop`` 在 CPython 下
是原子的。``pause()``/``stop()`` 从别的线程清空 ``_pressed`` 只会影响"这次长按算不算
数"，不会产生半个状态。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ..adapters.ports import CaptureUnavailable, KeyboardSource, RawKeyEvent
from ..core.bus import EventBus
from .coordinator import CaptureCoordinator
from .models import KeyEvent
from .queue import EventQueue

logger = logging.getLogger(__name__)

#: 超过一分钟的"按住"意味着我们漏了抬起（焦点丢失、消息丢失、物理卡键）。
#: 不截断的话，一次丢失的抬起就能把某个键的 ``duration_max_ms`` 变成几小时，
#: 而聚合表是累加的、无法回滚（04 文档 §3.4）。
MAX_PLAUSIBLE_PRESS_MS = 60_000.0

#: 事件总线主题：仅推 ``key_id``，不推时间戳与内容（08 文档 §3.3）。
TOPIC_KEY_PRESSED = "key_pressed"


@dataclass(frozen=True, slots=True)
class PressState:
    wall_ts_ns: int
    mono_ts_ns: int
    hid_usage: int | None
    native_code: int | None
    native_code2: int | None


@dataclass(slots=True)
class KeyboardStats:
    presses: int = 0
    releases: int = 0
    #: 抬起时没有对应按下：程序启动前键已按住。无法知道按下时刻，只能丢弃。
    unpaired_releases: int = 0
    clamped: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "presses": self.presses,
            "releases": self.releases,
            "unpaired_releases": self.unpaired_releases,
            "clamped": self.clamped,
        }


class KeyboardCapture:
    """把 :class:`KeyboardSource` 的原始上报变成带归因的 :class:`KeyEvent`。"""

    def __init__(
        self,
        source: KeyboardSource,
        coordinator: CaptureCoordinator,
        queue: EventQueue,
        *,
        bus: EventBus | None = None,
        realtime_stream: bool = True,
        paused: bool = False,
    ) -> None:
        self._source = source
        self._coordinator = coordinator
        self._queue = queue
        self._bus = bus
        self._realtime_stream = realtime_stream
        self._paused = paused
        self._pressed: dict[str, PressState] = {}
        self.stats = KeyboardStats()

    # ── 生命周期 ────────────────────────────────────────────────────────
    @property
    def running(self) -> bool:
        return bool(self._source.running)

    @property
    def backend_name(self) -> str:
        return self._source.backend_name

    @property
    def paused(self) -> bool:
        return self._paused

    def start(self) -> None:
        """启动后端。失败抛 :class:`CaptureUnavailable`，**不应导致程序退出**。"""
        self._source.start(self._on_raw)

    def stop(self) -> None:
        self._source.stop()
        # 停止时仍按住的键不落盘：只有按下时刻、没有抬起时刻，时长无从得知。
        self._pressed.clear()

    def pause(self) -> None:
        """暂停采集。必须是真的暂停——一个"以为在记录但实际没记"的工具比不记录更糟。"""
        self._paused = True
        self._pressed.clear()

    def resume(self) -> None:
        """恢复。不补记暂停期间的任何数据（04 文档 §7）。"""
        self._paused = False

    def snapshot(self) -> dict[str, object]:
        return {
            "running": self.running,
            "backend": self.backend_name,
            "paused": self._paused,
            "pressed_now": len(self._pressed),
            "unmapped_events": int(getattr(self._source, "unmapped_events", 0)),
            **self.stats.as_dict(),
        }

    # ── 热路径 ──────────────────────────────────────────────────────────
    def _on_raw(self, event: RawKeyEvent) -> None:
        if self._paused:
            return
        if event.pressed:
            self._press(event)
        else:
            self._release(event)

    def _press(self, event: RawKeyEvent) -> None:
        if event.key_id in self._pressed:
            # 自动重复：一次长按记为**一次**按下，时长为整个按住时长。这让
            # duration_max_ms 这个指标有意义（04 文档 §3.3）。
            return
        self._pressed[event.key_id] = PressState(
            wall_ts_ns=event.wall_ts_ns,
            mono_ts_ns=event.mono_ts_ns,
            hid_usage=event.hid_usage,
            native_code=event.native_code,
            native_code2=event.native_code2,
        )
        self.stats.presses += 1
        if self._bus is not None and self._realtime_stream:
            # 实时高亮要的是"按下的那一刻"，因此发在按下而非抬起（01 文档 §5.2）。
            self._bus.publish(TOPIC_KEY_PRESSED, event.key_id)

    def _release(self, event: RawKeyEvent) -> None:
        state = self._pressed.pop(event.key_id, None)
        if state is None:
            self.stats.unpaired_releases += 1
            return
        self.stats.releases += 1

        # 时长用单调钟：墙钟会被 NTP 校时或用户改时间拨动，用它算会出现负值或荒谬
        # 的大值。分桶用墙钟——单调钟无法定位到日历日期（04 文档 §3.3）。
        duration_ms = max(0.0, (event.mono_ts_ns - state.mono_ts_ns) / 1_000_000)
        clamped = duration_ms > MAX_PLAUSIBLE_PRESS_MS
        if clamped:
            duration_ms = MAX_PLAUSIBLE_PRESS_MS
            self.stats.clamped += 1

        # ★ 合并带来的关键一步：归因在采集时刻完成，不是查询时算。
        attribution = self._coordinator.attribution()
        self._queue.put(
            KeyEvent(
                key_id=event.key_id,
                down_ts_ns=state.wall_ts_ns,
                up_ts_ns=event.wall_ts_ns,
                duration_ms=duration_ms,
                app_id=attribution.app_id,
                confidence=attribution.confidence,
                hid_usage=state.hid_usage,
                native_code=state.native_code,
                native_code2=state.native_code2,
                clamped=clamped,
            )
        )


__all__ = [
    "MAX_PLAUSIBLE_PRESS_MS",
    "TOPIC_KEY_PRESSED",
    "CaptureUnavailable",
    "KeyboardCapture",
    "KeyboardStats",
    "PressState",
]
