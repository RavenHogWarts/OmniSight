"""跨维度查询：应用 × 键（02 文档 §2 的 ``repositories/insights.py``）。

这个文件里的每一条查询在合并之前都**无法回答**——它们要么需要按键事件带着 ``app_id``，
要么需要前台时长与按键量在同一个库里。这也是为什么 05 文档把 ``/insights/*`` 称为
"合并后的核心新能力"。

一条铁律仍然生效：**常规查询不扫 ``raw_key_events_*``**（01 文档 §4.1）。本文件只有
一个例外，且它带着显式的单日窗口——见 :meth:`InsightsRepository.app_hourly_presses`。

**修饰键占比的口径**（``/insights/app-keyboard`` 的 ``modifier_percent``）：数的是修饰键
**自身**被按下的次数，不是"按某个键时按住了修饰键"。后者需要和弦信息，而我们既不记录
按键顺序、也不允许常规查询扫原始事件（08 文档 §2）。这个口径必须在 UI 上写明。它由
``app_key_totals`` 的结果在服务层汇总得出，这里不再单独提供查询——同一批数字来自同一次
读取，就不会因为两次查询之间落了一批数据而对不上。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, tzinfo
from sqlite3 import Connection, DatabaseError

from .. import schema
from ..database import Database

logger = logging.getLogger(__name__)


class InsightsRepository:
    __slots__ = ("_db",)

    def __init__(self, db: Database) -> None:
        self._db = db

    def _conn(self) -> Connection:
        return self._db.connect()

    def app_presses(self, start_day: str, end_day: str) -> dict[int, int]:
        """``app_id`` → 周期内按键数。KPM 的分子。

        走 ``agg_app_day.press_count`` 而不是 ``agg_key_app_day``：后者按 (日, 应用, **键**)
        存同一事实，一年要扫 480k 行而这里只需要 4.4k 行（实测 46ms → <1ms）。这个查询在
        ``/usage/period`` / ``/apps`` / ``/overview`` / ``/insights/app-keyboard`` 上都要跑。
        """
        rows = self._conn().execute(
            "SELECT app_id, SUM(press_count) AS press_count FROM agg_app_day "
            "WHERE day_bucket BETWEEN ? AND ? GROUP BY app_id",
            (start_day, end_day),
        )
        return {int(row["app_id"]): int(row["press_count"] or 0) for row in rows}

    def app_presses_all_time(self) -> dict[int, int]:
        rows = self._conn().execute(
            "SELECT app_id, SUM(press_count) AS press_count FROM agg_app_key_total GROUP BY app_id"
        )
        return {int(row["app_id"]): int(row["press_count"] or 0) for row in rows}

    def app_hourly_presses(
        self, day: str, app_id: int, tz: tzinfo | None = None
    ) -> dict[int, int] | None:
        """★ 唯一允许触碰原始事件表的查询：**单个应用、单一天**的按键小时分布。

        ``agg_key_hour`` 没有应用维度，而为"应用 × 键 × 小时"再建一张表的写入代价不划算
        （日活跃应用 10 个 × 60 键 × 16 小时 ≈ 9600 行/天）。01 文档 §4.1 为"应用热力图
        回溯"留了这个例外，条件是**必须有时间窗上限**——这里的上限是一天，且
        ``WHERE app_id = ? AND down_ts_ns >= ? AND down_ts_ns < ?`` 正好走
        ``idx_rke_YYYY_MM_app_down``。

        返回 ``None`` 表示这一天的月表不存在（``store_raw_key_events`` 关闭，或那个月
        没有数据）。调用方据此如实告诉用户"该视图在当前设置下不可用"，而不是画一张
        全 0 的图——后者会让用户以为自己那天在这个应用里没按过键。
        """
        try:
            table = schema.raw_table_name(day[:7])
        except ValueError:  # pragma: no cover - 调用方已校验日期
            return None
        conn = self._conn()
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
        ).fetchone()
        if exists is None:
            return None
        midnight = datetime.fromisoformat(day)
        midnight = midnight.replace(tzinfo=tz) if tz else midnight.astimezone()
        start_ns = int(midnight.timestamp() * 1_000_000_000)
        end_ns = int((midnight + timedelta(days=1)).timestamp() * 1_000_000_000)
        try:
            rows = conn.execute(
                f"SELECT down_ts_ns FROM {table} "
                "WHERE app_id = ? AND down_ts_ns >= ? AND down_ts_ns < ?",
                (app_id, start_ns, end_ns),
            ).fetchall()
        except DatabaseError:  # pragma: no cover
            logger.debug("读取 %s 失败", table, exc_info=True)
            return None
        # 分桶在 Python 里做：SQL 侧要按本地小时分桶只能用 strftime，那会让索引失效
        # （03 文档开头的两条约定之一）。
        buckets: dict[int, int] = {}
        for row in rows:
            hour = datetime.fromtimestamp(int(row["down_ts_ns"]) / 1_000_000_000, tz=tz).hour
            buckets[hour] = buckets.get(hour, 0) + 1
        return buckets


__all__ = ["InsightsRepository"]
