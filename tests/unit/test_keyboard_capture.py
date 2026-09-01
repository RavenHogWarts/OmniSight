"""按键采集的产品语义（04 文档 §3.3、§3.4；11 文档 §3.4）。

"长按算一次""卡键要截断""时长用单调钟"这三条都是**产品语义而非平台细节**，因此
统一在 ``capture/keyboard.py`` 做，三个平台自动一致。这也意味着它们可以用假后端在
任何平台上测——本文件不需要 Raw Input。
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from fakes import FakeClock, FakeKeyboardSource
from omnisight.adapters.ports import CaptureUnavailable
from omnisight.capture.coordinator import CaptureCoordinator
from omnisight.capture.keyboard import (
    MAX_PLAUSIBLE_PRESS_MS,
    TOPIC_KEY_PRESSED,
    KeyboardCapture,
)
from omnisight.capture.models import KeyEvent
from omnisight.capture.queue import EventQueue
from omnisight.core.bus import EventBus


def _capture(clock: FakeClock, **kwargs):
    source = FakeKeyboardSource(clock)
    queue = EventQueue()
    coordinator = CaptureCoordinator(monotonic=clock.monotonic)
    capture = KeyboardCapture(source, coordinator, queue, **kwargs)
    capture.start()
    return capture, source, queue, coordinator


def _events(queue: EventQueue) -> list[KeyEvent]:
    return [event for event in queue.drain_all() if isinstance(event, KeyEvent)]


def test_a_press_and_release_produces_exactly_one_event():
    clock = FakeClock()
    _capture_obj, source, queue, _ = _capture(clock)
    source.tap("key_a", hold_ms=120)
    events = _events(queue)
    assert len(events) == 1
    assert events[0].key_id == "key_a"
    assert events[0].duration_ms == 120


def test_auto_repeat_counts_as_one_press_for_the_whole_hold():
    """长按会连续上报按下。记多次会让 press_count 变成"按了多久"而不是"按了几次"，
    并让 ``duration_max_ms`` 这个指标彻底失去意义（04 文档 §3.3）。
    """
    clock = FakeClock()
    capture, source, queue, _ = _capture(clock)
    source.emit("key_a", pressed=True)
    for _ in range(30):  # 自动重复
        clock.advance(ms=30)
        source.emit("key_a", pressed=True)
    source.emit("key_a", pressed=False)

    events = _events(queue)
    assert len(events) == 1
    assert events[0].duration_ms == 900  # 整个按住时长
    assert capture.stats.presses == 1


def test_duration_uses_monotonic_not_wall_clock():
    """NTP 回拨或用户改时间时，用墙钟算会出现负值或荒谬的大值。"""
    clock = FakeClock()
    _capture_obj, source, queue, _ = _capture(clock)
    source.emit("key_a", pressed=True)
    clock.advance_monotonic(ms=120)
    clock.set_wall_clock(back_by=timedelta(hours=1))
    source.emit("key_a", pressed=False)

    events = _events(queue)
    assert len(events) == 1
    assert events[0].duration_ms == 120
    # 墙钟时间戳照实落盘（分桶只能靠它），因此这里 up < down 是可能的——
    # 但**时长**不受影响，这正是两个钟分开的意义。
    assert events[0].up_ts_ns < events[0].down_ts_ns


def test_stuck_key_duration_is_clamped_and_flagged():
    """漏掉一次抬起就能把某个键的 duration_max_ms 变成几小时，而聚合表是累加的、
    无法回滚（04 文档 §3.4）。
    """
    clock = FakeClock()
    capture, source, queue, _ = _capture(clock)
    source.emit("key_a", pressed=True)
    clock.advance(seconds=7200)
    source.emit("key_a", pressed=False)

    events = _events(queue)
    assert events[0].duration_ms == MAX_PLAUSIBLE_PRESS_MS
    assert events[0].clamped is True
    assert capture.stats.clamped == 1


def test_release_without_press_is_counted_not_guessed():
    """程序启动前键已按住：只有抬起时刻，时长无从得知，只能丢弃——但要留下痕迹。"""
    clock = FakeClock()
    capture, source, queue, _ = _capture(clock)
    source.emit("shift_left", pressed=False)
    assert _events(queue) == []
    assert capture.stats.unpaired_releases == 1
    assert capture.stats.releases == 0


def test_keys_held_at_stop_are_not_written():
    clock = FakeClock()
    capture, source, queue, _ = _capture(clock)
    source.emit("key_a", pressed=True)
    capture.stop()
    assert _events(queue) == []
    assert source.stop_calls == 1
def test_paused_capture_records_nothing():
    """暂停必须是真的暂停——"以为在记录但实际没记"比不记录更糟（11 文档 §4.5）。"""
    clock = FakeClock()
    capture, source, queue, _ = _capture(clock, paused=True)
    for _ in range(10):
        source.tap("key_a")
    assert _events(queue) == []
    assert capture.stats.presses == 0

    capture.resume()
    source.tap("key_a")
    assert len(_events(queue)) == 1


def test_pause_mid_hold_does_not_leave_a_dangling_press():
    """暂停时清空按下表，否则恢复后第一次抬起会算出一个横跨暂停期的时长。"""
    clock = FakeClock()
    capture, source, queue, _ = _capture(clock)
    source.emit("key_a", pressed=True)
    capture.pause()
    clock.advance(seconds=600)
    capture.resume()
    source.emit("key_a", pressed=False)
    assert _events(queue) == []
    assert capture.stats.unpaired_releases == 1


def test_attribution_is_attached_at_release_time():
    """★ 合并的关键一步：app_id 在采集时刻就定下来，不是查询时算区间交集。"""
    clock = FakeClock()
    _capture_obj, source, queue, coordinator = _capture(clock)
    coordinator.set_foreground(42)
    clock.advance(seconds=3)  # 越过 boundary 窗口
    source.tap("key_a")

    event = _events(queue)[0]
    assert event.app_id == 42
    assert event.confidence == "high"
    assert event.confidence_code == 2


def test_keys_during_switch_are_marked_boundary_not_dropped():
    clock = FakeClock()
    _capture_obj, source, queue, coordinator = _capture(clock)
    coordinator.set_foreground(1)
    source.tap("key_a", hold_ms=10)  # 切换后 10ms，仍在 boundary 窗口内
    event = _events(queue)[0]
    assert event.app_id == 1
    assert event.confidence == "boundary"


def test_keys_with_no_foreground_go_to_the_sentinel_app():
    """归到 app_id = 0 而不是丢弃——键盘总量必须守恒，否则"各应用之和 < 总数"
    的差额无法解释。
    """
    clock = FakeClock()
    _capture_obj, source, queue, _ = _capture(clock)
    source.tap("key_a")
    event = _events(queue)[0]
    assert event.app_id == 0
    assert event.confidence == "unknown"


def test_native_codes_are_carried_from_press_not_release():
    """诊断字段取按下那一次的值：抬起报文的 vk 在某些键上与按下不同。"""
    clock = FakeClock()
    _capture_obj, source, queue, _ = _capture(clock)
    source.emit("key_a", pressed=True, hid_usage=0x04, native_code=0x1E)
    source.emit("key_a", pressed=False, hid_usage=None, native_code=None)
    event = _events(queue)[0]
    assert event.hid_usage == 0x04
    assert event.native_code == 0x1E


def test_realtime_stream_publishes_only_the_key_id_on_press():
    """SSE 只推 key_id：不推时间戳、不推内容（08 文档 §3.3）。

    推时间戳就等于推击键节奏，而击键节奏足以做用户识别；这条约束是隐私承诺的一部分，
    因此这里断言的是消息**形状**，不只是"有消息"。
    """
    clock = FakeClock()
    bus = EventBus()
    received: list[tuple[str, object]] = []
    bus.subscribe(TOPIC_KEY_PRESSED, lambda topic, payload: received.append((topic, payload)))
    _capture_obj, source, _queue, _ = _capture(clock, bus=bus, realtime_stream=True)

    source.tap("key_a")
    assert received == [(TOPIC_KEY_PRESSED, "key_a")], "载荷只应是 key_id 字符串本身"


def test_realtime_stream_can_be_switched_off():
    clock = FakeClock()
    bus = EventBus()
    received: list = []
    bus.subscribe(TOPIC_KEY_PRESSED, lambda topic, payload: received.append(payload))
    _capture_obj, source, _queue, _ = _capture(clock, bus=bus, realtime_stream=False)
    source.tap("key_a")
    assert received == []


def test_snapshot_reports_backend_and_counters():
    clock = FakeClock()
    capture, source, _queue, _ = _capture(clock)
    source.tap("key_a")
    snapshot = capture.snapshot()
    assert snapshot["running"] is True
    assert snapshot["backend"] == "fake"
    assert snapshot["presses"] == 1
    assert snapshot["pressed_now"] == 0
    assert snapshot["unmapped_events"] == 0


def test_unmapped_events_are_surfaced_from_the_backend():
    """未映射的键必须能被看到——否则"某个键永远是 0"是唯一症状。"""
    clock = FakeClock()
    capture, source, _queue, _ = _capture(clock)
    source.unmapped_events = 3
    assert capture.snapshot()["unmapped_events"] == 3


def test_start_failure_is_raised_for_the_caller_to_degrade():
    """键盘起不来不许让程序退出：屏幕时间统计必须照常工作（10 文档 §6）。"""
    clock = FakeClock()
    source = FakeKeyboardSource(clock, fail_on_start=True)
    capture = KeyboardCapture(source, CaptureCoordinator(), EventQueue())
    with pytest.raises(CaptureUnavailable):
        capture.start()
    assert capture.running is False
