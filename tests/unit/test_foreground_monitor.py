"""前台会话切分与空闲判定（04 文档 §2；11 文档 §2 的可测性接缝）。

用 ``tick()`` 直接驱动，不起线程也不 sleep：整组用例在毫秒级跑完，而覆盖的是
"挂机 8 小时被记成 8 小时使用"这类只有真人挂机才会遇到的 bug。

``resolve_app`` 在这里是一个假的字典查找。真实实现（``AppRegistry``）会写库，
但它对本文件的语义没有影响——前台监控只关心"同一个应用是否还是同一个 id"。
"""

from __future__ import annotations

from datetime import timedelta

from fakes import FakeClock, FakeForegroundSource, FakeIdleSource
from omnisight.capture.coordinator import CaptureCoordinator
from omnisight.capture.foreground import MIN_SESSION_MS, ForegroundMonitor
from omnisight.capture.models import UsageSession
from omnisight.capture.queue import EventQueue

APP_IDS = {"code.exe": 1, "chrome.exe": 2, "secret.exe": 3}


def _monitor(clock: FakeClock, source: FakeForegroundSource, **kwargs):
    queue = EventQueue()
    coordinator = CaptureCoordinator(monotonic=clock.monotonic)
    monitor = ForegroundMonitor(
        source,
        coordinator,
        queue,
        lambda identity: APP_IDS.get(identity.app_key, 0),
        clock=clock,
        poll_seconds=1.0,
        session_flush_seconds=10.0,
        **kwargs,
    )
    return monitor, queue, coordinator


def _sessions(queue: EventQueue) -> list[UsageSession]:
    return [event for event in queue.drain_all() if isinstance(event, UsageSession)]


def test_switching_apps_closes_the_previous_session():
    clock = FakeClock()
    source = FakeForegroundSource()
    monitor, queue, coordinator = _monitor(clock, source)

    source.switch_to("code.exe")
    monitor.tick()
    for _ in range(4):
        clock.advance(seconds=1)
        monitor.tick()
    source.switch_to("chrome.exe")
    clock.advance(seconds=1)
    monitor.tick()

    sessions = _sessions(queue)
    assert len(sessions) == 1
    assert sessions[0].app_id == 1
    assert sessions[0].duration_ms == 5000
    assert coordinator.current_app_id == 2


def test_heartbeat_splits_a_long_session_so_a_kill_loses_at_most_one_slice():
    """用户在一个应用里连续工作 3 小时，不切分的话进程被杀就丢 3 小时。"""
    clock = FakeClock()
    source = FakeForegroundSource()
    monitor, queue, _ = _monitor(clock, source)

    source.switch_to("code.exe")
    for _ in range(31):
        monitor.tick()
        clock.advance(seconds=1)

    sessions = _sessions(queue)
    assert len(sessions) == 3, "每 10 秒应落一段"
    assert {session.app_id for session in sessions} == {1}
    assert sum(session.duration_ms for session in sessions) == 30_000


def test_sub_second_sessions_are_dropped_but_keys_are_not():
    """快速 Alt+Tab 穿过若干窗口只产生无统计价值的碎片；丢的是**会话**不是**按键**。"""
    clock = FakeClock()
    source = FakeForegroundSource()
    monitor, queue, coordinator = _monitor(clock, source)

    for app in ("code.exe", "chrome.exe", "code.exe", "chrome.exe"):
        source.switch_to(app)
        monitor.tick()
        clock.advance(ms=200)

    assert _sessions(queue) == []
    assert monitor.stats.dropped_short == 3
    # 归因状态照常更新——期间的按键仍然归给当时的前台应用。
    assert coordinator.current_app_id == 2


def test_minimum_session_boundary_is_inclusive_of_one_second():
    clock = FakeClock()
    source = FakeForegroundSource()
    monitor, queue, _ = _monitor(clock, source)

    source.switch_to("code.exe")
    monitor.tick()
    clock.advance(ms=MIN_SESSION_MS)
    source.switch_to("chrome.exe")
    monitor.tick()

    assert [session.duration_ms for session in _sessions(queue)] == [MIN_SESSION_MS]


def test_no_foreground_window_ends_the_session_and_clears_attribution():
    """锁屏、系统外壳、探测失败都走这条路：按键归到未知，而不是继续算给上一个应用。"""
    clock = FakeClock()
    source = FakeForegroundSource()
    monitor, queue, coordinator = _monitor(clock, source)

    source.switch_to("code.exe")
    monitor.tick()
    clock.advance(seconds=3)
    source.clear()
    monitor.tick()

    assert [session.app_id for session in _sessions(queue)] == [1]
    assert coordinator.current_app_id == 0


def test_excluded_app_produces_no_session_but_keys_still_land_on_the_sentinel():
    """用户排除列表：不记会话，期间按键归 app_id = 0 而**不丢弃**（04 文档 §2.2）。

    丢弃会让"各应用按键之和 < 总按键数"，而这个差额用户无法解释——他只会认为
    统计坏了。
    """
    clock = FakeClock()
    source = FakeForegroundSource()
    monitor, queue, coordinator = _monitor(
        clock, source, excluded=frozenset({"secret.exe"})
    )

    source.switch_to("secret.exe")
    monitor.tick()
    clock.advance(seconds=30)
    monitor.tick()

    assert _sessions(queue) == []
    assert coordinator.current_app_id == 0
    assert coordinator.attribution().app_id == 0


def test_idle_truncates_the_session_back_to_the_last_input():
    """会话结束于"最后一次输入 + 阈值"，不是发现空闲的时刻。

    不回溯的话"挂机 8 小时"会被完整记成 8 小时使用——这是 TimeLens 现状里最大的
    单项误差来源。
    """
    clock = FakeClock()
    source = FakeForegroundSource()
    idle = FakeIdleSource()
    monitor, queue, coordinator = _monitor(
        clock, source, idle_source=idle, idle_threshold_seconds=1800.0
    )

    source.switch_to("code.exe")
    monitor.tick()
    start_ns = clock.time_ns()

    # 用户走开：8 小时后回来。空闲检查在活跃期是 60 秒一次，所以推 8 小时再 tick。
    clock.advance(seconds=8 * 3600)
    idle.idle = 8 * 3600 - 60  # 最后一次输入发生在会话开始后 60 秒
    monitor.tick()

    sessions = _sessions(queue)
    assert len(sessions) == 1
    session = sessions[0]
    assert session.idle_trimmed is True
    # 结束时刻 = 现在 -（空闲时长 - 阈值），即"最后一次输入 + 30 分钟"。
    expected_end = clock.time_ns() - int((idle.idle - 1800.0) * 1e9)
    assert session.end_ts_ns == expected_end
    assert session.duration_ms == (expected_end - start_ns) // 1_000_000
    assert coordinator.current_app_id == 0
    assert monitor.stats.idle_truncations == 1


def test_returning_from_idle_starts_a_fresh_session():
    clock = FakeClock()
    source = FakeForegroundSource()
    idle = FakeIdleSource()
    monitor, queue, coordinator = _monitor(
        clock, source, idle_source=idle, idle_threshold_seconds=1800.0
    )

    source.switch_to("code.exe")
    monitor.tick()
    clock.advance(seconds=3600)
    idle.idle = 3600.0
    monitor.tick()
    _sessions(queue)  # 清掉被截断的那一段

    # 回来了：空闲期按轮询间隔（1 秒）复查，因此下一 tick 就能发现。
    idle.idle = 0.0
    clock.advance(seconds=1)
    monitor.tick()
    clock.advance(seconds=5)
    source.switch_to("chrome.exe")
    monitor.tick()

    sessions = _sessions(queue)
    assert [session.app_id for session in sessions] == [1]
    assert sessions[0].duration_ms == 5000
    assert coordinator.idle is False


def test_idle_recheck_during_idle_uses_the_poll_interval_not_sixty_seconds():
    """旧实现空闲后 60 秒才复查，用户回来最多 60 秒不产生会话——实打实的时长丢失。"""
    clock = FakeClock()
    source = FakeForegroundSource()
    idle = FakeIdleSource(idle=2000.0)
    monitor, _queue, _coordinator = _monitor(
        clock, source, idle_source=idle, idle_threshold_seconds=1800.0
    )
    source.switch_to("code.exe")
    monitor.tick()
    assert monitor.snapshot()["idle"] is True

    idle.idle = 0.0
    clock.advance(seconds=1)
    monitor.tick()
    assert monitor.snapshot()["idle"] is False, "空闲期应按轮询间隔复查"


def test_wall_clock_going_backwards_never_yields_a_negative_duration():
    """段长最多 10 秒，因此一次跳变最多影响一段——但那一段也不许是负数。"""
    clock = FakeClock()
    source = FakeForegroundSource()
    monitor, queue, _ = _monitor(clock, source)

    source.switch_to("code.exe")
    monitor.tick()
    clock.set_wall_clock(back_by=timedelta(hours=1))
    source.switch_to("chrome.exe")
    monitor.tick()

    assert all(session.duration_ms >= 0 for session in _sessions(queue))


def test_stop_flushes_the_last_session():
    """否则最后一段（最多 10 秒）会丢，而"退出前那一会儿"恰是用户最容易注意的。"""
    clock = FakeClock()
    source = FakeForegroundSource()
    monitor, queue, coordinator = _monitor(clock, source)

    source.switch_to("code.exe")
    monitor.tick()
    clock.advance(seconds=4)
    monitor.stop()

    assert [session.duration_ms for session in _sessions(queue)] == [4000]
    assert coordinator.current_app_id == 0


def test_paused_monitor_produces_nothing():
    clock = FakeClock()
    source = FakeForegroundSource()
    monitor, queue, _ = _monitor(clock, source, paused=True)
    source.switch_to("code.exe")
    for _ in range(20):
        monitor.tick()
        clock.advance(seconds=1)
    assert _sessions(queue) == []
    assert source.calls == 0, "暂停时连探测都不该做"


def test_a_probe_failure_does_not_kill_the_polling_loop():
    """一次探测异常绝不能让常驻线程死掉——死了以后屏幕时间就永久停止了。

    这里走的是 ``_loop`` 的异常兜底路径（``tick()`` 本身允许抛），因此断言的是
    "线程还活着、下一轮照常探测"。
    """
    clock = FakeClock()
    source = FakeForegroundSource()
    monitor, _queue, _ = _monitor(clock, source)
    source.switch_to("code.exe")
    monitor.tick()
    clock.advance(seconds=2)

    source.raise_next = True
    monitor.start()  # 真起线程：让 _loop 的 try/except 接住这一次失败
    monitor.stop()

    clock.advance(seconds=2)
    monitor.tick()
    assert monitor.stats.polls >= 3
    assert monitor.running is False


def test_window_title_is_carried_on_the_session_only():
    """标题只在会话上，且默认适配器根本不返回它（08 文档 §2.1）。"""
    clock = FakeClock()
    source = FakeForegroundSource()
    monitor, queue, _ = _monitor(clock, source)

    source.switch_to("code.exe", title="秘密项目.py")
    monitor.tick()
    clock.advance(seconds=3)
    monitor.stop()

    assert _sessions(queue)[0].window_title == "秘密项目.py"


def test_snapshot_reports_current_app_and_counters():
    clock = FakeClock()
    source = FakeForegroundSource()
    monitor, _queue, _ = _monitor(clock, source)
    source.switch_to("chrome.exe")
    monitor.tick()

    snapshot = monitor.snapshot()
    assert snapshot["current_app_id"] == 2
    assert snapshot["polls"] == 1
    assert snapshot["switches"] == 1
    assert snapshot["paused"] is False
    # 后端名是**机制**而不是实现类名：类名会把 WindowsForegroundSource 这种带平台名的
    # 字符串送进 /api/v1/status，而前端被禁止按平台字符串分支（05 文档 §7、07 文档 §10）。
    assert snapshot["backend"] == "polling"
    assert "Windows" not in str(snapshot)
