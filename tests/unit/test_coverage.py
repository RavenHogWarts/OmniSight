"""``coverage``：把"测不到"与"没有"分开（03 文档 §2.8、05 文档 §1.4）。

把"测不到"画成"没有"是最容易让用户误判自己行为的一类错误——他上周在 Wayland 上用了
一整天，界面告诉他"应用使用时长 0"。这个模块的三条判定规则各有一条反例支撑，逐条固定。
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from omnisight.services import coverage
from omnisight.storage import capability as capability_table

TZ = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 9, 2, 10, 0, tzinfo=TZ)


def _record(database, day: str, **overrides):
    row = {
        "platform_id": "windows",
        "keyboard_backend": "raw_input",
        "foreground_available": True,
        "titles_recorded": False,
        "key_position_stable": True,
    }
    row.update(overrides)
    with database.transaction() as conn:
        capability_table.upsert(conn, day_bucket=day, now=NOW, **row)


def _summary(database, start: str, end: str, days: int):
    return coverage.summarize(database.connect(), start, end, days)


def test_empty_database_reports_zeros_not_an_error(database):
    summary = _summary(database, "2026-09-01", "2026-09-02", 2)
    assert summary["recorded_days"] == 0
    assert summary["gaps"] == []
    assert summary["total_days"] == 2


def test_a_day_the_program_never_ran_produces_no_gap(database):
    """规则一：只有**明确的否定证据**才产生 gap。

    没有能力快照意味着我们对那天一无所知，不能宣称"该环境不支持应用归因"。差额从
    ``total_days - recorded_days`` 就能看出来，不需要我们编一条 gap。
    """
    _record(database, "2026-09-01")
    summary = _summary(database, "2026-09-01", "2026-09-03", 3)
    assert summary["recorded_days"] == 1
    assert summary["gaps"] == []


def test_missing_foreground_produces_a_gap_with_a_readable_reason(database):
    _record(database, "2026-09-01", foreground_available=False)
    summary = _summary(database, "2026-09-01", "2026-09-01", 1)
    assert summary["foreground_days"] == 0
    gap = summary["gaps"][0]
    assert gap["missing"] == "foreground"
    assert gap["from"] == gap["to"] == "2026-09-01"
    assert "键盘统计仍然正常" in gap["message"]


def test_titles_never_produce_a_gap(database):
    """规则二：窗口标题默认关闭，是隐私选择而不是能力缺失。

    为它每天报一条 gap 会让 ``gaps`` 永远非空，从而彻底失去信噪比。
    """
    _record(database, "2026-09-01", titles_recorded=False)
    summary = _summary(database, "2026-09-01", "2026-09-01", 1)
    assert summary["title_days"] == 0
    assert summary["gaps"] == []


def test_a_day_with_both_positive_and_negative_evidence_produces_no_gap(database):
    """规则三之补充：当天换过后端时那天的数据部分可用，报"整天不支持"是错的。"""
    _record(database, "2026-09-01", foreground_available=False, keyboard_backend="pynput")
    _record(database, "2026-09-01", foreground_available=True)
    summary = _summary(database, "2026-09-01", "2026-09-01", 1)
    assert summary["foreground_days"] == 1
    assert summary["gaps"] == []


def test_adjacent_days_with_the_same_cause_merge_into_one_run(database):
    """规则三：用户该看到"8月28日–8月30日 无应用归因"，而不是三条一模一样的记录。"""
    for day in ("2026-08-28", "2026-08-29", "2026-08-30"):
        _record(database, day, foreground_available=False)
    _record(database, "2026-08-31")
    summary = _summary(database, "2026-08-28", "2026-08-31", 4)
    assert len(summary["gaps"]) == 1
    assert (summary["gaps"][0]["from"], summary["gaps"][0]["to"]) == ("2026-08-28", "2026-08-30")


def test_a_break_in_the_run_starts_a_new_gap(database):
    for day in ("2026-08-28", "2026-08-30"):
        _record(database, day, foreground_available=False)
    _record(database, "2026-08-29")
    summary = _summary(database, "2026-08-28", "2026-08-30", 3)
    assert [(gap["from"], gap["to"]) for gap in summary["gaps"]] == [
        ("2026-08-28", "2026-08-28"),
        ("2026-08-30", "2026-08-30"),
    ]


def test_unstable_key_positions_are_reported_separately(database):
    """左右修饰键合并统计是"数据口径变了"，与"没有数据"不同，必须能分辨。"""
    _record(database, "2026-09-01", key_position_stable=False, keyboard_backend="pynput")
    summary = _summary(database, "2026-09-01", "2026-09-01", 1)
    assert summary["key_position_days"] == 0
    assert summary["gaps"][0]["missing"] == "key_position"
    assert summary["gaps"][0]["reason"] == "pynput"


@pytest.mark.parametrize("total_days", [1, 30, 366])
def test_empty_helper_has_the_same_shape_as_a_real_summary(database, total_days: int):
    """状态接口在采集未装配时用 ``empty()``。形状不同会让前端多一条分支。"""
    real = _summary(database, "2026-09-01", "2026-09-01", total_days)
    assert set(coverage.empty(total_days)) == set(real)
    assert coverage.empty(total_days)["total_days"] == total_days
