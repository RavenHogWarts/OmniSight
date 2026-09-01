"""日志红线（10 文档 §7、11 文档 §4.5）。

08 文档承诺"日志里不出现窗口标题与按键标识"。人写代码会忘，过滤器不会——
所以这条承诺必须有机械化的保障，而不是靠 code review。
"""

from __future__ import annotations

import logging
from pathlib import Path

from omnisight.core import logging as log_setup

SECRET_TITLE = "季度财报（机密） - Excel"


def test_window_title_is_scrubbed():
    assert SECRET_TITLE not in log_setup.scrub(f"session end window_title='{SECRET_TITLE}'")


def test_key_id_is_scrubbed():
    assert "key_a" not in log_setup.scrub("flush key_id=key_a count=3")


def test_aggregate_counts_survive():
    """允许记录聚合计数——否则排查写入性能问题时无从下手。"""
    message = "flushed 412 key events, 3 sessions in 18ms"
    assert log_setup.scrub(message) == message


def test_filter_applies_to_records_written_through_logging(tmp_path: Path):
    log_path = log_setup.configure(tmp_path, console=False)
    logging.getLogger("test.privacy").info("closing window_title=%r", SECRET_TITLE)
    for handler in logging.getLogger().handlers:
        handler.flush()
    contents = log_path.read_text(encoding="utf-8")
    assert SECRET_TITLE not in contents
    assert log_setup.REDACTED in contents


def test_configure_is_repeatable_without_duplicating_handlers(tmp_path: Path):
    log_setup.configure(tmp_path, console=False)
    first = len(logging.getLogger().handlers)
    log_setup.configure(tmp_path, console=False)
    assert len(logging.getLogger().handlers) == first


def test_logs_never_contain_key_ids_or_titles_while_capture_runs(tmp_path: Path):
    """M1 起真的有采集了，因此这条承诺要在**跑着的管道**上验一遍。

    上面几条测的是过滤器本身；这一条测的是"过滤器真的挂在了采集代码会用的那些
    logger 上"。两者缺一不可——过滤器写对了但没装上，日志照样泄漏。
    """
    from fakes import FakeClock, FakeForegroundSource, FakeKeyboardSource
    from omnisight.capture.coordinator import CaptureCoordinator
    from omnisight.capture.foreground import ForegroundMonitor
    from omnisight.capture.keyboard import KeyboardCapture
    from omnisight.capture.queue import EventQueue

    log_path = log_setup.configure(tmp_path, console=False)
    clock = FakeClock()
    queue = EventQueue()
    coordinator = CaptureCoordinator(monotonic=clock.monotonic)
    source = FakeForegroundSource()
    monitor = ForegroundMonitor(
        source, coordinator, queue, lambda identity: 1, clock=clock, poll_seconds=1.0
    )
    keyboard_source = FakeKeyboardSource(clock)
    keyboard = KeyboardCapture(keyboard_source, coordinator, queue, realtime_stream=False)
    keyboard.start()

    source.switch_to("code.exe", title=SECRET_TITLE)
    monitor.tick()
    clock.advance(seconds=2)
    for key_id in ("key_a", "shift_left", "digit7"):
        keyboard_source.tap(key_id)
    # 让采集侧真的记一次日志（正常路径下它只在异常时记，因此这里主动触发一次）。
    logging.getLogger("omnisight.capture.foreground").info(
        "session end window_title=%r key_id=%s", SECRET_TITLE, "key_a"
    )
    monitor.stop()
    keyboard.stop()

    for handler in logging.getLogger().handlers:
        handler.flush()
    contents = log_path.read_text(encoding="utf-8")
    assert SECRET_TITLE not in contents
    assert "key_id=key_a" not in contents
    assert log_setup.REDACTED in contents
