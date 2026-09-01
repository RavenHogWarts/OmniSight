"""可注入的测试替身（11 文档 §2 的"可测性接缝"）。

每一个都对应一处**刻意留出的接缝**，而不是为了绕开某个难测的实现：

* :class:`FakeClock` —— 墙钟与单调钟分开推进，这是验证"改系统时间不影响时长"的
  唯一方式（04 文档 §3.3）。
* :class:`FakeForegroundSource` / :class:`FakeIdleSource` —— 让前台会话切分与空闲
  截断可以在任何平台上被测试，不需要真的切换窗口或挂机半小时。
* :class:`FakeKeyboardSource` —— 让"按下/抬起配对、长按去重、卡键截断"这些**产品
  语义**脱离 Raw Input 被测试；它们统一在 ``capture/`` 层做，因此三个平台一致。

放在 ``tests/`` 根而不是 ``conftest.py``：这些是类，需要在用例里带参数构造，做成
fixture 反而绕了一圈（``pythonpath`` 在 pyproject 里已包含 ``tests``）。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta, tzinfo

from omnisight.adapters.ports import (
    AppIdentity,
    CaptureUnavailable,
    ForegroundInfo,
    RawKeyEvent,
)

#: 一个固定的、与真实时间无关的起点。带时区，避免 naive/aware 混用。
DEFAULT_START = datetime(2026, 8, 31, 9, 0, 0, tzinfo=UTC)


class FakeClock:
    """墙钟与单调钟**独立**可控。

    默认两者一起走（:meth:`advance`），需要模拟 NTP 校时或用户改时间时分别推。
    单调钟起点故意不是 0：真实的 ``perf_counter_ns`` 也不是，写死 0 会掩盖"把单调
    时间当成了纪元时间"这类错误。
    """

    def __init__(self, start: datetime = DEFAULT_START, tz: tzinfo | None = None) -> None:
        self._now = start.astimezone(tz) if tz else start
        self._mono_ns = 12_345_000_000_000

    # ── Clock 协议 ──────────────────────────────────────────────────────
    def now(self) -> datetime:
        return self._now

    def time_ns(self) -> int:
        return int(self._now.timestamp() * 1_000_000_000)

    def monotonic_ns(self) -> int:
        return self._mono_ns

    def monotonic(self) -> float:
        """给 :class:`~omnisight.capture.coordinator.CaptureCoordinator` 用（它只要秒）。"""
        return self._mono_ns / 1_000_000_000

    # ── 推进 ────────────────────────────────────────────────────────────
    def advance(self, seconds: float = 0.0, *, ms: float = 0.0) -> None:
        """两个钟一起走——正常时间流逝。"""
        delta = seconds + ms / 1000
        self._now += timedelta(seconds=delta)
        self._mono_ns += int(delta * 1_000_000_000)

    def advance_monotonic(self, seconds: float = 0.0, *, ms: float = 0.0) -> None:
        """只推单调钟：用于"时长应当只由单调钟决定"的断言。"""
        self._mono_ns += int((seconds + ms / 1000) * 1_000_000_000)

    def set_wall_clock(self, *, back_by: timedelta | None = None,
                       forward_by: timedelta | None = None) -> None:
        """只动墙钟：模拟 NTP 回拨或用户改系统时间。"""
        if back_by is not None:
            self._now -= back_by
        if forward_by is not None:
            self._now += forward_by

    def set_wall_time(self, moment: datetime) -> None:
        self._now = moment


def identity(app_key: str, *, display_name: str | None = None,
             exe_path: str = "") -> AppIdentity:
    return AppIdentity(
        app_key=app_key.lower(),
        identity_kind="process",
        display_name=display_name or app_key,
        process_name=app_key,
        exe_path=exe_path,
    )


class FakeForegroundSource:
    """当前前台由测试直接设定。``None`` 表示无前台（锁屏、系统外壳、探测失败）。"""

    def __init__(self, info: ForegroundInfo | None = None) -> None:
        self._info = info
        self.calls = 0
        self.raise_next = False

    def current(self) -> ForegroundInfo | None:
        self.calls += 1
        if self.raise_next:
            self.raise_next = False
            raise OSError("模拟一次探测失败")
        return self._info

    def list_running(self) -> list[AppIdentity]:
        return [self._info.identity] if self._info else []

    # ── 测试驱动 ────────────────────────────────────────────────────────
    def switch_to(self, app_key: str, *, title: str = "") -> None:
        self._info = ForegroundInfo(identity=identity(app_key), window_title=title)

    def clear(self) -> None:
        self._info = None


class FakeIdleSource:
    def __init__(self, idle: float = 0.0) -> None:
        self.idle = idle

    def idle_seconds(self) -> float:
        return self.idle


class FakeKeyboardSource:
    """由测试直接投递按下/抬起，时间戳取自注入的钟。"""

    def __init__(self, clock: FakeClock | None = None, *, fail_on_start: bool = False,
                 backend_name: str = "fake") -> None:
        self._clock = clock or FakeClock()
        self._sink: Callable[[RawKeyEvent], None] | None = None
        self._fail_on_start = fail_on_start
        self._backend_name = backend_name
        self.running = False
        self.needs_main_loop = False
        self.unmapped_events = 0
        self.stop_calls = 0

    @property
    def backend_name(self) -> str:
        return self._backend_name

    def start(self, sink: Callable[[RawKeyEvent], None]) -> None:
        if self._fail_on_start:
            raise CaptureUnavailable("模拟后端注册失败")
        self._sink = sink
        self.running = True

    def stop(self) -> None:
        self.stop_calls += 1
        self.running = False
        self._sink = None

    # ── 测试驱动 ────────────────────────────────────────────────────────
    def emit(self, key_id: str, *, pressed: bool, hid_usage: int | None = None,
             native_code: int | None = None) -> None:
        if self._sink is None:
            raise AssertionError("后端还没启动，不该有事件")
        self._sink(
            RawKeyEvent(
                key_id=key_id,
                pressed=pressed,
                wall_ts_ns=self._clock.time_ns(),
                mono_ts_ns=self._clock.monotonic_ns(),
                hid_usage=hid_usage,
                native_code=native_code,
            )
        )

    def tap(self, key_id: str, *, hold_ms: float = 80.0) -> None:
        """一次完整按压：按下、时间流逝、抬起。"""
        self.emit(key_id, pressed=True)
        self._clock.advance(ms=hold_ms)
        self.emit(key_id, pressed=False)


__all__ = [
    "DEFAULT_START",
    "FakeClock",
    "FakeForegroundSource",
    "FakeIdleSource",
    "FakeKeyboardSource",
    "identity",
]
