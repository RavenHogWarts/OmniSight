r"""``raw_key_events_YYYY_MM`` 按月分表管理（03 文档 §2.5）。

分表的收益是**归档变成 ``DROP TABLE``**：单表三年后有六千万行，删掉老数据要
``DELETE`` 大范围再 ``VACUUM``（重写整库、占用等量临时空间）；分表下代价接近零，
配合 ``auto_vacuum=INCREMENTAL`` 还能真正把磁盘还给系统。

**这是全代码库唯一的动态 SQL 构造点**——表名无法参数化。因此这里的校验比"看着够用"
要严一档：``schema.raw_table_name`` 用正则兜底表名形态，本文件再先校验**月份本身
合法**（``2026-13`` 与 ``9999-99`` 会通过前者的 ``\d{4}_\d{2}``，但它们是 bug 而不是
攻击，同样必须拒绝，否则库里会静默多出一张没人会去查的垃圾表）。
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, tzinfo
from sqlite3 import Connection

from . import schema

logger = logging.getLogger(__name__)

#: 严格的月份形态：四位年 + ``-`` + ``01``~``12``。
MONTH_RE = re.compile(r"^\d{4}-(?:0[1-9]|1[0-2])$")

INSERT_SQL = """
INSERT INTO {table} (
    key_id, app_id, down_ts_ns, up_ts_ns, duration_ms,
    native_code, native_code2, hid_usage, confidence
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def validate_month(month: str) -> str:
    if not isinstance(month, str) or not MONTH_RE.fullmatch(month):
        raise ValueError(f"月份必须形如 YYYY-MM（01~12），收到 {month!r}")
    return month


def raw_table(month: str) -> str:
    """``"2026-08"`` → ``"raw_key_events_2026_08"``。两道校验，任何异常输入直接拒绝。"""
    return schema.raw_table_name(validate_month(month))


def month_of(ts_ns: int, tz: tzinfo | None = None) -> str:
    """纳秒时间戳 → 本地月份桶。

    用**本地**时区而非 UTC：分表要与 ``day_bucket`` 的语义一致，否则每月 1 日凌晨的
    事件会落到上个月的表里，而它的日期桶写的是本月（03 文档 §3.1）。
    """
    moment = datetime.fromtimestamp(ts_ns / 1_000_000_000, tz=tz)
    return f"{moment.year:04d}-{moment.month:02d}"


class Partitions:
    """记住哪些月表已经建好，避免每批都执行一次 ``CREATE TABLE IF NOT EXISTS``。

    缓存只在**本进程内**有效，且只做正向断言（"我建过"）。这样即使别的进程建了表，
    这里最多多执行一次幂等 DDL，不会出错。
    """

    __slots__ = ("_ensured",)

    def __init__(self) -> None:
        self._ensured: set[str] = set()

    def ensure(self, conn: Connection, month: str) -> str:
        """确保该月的表与索引存在，返回表名。幂等。"""
        table = raw_table(month)
        if table in self._ensured:
            return table
        for statement in schema.raw_partition_ddl(month):
            conn.execute(statement)
        self._ensured.add(table)
        logger.debug("分表已就绪 %s", table)
        return table

    def knows(self, month: str) -> bool:
        return raw_table(month) in self._ensured

    def forget(self, month: str) -> None:
        """归档删表后调用，让缓存不再声称它存在。"""
        self._ensured.discard(raw_table(month))

    def reset(self) -> None:
        """清空缓存。建表事务失败后必须调用。

        缓存声称的是「这张表已经建好并提交了」。如果建表语句执行了但事务最终回滚，
        缓存就会说谎，而且是永久说谎——之后每次插入都报 no such table，直到进程重启。
        这个坑真实踩过一次，因此建表现在走独立事务，且失败即清缓存。
        """
        self._ensured.clear()

    @staticmethod
    def existing_months(conn: Connection) -> list[str]:
        """库里已有的月份，升序。供聚合重算、归档与一致性校验使用。"""
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name LIKE 'raw_key_events_%' ORDER BY name"
        )
        months: list[str] = []
        for row in rows:
            name = row[0]
            if not schema.RAW_TABLE_RE.fullmatch(name):
                continue
            suffix = name.removeprefix("raw_key_events_")
            months.append(suffix.replace("_", "-", 1))
        return months

    @staticmethod
    def insert_sql(table: str) -> str:
        """构造插入语句。只接受**已经**经过 :func:`raw_table` 的表名。"""
        if not schema.RAW_TABLE_RE.fullmatch(table):
            raise ValueError(f"拒绝不安全的表名：{table!r}")
        return INSERT_SQL.format(table=table)


__all__ = ["MONTH_RE", "Partitions", "month_of", "raw_table", "validate_month"]
