"""展示层格式化（05 文档 §1.6）。

**格式化在后端做**，响应里同时带 ``seconds`` 与 ``seconds_formatted``。理由是 TimeLens
与 KeyTrace 各有一份 JS 实现，"7小时33分钟"在两处长得不一样；把它挪到后端并固定住，是
消除两套前端文案差异的唯一办法。这些用例的期望值直接抄自 05 文档的示例。
"""

from __future__ import annotations

import pytest

from omnisight.services.formatting import (
    average,
    delta,
    format_count,
    format_duration,
    percent,
    percentile,
    ratio_per_minute,
)


@pytest.mark.parametrize(
    ("seconds", "text"),
    [
        (0, "0秒"),
        (0.4, "0秒"),
        (1, "1秒"),
        (59, "59秒"),
        (59.6, "59秒"),  # 截断而不是四舍五入，沿用旧实现
        (60, "1分钟"),
        (61, "1分钟"),
        (3599, "59分钟"),
        (3600, "1小时"),
        (3660, "1小时1分钟"),
        (27183.5, "7小时33分钟"),  # 05 文档的示例值
        (86400, "24小时"),
    ],
)
def test_format_duration_matches_the_documented_examples(seconds: float, text: str):
    assert format_duration(seconds) == text


def test_format_duration_never_shows_a_bare_zero_hour():
    """"0小时5分钟"是 TimeLens 现状里出现过的输出，读起来像坏了。"""
    assert format_duration(300) == "5分钟"
    assert not format_duration(300).startswith("0")


def test_kpm_matches_the_documented_example():
    """9120 次 / 9840 秒 ≈ 55.6 次/分钟（05 文档 §5）。"""
    assert ratio_per_minute(9120, 9840 * 1000) == 55.6


@pytest.mark.parametrize("duration_ms", [0, -1])
def test_kpm_of_a_zero_length_period_is_zero_not_infinity(duration_ms: int):
    assert ratio_per_minute(100, duration_ms) == 0


def test_percent_of_an_empty_whole_is_zero():
    """空库的第一屏会走这条路径。除零异常在这里等于首屏 500。"""
    assert percent(0, 0) == 0
    assert percent(5, 0) == 0


def test_percent_rounds_to_one_digit():
    assert percent(1, 3) == 33.3


def test_delta_reports_both_absolute_and_relative_change():
    assert delta(2400, 1200) == {"value": 1200, "percent": 100.0}


def test_delta_against_a_zero_baseline_reports_zero_percent_not_infinity():
    """"比上期增长 ∞%"没有意义。绝对值仍然给出，前端据此显示"新增"。"""
    assert delta(2400, 0) == {"value": 2400, "percent": 0.0}


def test_delta_direction_is_signed_and_carries_no_judgement():
    """屏幕时间下降不一定是好事：方向只由符号表达，配色由 UI 决定（06 文档 §5.1）。"""
    assert delta(1200, 2400)["value"] == -1200


def test_average_and_count_formatting():
    assert average(2400, 3) == 800.0
    assert average(2400, 0) == 0
    assert format_count(9120) == "9,120"


@pytest.mark.parametrize(
    ("values", "fraction", "expected"),
    [
        ([], 0.95, 0.0),
        ([5], 0.95, 5),
        (list(range(1, 101)), 0.95, 95),  # 最近秩：index = round(0.95 × 99) = 94
    ],
)
def test_percentile_is_defined_on_empty_and_single_element_inputs(
    values: list[float], fraction: float, expected: float
):
    """热力图的 ``scale.p95`` 用它。空键盘（新装用户）不能让整张图 500。"""
    assert percentile(values, fraction) == expected
