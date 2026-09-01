"""跨小时 / 跨日 / 夏令时的会话切片（03 文档 §3.3；11 文档 §3.4）。

切片放在**写入侧只做一次**，因此查询"某日总时长"可以直接读 ``agg_app_day``，不必
``SUM(usage_session.duration_ms) WHERE day_bucket = ?``（后者会把跨日会话整段算给
起始日）。这也意味着切片错了会同时污染日/月/年/小时四张表，且不可回滚——聚合表是
累加的。

DST 用例对 ``Asia/Shanghai`` 是空转（中国不用夏令时），但配置允许任意时区，而这类
bug 只在切换当天出现、事后无法复现。因此这里用 ``America/New_York`` 固定住。
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from omnisight.storage.writer import day_bucket, hour_of, split_by_hour

SHANGHAI = ZoneInfo("Asia/Shanghai")
NEW_YORK = ZoneInfo("America/New_York")


def _ns(year, month, day, hour=0, minute=0, second=0, *, tz=UTC) -> int:
    return int(datetime(year, month, day, hour, minute, second, tzinfo=tz).timestamp() * 1e9)


def test_a_session_inside_one_hour_is_a_single_slice():
    start = _ns(2026, 8, 31, 10, 5, tz=SHANGHAI)
    end = _ns(2026, 8, 31, 10, 35, tz=SHANGHAI)
    assert split_by_hour(start, end, SHANGHAI) == [("2026-08-31", 10, 30 * 60 * 1000)]


def test_a_session_crossing_an_hour_is_split_at_the_boundary():
    start = _ns(2026, 8, 31, 10, 50, tz=SHANGHAI)
    end = _ns(2026, 8, 31, 11, 20, tz=SHANGHAI)
    assert split_by_hour(start, end, SHANGHAI) == [
        ("2026-08-31", 10, 10 * 60 * 1000),
        ("2026-08-31", 11, 20 * 60 * 1000),
    ]


def test_a_session_crossing_midnight_is_split_across_two_days():
    """否则"昨天用了 6 小时"里会含着今天凌晨的时间（03 文档 §3.3 点明的易错点）。"""
    start = _ns(2026, 8, 31, 23, 40, tz=SHANGHAI)
    end = _ns(2026, 9, 1, 0, 20, tz=SHANGHAI)
    slices = split_by_hour(start, end, SHANGHAI)
    assert slices == [
        ("2026-08-31", 23, 20 * 60 * 1000),
        ("2026-09-01", 0, 20 * 60 * 1000),
    ]


def test_empty_and_inverted_ranges_produce_no_slices():
    start = _ns(2026, 8, 31, 10, 0, tz=SHANGHAI)
    assert split_by_hour(start, start, SHANGHAI) == []
    assert split_by_hour(start, start - 1000, SHANGHAI) == []


@pytest.mark.parametrize("hours", [1, 5, 26, 49])
def test_total_duration_is_conserved_exactly(hours: int):
    """每片各自整除会累积出几毫秒的差额，让"日之和 != 总计"。

    余数交给最后一片，各级聚合之间才精确一致。这里刻意用一个不能被整除的起点。
    """
    start = _ns(2026, 8, 30, 7, 17, 33, tz=SHANGHAI) + 456_789
    end = start + hours * 3_600_000_000_000 + 777_777
    slices = split_by_hour(start, end, SHANGHAI)
    assert sum(duration for _day, _hour, duration in slices) == (end - start) // 1_000_000


def test_no_slice_ever_exceeds_one_hour():
    start = _ns(2026, 8, 30, 0, 0, tz=SHANGHAI)
    end = _ns(2026, 9, 2, 0, 0, tz=SHANGHAI)
    slices = split_by_hour(start, end, SHANGHAI)
    assert all(duration <= 3_600_000 for _day, _hour, duration in slices)
    assert len(slices) == 72


def test_dst_fall_back_day_records_the_repeated_hour_twice():
    """2026-11-01 的美东时区有 25 小时：凌晨 1 点确实过了两遍。

    两遍都累加到同一个 ``(day, 1)`` 桶里——那天的 1 点真的用了两小时。重要的是**时长
    守恒**，而不是"每天固定 24 格"。
    """
    start = _ns(2026, 11, 1, 5, 0, tz=UTC)  # 美东 01:00 EDT
    end = _ns(2026, 11, 1, 7, 30, tz=UTC)  # 美东 02:30 EST
    slices = split_by_hour(start, end, NEW_YORK)

    total = sum(duration for _day, _hour, duration in slices)
    assert total == (end - start) // 1_000_000 == 150 * 60 * 1000
    hours = [hour for _day, hour, _duration in slices]
    assert hours.count(1) == 2, "回拨那天的 1 点出现两次"
    assert {day for day, _hour, _duration in slices} == {"2026-11-01"}


def test_dst_spring_forward_day_simply_has_no_missing_hour():
    """2026-03-08 的美东时区只有 23 小时：02 点不存在，因此一片都不该有。"""
    start = _ns(2026, 3, 8, 6, 30, tz=UTC)  # 美东 01:30 EST
    end = _ns(2026, 3, 8, 8, 30, tz=UTC)  # 美东 04:30 EDT
    slices = split_by_hour(start, end, NEW_YORK)

    total = sum(duration for _day, _hour, duration in slices)
    assert total == (end - start) // 1_000_000 == 120 * 60 * 1000
    hours = [hour for _day, hour, _duration in slices]
    assert 2 not in hours, "前拨那天没有 2 点"
    assert hours == [1, 3, 4]


def test_a_full_dst_day_conserves_duration_in_both_directions():
    for day, expected_hours in ((datetime(2026, 11, 1), 25), (datetime(2026, 3, 8), 23)):
        start = int(day.replace(tzinfo=NEW_YORK).timestamp() * 1e9)
        end = int(day.replace(day=day.day + 1, tzinfo=NEW_YORK).timestamp() * 1e9)
        slices = split_by_hour(start, end, NEW_YORK)
        total = sum(duration for _d, _h, duration in slices)
        assert total == (end - start) // 1_000_000
        assert len(slices) == expected_hours


def test_naive_timezone_falls_back_to_system_local_without_crashing():
    """``tz=None`` 是合法输入（配置没写时区时就是它），不许因此抛异常。"""
    start = _ns(2026, 8, 31, 10, 0, tz=UTC)
    slices = split_by_hour(start, start + 5_400_000_000_000, None)
    assert sum(duration for _d, _h, duration in slices) == 90 * 60 * 1000


def test_day_bucket_and_hour_agree_with_the_slicer():
    """三个函数必须用同一套时区语义，否则原始事件与聚合会对不上账。"""
    ts = _ns(2026, 8, 31, 23, 59, 59, tz=SHANGHAI)
    assert day_bucket(ts, SHANGHAI) == "2026-08-31"
    assert hour_of(ts, SHANGHAI) == 23
    assert split_by_hour(ts, ts + 2_000_000_000, SHANGHAI)[0][0] == "2026-08-31"
