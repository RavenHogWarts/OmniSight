"""分表表名白名单（11 文档 §4.3）。

``raw_key_events_YYYY_MM`` 是全代码库唯一的动态 SQL 构造点——表名无法参数化，
只能靠正则兜底。因此它必须有专门的测试。
"""

from __future__ import annotations

import pytest

from omnisight.storage import schema


def test_valid_month_maps_to_partition_name():
    assert schema.raw_table_name("2026-08") == "raw_key_events_2026_08"


@pytest.mark.parametrize(
    "month",
    [
        "2026-08'; DROP TABLE app; --",
        "../etc",
        "2026_08_extra",
        "9999-99-99",
        "",
        "2026-8",
        "raw_key_events_2026_08",
    ],
)
def test_anything_but_yyyy_mm_is_rejected(month: str):
    with pytest.raises(ValueError):
        schema.raw_table_name(month)


def test_partition_ddl_indexes_reference_the_same_table():
    statements = schema.raw_partition_ddl("2026-08")
    assert len(statements) == 4
    assert all("raw_key_events_2026_08" in stmt for stmt in statements)


def test_expected_tables_matches_ddl_count():
    """两处清单必须同步，否则启动自检会漏表。"""
    assert len(schema.EXPECTED_TABLES) == len(schema.TABLES)
