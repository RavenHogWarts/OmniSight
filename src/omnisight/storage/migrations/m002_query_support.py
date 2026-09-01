"""M2 查询层所需的列与表（schema v1 → v2）。

M2 把 05 文档定义的接口全部接上真实数据，过程中发现四处**存储层缺口**——它们都不是
"想多存点东西"，而是没有它们某个已承诺的接口字段只能返回假数据：

1. ``usage_session.end_reason`` / ``visit_start_ts_ns``
   心跳落盘每 10 秒把一次使用切成一段（04 文档 §2.3）。因此 ``session_count`` 数的是
   **段数**而不是"用了几次"，``MAX(duration_ms)`` 恒等于心跳间隔而不是"最长一次使用"，
   ``/insights/rhythm`` 的 ``switch_count``（注意力碎片化）更是差两个数量级。
   04 文档原文说"代价是一天会产生较多短会话行——查询侧不受影响"，这句话不成立。
2. ``agg_app_day.longest_visit_ms``
   有了访问起点，"最长一次访问"可以在写入侧顺手维护，查询期零成本。
3. ``agg_press_minute`` / ``agg_press_hour``
   ``kpm_peak`` / ``peak_kpm.at`` / ``active_hours.first`` 都要求分钟精度，而最细的
   已有聚合是小时——用小时均值充当"峰值"是在编数据。``agg_press_hour`` 则是基准跑出来
   的：``agg_key_hour`` 里同一事实按键拆开存，"我一般几点在敲键盘"因此要扫三年 2.9M 行
   （实测 200ms，是 M2 基准里最大的单项开销）；键无关的小时表只有 26k 行。
4. ``app_icon``
   图标解析结果要持久化（04 文档 §6"改动一"），否则每次重启都要重走一遍注册表遍历。

**不回填历史数据。** v1 期间没有记录访问起点，无法事后推断哪些段属于同一次访问；
硬猜会把"最长使用 3 小时"这类结论建立在编造的数据上。v1 的日子里
``longest_visit_ms`` 保持 0、``session_count`` 仍是段数口径，这一点在
``/api/v1/*`` 的 ``coverage`` 之外无法表达，因此记在这里与 PROGRESS 里。
"""

from __future__ import annotations

import logging
from sqlite3 import Connection

from .. import schema

logger = logging.getLogger(__name__)

#: (表, 列, 列定义)。逐列判断而不是整表重建：``ALTER TABLE ADD COLUMN`` 对
#: ``WITHOUT ROWID`` 表同样可用，而重建一张有数据的聚合表要复制全部行。
ADDED_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("usage_session", "end_reason", "TEXT NOT NULL DEFAULT 'switch'"),
    ("usage_session", "visit_start_ts_ns", "INTEGER NOT NULL DEFAULT 0"),
    *(
        ("agg_app_day", name, decl)
        for name, decl in schema.AGG_APP_DAY_EXTRA_COLUMNS
    ),
)

ADDED_TABLES: tuple[str, ...] = (
    schema.AGG_PRESS_HOUR_DDL,
    schema.AGG_PRESS_MINUTE_DDL,
    schema.APP_ICON_DDL,
)


def _columns(conn: Connection, table: str) -> frozenset[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return frozenset(row[1] for row in rows)


def up(conn: Connection) -> None:
    """幂等：全新库由 m001 直接建成 v2 结构，这里会发现列与表都已存在并跳过。"""
    for table, column, decl in ADDED_COLUMNS:
        if column in _columns(conn, table):
            continue
        logger.info("迁移 002：为 %s 添加列 %s", table, column)
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
    for ddl in ADDED_TABLES:
        conn.execute(ddl)
    # 索引在 schema.INDEXES 里已是 IF NOT EXISTS，重放一遍即可补上新增的那条。
    for ddl in schema.INDEXES:
        conn.execute(ddl)


__all__ = ["ADDED_COLUMNS", "ADDED_TABLES", "up"]
