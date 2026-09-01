"""归因中枢（11 文档 §3.3）。

这是**合并的技术核心**：一个内存引用取代了旧方案的"HTTP 调另一个进程 → 区间合并
→ 扫描原始事件表求交"。它只有三十行，但错了会让"应用×键"这个合并的核心产出静默
失真——所以每一条语义都要有断言，包括那条最容易被"优化"掉的：同一应用继续在前台时
**不刷新** ``since``。
"""

from __future__ import annotations

from fakes import FakeClock
from omnisight.adapters.ports import UNKNOWN_APP_ID
from omnisight.capture.coordinator import CaptureCoordinator


def _coordinator(clock: FakeClock, boundary: float = 1.0) -> CaptureCoordinator:
    return CaptureCoordinator(boundary_window_seconds=boundary, monotonic=clock.monotonic)


def test_keys_are_attributed_to_foreground_app():
    clock = FakeClock()
    coordinator = _coordinator(clock)
    coordinator.set_foreground(7)
    assert coordinator.attribution().app_id == 7
    assert coordinator.current_app_id == 7


def test_attribution_right_after_switch_is_marked_boundary():
    """切换后一个轮询周期内的按键可能属于任一方，必须标出来。"""
    clock = FakeClock()
    coordinator = _coordinator(clock)
    coordinator.set_foreground(7)
    assert coordinator.attribution().confidence == "boundary"
    clock.advance(seconds=2)
    assert coordinator.attribution().confidence == "high"


def test_staying_in_the_same_app_does_not_refresh_the_boundary_window():
    """前台监控每秒都会调 ``set_foreground``。

    如果同一个 app_id 也刷新时间戳，那么**每一次按键都会被标成 boundary**——
    归因准确率判据（`boundary` 占比 < 2%）会直接失败，而数据看起来一切正常。
    """
    clock = FakeClock()
    coordinator = _coordinator(clock)
    coordinator.set_foreground(7)
    clock.advance(seconds=5)
    for _ in range(5):
        coordinator.set_foreground(7)  # 轮询线程的常态
        clock.advance(seconds=1)
    assert coordinator.attribution().confidence == "high"


def test_switching_away_and_back_restarts_the_boundary_window():
    clock = FakeClock()
    coordinator = _coordinator(clock)
    coordinator.set_foreground(7)
    clock.advance(seconds=5)
    coordinator.set_foreground(9)
    assert coordinator.attribution() == coordinator.attribution()
    assert coordinator.attribution().app_id == 9
    assert coordinator.attribution().confidence == "boundary"


def test_no_foreground_yields_unknown_sentinel_not_none():
    """哨兵 0 而不是 ``None``：聚合表的主键列隐含 NOT NULL（PROGRESS 偏离 3）。"""
    coordinator = _coordinator(FakeClock())
    attribution = coordinator.attribution()
    assert attribution.app_id == UNKNOWN_APP_ID
    assert attribution.confidence == "unknown"
    assert attribution.known is False


def test_zero_and_none_both_mean_no_foreground():
    clock = FakeClock()
    coordinator = _coordinator(clock)
    coordinator.set_foreground(7)
    coordinator.set_foreground(None)
    assert coordinator.attribution().app_id == UNKNOWN_APP_ID
    coordinator.set_foreground(7)
    coordinator.set_foreground(0)
    assert coordinator.attribution().app_id == UNKNOWN_APP_ID


def test_clear_forgets_the_current_app():
    """停止采集后的按键不许归给一个已经结束的会话。"""
    clock = FakeClock()
    coordinator = _coordinator(clock)
    coordinator.set_foreground(7)
    coordinator.set_idle(True)
    coordinator.clear()
    assert coordinator.attribution().app_id == UNKNOWN_APP_ID
    assert coordinator.idle is False


def test_idle_flag_is_advisory_only():
    """空闲标志只让前台监控知道该截断会话——按键本身就是输入，不会因空闲被丢。"""
    clock = FakeClock()
    coordinator = _coordinator(clock)
    coordinator.set_foreground(7)
    coordinator.set_idle(True)
    clock.advance(seconds=2)
    assert coordinator.idle is True
    assert coordinator.attribution().app_id == 7


def test_confidence_codes_are_stable():
    """落盘的是整数编码，改动它等于让历史数据的 confidence 列换了含义。"""
    from omnisight.capture.models import CONFIDENCE_CODES, CONFIDENCE_NAMES

    assert CONFIDENCE_CODES == {"unknown": 0, "boundary": 1, "high": 2}
    assert CONFIDENCE_NAMES[2] == "high"
