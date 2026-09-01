"""周期计算（11 文档 §3.2、05 文档 §1.3）。

TimeLens 的"周"是"选中日往前 6 天"，KeyTrace 的是 ISO 周一起。合并后统一为**自然周**，
起始日可配。这个改动会让老用户看到的数字变化，因此必须被测试钉死——它是一次有意的语义
变更，不是可以被后来的重构悄悄改回去的实现细节。
"""

from __future__ import annotations

from datetime import date

import pytest

from omnisight.services.period import (
    MAX_CUSTOM_SPAN_DAYS,
    Period,
    PeriodRequest,
    buckets,
    parse_date,
    previous,
    resolve,
)

TODAY = date(2026, 9, 2)


def _resolve(range_name: str, anchor: str | None = None, **kwargs) -> Period:
    return resolve(
        PeriodRequest(range_name, anchor=date.fromisoformat(anchor) if anchor else None),
        today=kwargs.pop("today", TODAY),
        **kwargs,
    )


@pytest.mark.parametrize(
    ("range_name", "anchor", "start", "end"),
    [
        ("week", "2026-08-31", "2026-08-31", "2026-09-06"),  # 周一
        ("week", "2026-09-06", "2026-08-31", "2026-09-06"),  # 周日 → 同一周
        ("month", "2026-02-15", "2026-02-01", "2026-02-28"),
        ("month", "2028-02-15", "2028-02-01", "2028-02-29"),  # 闰年
        ("month", "2026-12-09", "2026-12-01", "2026-12-31"),  # 年末不越界
        ("year", "2026-06-01", "2026-01-01", "2026-12-31"),
        ("day", "2026-09-02", "2026-09-02", "2026-09-02"),
    ],
)
def test_period_bounds(range_name: str, anchor: str, start: str, end: str):
    period = _resolve(range_name, anchor, today=date(2030, 1, 1))
    assert (period.start.isoformat(), period.end.isoformat()) == (start, end)


@pytest.mark.parametrize(
    ("week_starts_on", "start", "end"),
    [(0, "2026-08-31", "2026-09-06"), (6, "2026-08-30", "2026-09-05")],
)
def test_week_start_is_configurable(week_starts_on: int, start: str, end: str):
    """``ui.week_starts_on`` 是配置项而不是常量：周日起周的地区不该看到错位的一周。"""
    period = _resolve("week", "2026-09-02", week_starts_on=week_starts_on, today=date(2030, 1, 1))
    assert (period.start.isoformat(), period.end.isoformat()) == (start, end)


def test_future_end_is_truncated_but_natural_end_is_kept():
    """本周还没过完时，查询要用截断后的结束日，而 UI 仍要显示自然的一周。

    两个字段都存在是刻意的：只留截断值，日均值的分母会变成"到今天为止的天数"（对），
    但"本周"标签会写成"8月31日–9月2日"（错）。
    """
    period = _resolve("week", "2026-09-02")
    assert period.end == date(2026, 9, 6)
    assert period.truncated_end == TODAY
    assert period.days == 3
    assert period.is_current is True


def test_fully_future_period_collapses_instead_of_erroring():
    """用户点"下一周"翻过头是正常操作，不是错误输入。"""
    period = _resolve("week", "2027-01-04")
    assert period.days == 1
    assert period.truncated_end == period.start
    assert period.is_current is False


def test_total_starts_at_the_first_day_with_data():
    period = resolve(
        PeriodRequest("total"),
        today=TODAY,
        data_range=(date(2025, 12, 15), date(2026, 9, 2)),
    )
    assert period.start == date(2025, 12, 15)
    assert period.truncated_end == TODAY
    assert period.granularity == "year"


def test_total_on_an_empty_database_is_today_not_an_error():
    """空库必须返回结构完整的空数据（11 文档 §4.3）。"""
    period = resolve(PeriodRequest("total"), today=TODAY, data_range=(None, None))
    assert period.start == period.truncated_end == TODAY
    assert period.days == 1


@pytest.mark.parametrize(
    ("range_name", "anchor", "previous_start", "previous_end"),
    [
        ("day", "2026-09-02", "2026-09-01", "2026-09-01"),
        ("week", "2026-09-02", "2026-08-24", "2026-08-30"),
        ("month", "2026-03-15", "2026-02-01", "2026-02-28"),  # 上一月长度不同
        ("year", "2026-06-01", "2025-01-01", "2025-12-31"),
    ],
)
def test_previous_period_has_the_same_grain(
    range_name: str, anchor: str, previous_start: str, previous_end: str
):
    """同比必须同粒度、同性质。月不能用"往前 30 天"，否则 2 月永远显得少。"""
    period = _resolve(range_name, anchor, today=date(2030, 1, 1))
    earlier = previous(period, today=date(2030, 1, 1))
    assert earlier is not None
    assert (earlier.start.isoformat(), earlier.end.isoformat()) == (previous_start, previous_end)


def test_total_has_no_previous_period():
    period = resolve(PeriodRequest("total"), today=TODAY, data_range=(date(2025, 1, 1), TODAY))
    assert previous(period, today=TODAY) is None


def test_previous_custom_period_is_the_adjacent_window_of_equal_length():
    period = resolve(
        PeriodRequest("custom", start=date(2026, 8, 10), end=date(2026, 8, 19)),
        today=TODAY,
    )
    earlier = previous(period, today=TODAY)
    assert earlier is not None
    assert (earlier.start, earlier.end) == (date(2026, 7, 31), date(2026, 8, 9))
    assert earlier.days == period.days == 10


@pytest.mark.parametrize(
    ("range_name", "anchor", "count", "first", "last"),
    [
        ("day", "2026-09-02", 24, "00", "23"),
        ("month", "2026-09-02", 2, "2026-09-01", "2026-09-02"),
        ("year", "2026-09-02", 9, "2026-01", "2026-09"),
    ],
)
def test_buckets_include_empty_slots(
    range_name: str, anchor: str, count: int, first: str, last: str
):
    """缺口由后端补齐：前端拿到不连续的桶只能自己猜"是没数据还是没这一天"。"""
    series = buckets(_resolve(range_name, anchor))
    assert len(series) == count
    assert series[0][0] == first
    assert series[-1][0] == last


@pytest.mark.parametrize("bad", ["20260831", "2026-W35-1", "2026-13-01", "2026-02-30", "", "今天"])
def test_parse_date_accepts_only_iso_dates(bad: str):
    """``date.fromisoformat`` 从 3.11 起还吃 ``20260831`` 与周日期，这里必须拒绝。

    放宽会让 ``?date=2026W351`` 这种输入静默解析成某个别的日期，用户看着图表以为自己
    查的是另一天——比报错糟得多（05 文档 §1.5）。
    """
    with pytest.raises(ValueError):
        parse_date(bad)


def test_custom_span_cap_matches_the_retention_ceiling():
    """自定义区间的上限与三年留存对齐：允许查一个查不到数据的区间没有意义。"""
    assert MAX_CUSTOM_SPAN_DAYS == 1096
