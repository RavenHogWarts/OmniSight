r"""按月分表与表名校验（11 文档 §4.3 的最后一组）。

``raw_key_events_YYYY_MM`` 是**全代码库唯一的动态 SQL 构造点**——表名无法参数化。
因此它有两道独立的校验（月份形态 + 表名正则），本文件把两道都撬一遍。

注意这里的输入不只有注入形态。``2026-13`` 与 ``9999-99`` 会通过 ``\d{4}_\d{2}``
这种宽松的表名正则，它们是 bug 而不是攻击，但同样必须拒绝：否则库里会静默多出一张
没人会去查的垃圾表，而"某个月的数据不见了"是唯一症状。
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from omnisight.storage import schema
from omnisight.storage.partitions import Partitions, month_of, raw_table, validate_month


@pytest.mark.parametrize(
    "month",
    [
        "2026-08'; DROP TABLE app; --",
        "../etc",
        "2026_08",  # 下划线是表名的形态，不是月份的
        "9999-99",
        "2026-13",
        "2026-00",
        "2026-8",  # 缺前导零
        "26-08",
        "",
        "2026-08 ",
        "2026-08\n",
        "２０２６-０８",  # 全角数字
    ],
)
def test_raw_table_name_rejects_anything_but_yyyy_mm(month: str):
    with pytest.raises(ValueError):
        raw_table(month)


@pytest.mark.parametrize("month", [None, 202608, 3.14, b"2026-08", ["2026-08"]])
def test_raw_table_name_rejects_non_strings(month):
    with pytest.raises(ValueError):
        raw_table(month)


@pytest.mark.parametrize(
    ("month", "expected"),
    [
        ("2026-01", "raw_key_events_2026_01"),
        ("2026-08", "raw_key_events_2026_08"),
        ("2026-12", "raw_key_events_2026_12"),
    ],
)
def test_valid_months_produce_the_documented_table_name(month: str, expected: str):
    assert raw_table(month) == expected
    assert validate_month(month) == month


def test_insert_sql_refuses_a_table_name_that_did_not_come_from_raw_table():
    """第二道闸：即使调用方绕过了 :func:`raw_table`，拼 SQL 时也要再验一次。"""
    with pytest.raises(ValueError):
        Partitions.insert_sql("raw_key_events_2026_08; DROP TABLE app")
    with pytest.raises(ValueError):
        Partitions.insert_sql("app")
    assert "raw_key_events_2026_08" in Partitions.insert_sql("raw_key_events_2026_08")


def test_month_of_uses_local_time_not_utc():
    """分表必须与 ``day_bucket`` 同一个时区。

    否则每月 1 日凌晨的事件会落到上个月的表里，而它的 ``day_bucket`` 写的是本月——
    "按原始事件重算这一天"就会少掉几小时（03 文档 §3.1）。
    """
    # UTC 时间 2026-07-31 20:00 在东八区已经是 8 月 1 日 04:00。
    moment = datetime(2026, 7, 31, 20, 0, tzinfo=UTC)
    ts_ns = int(moment.timestamp() * 1_000_000_000)
    assert month_of(ts_ns, ZoneInfo("Asia/Shanghai")) == "2026-08"
    assert month_of(ts_ns, UTC) == "2026-07"


def test_ensure_is_idempotent_and_cached(database):
    partitions = Partitions()
    with database.transaction() as conn:
        first = partitions.ensure(conn, "2026-08")
        second = partitions.ensure(conn, "2026-08")
    assert first == second == "raw_key_events_2026_08"
    assert partitions.knows("2026-08") is True
    assert partitions.knows("2026-09") is False


def test_reset_clears_the_cache_after_a_rolled_back_ddl(database):
    """缓存说谎的后果是永久的：之后每次插入都报 ``no such table`` 直到进程重启。

    这个坑真实踩过一次——建表语句执行在数据事务里，事务回滚把表撤掉了，缓存却仍然
    声称"建过了"。因此建表现在走独立事务，且失败即清缓存。
    """
    partitions = Partitions()
    with database.transaction() as conn:
        partitions.ensure(conn, "2026-08")
    assert partitions.knows("2026-08") is True
    partitions.reset()
    assert partitions.knows("2026-08") is False
    # 清缓存后重新 ensure 必须仍然成功（DDL 是幂等的）。
    with database.transaction() as conn:
        assert partitions.ensure(conn, "2026-08") == "raw_key_events_2026_08"


def test_forget_is_for_archived_partitions(database):
    partitions = Partitions()
    with database.transaction() as conn:
        partitions.ensure(conn, "2026-08")
    partitions.forget("2026-08")
    assert partitions.knows("2026-08") is False


def test_existing_months_lists_only_real_partitions(database):
    partitions = Partitions()
    with database.transaction() as conn:
        for month in ("2026-08", "2026-09", "2025-12"):
            partitions.ensure(conn, month)
        # 一张形似但不合规的表：不该被当成分表。
        conn.execute("CREATE TABLE raw_key_events_backup (id INTEGER)")

    months = Partitions.existing_months(database.connect())
    assert months == ["2025-12", "2026-08", "2026-09"]


def test_partition_ddl_creates_the_indexes_the_queries_need(database):
    """没有索引的分表在"回退原始事件"的路径上会退化成全表扫描。"""
    partitions = Partitions()
    with database.transaction() as conn:
        table = partitions.ensure(conn, "2026-08")
    indexes = [
        row[0]
        for row in database.connect().execute(
            "SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = ?",
            (table,),
        )
    ]
    assert indexes, f"{table} 没有任何索引"


def test_raw_table_regex_is_anchored():
    """未加锚定的正则会放过 ``x_raw_key_events_2026_08_y`` 这类名字。"""
    assert schema.RAW_TABLE_RE.fullmatch("raw_key_events_2026_08")
    assert not schema.RAW_TABLE_RE.fullmatch("x_raw_key_events_2026_08")
    assert not schema.RAW_TABLE_RE.fullmatch("raw_key_events_2026_08_y")
