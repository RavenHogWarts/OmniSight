"""按键统计的最小查询（M1 只做"够验证闭环"的量，完整版在 M2）。

一条铁律贯穿本文件：**任何常规查询都不扫 `raw_key_events_*`**（01 文档 §4.1）。
下面每个方法都只碰 ``agg_*``，主键点查或范围扫。唯一允许扫原始表的是节奏分析，
那是 M4 的独立入口且必须带时间窗上限。
"""

from __future__ import annotations

from sqlite3 import Connection

from ..database import Database

_GRAIN_TABLES = {
    "day": "agg_key_day",
    "month": "agg_key_month",
    "year": "agg_key_year",
}


class KeyRepository:
    __slots__ = ("_db",)

    def __init__(self, db: Database) -> None:
        self._db = db

    def _conn(self) -> Connection:
        return self._db.connect()

    def heatmap(self, *, grain: str = "day", bucket: str | None = None) -> dict[str, dict]:
        """某个桶的键盘热力数据。``grain='total'`` 时忽略 ``bucket``。"""
        if grain == "total":
            rows = self._conn().execute(
                "SELECT key_id, press_count, duration_total_ms, duration_max_ms "
                "FROM agg_key_total"
            )
        else:
            table = _GRAIN_TABLES.get(grain)
            if table is None:
                raise ValueError(f"未知的粒度：{grain!r}")
            rows = self._conn().execute(
                f"SELECT key_id, press_count, duration_total_ms, duration_max_ms "
                f"FROM {table} WHERE bucket = ?",
                (bucket,),
            )
        return {row["key_id"]: _metrics(row) for row in rows}

    def range_heatmap(self, start_day: str, end_day: str) -> dict[str, dict]:
        """按日期区间聚合（周视图与自定义区间走这里，沿用 KeyTrace 的判断）。"""
        rows = self._conn().execute(
            "SELECT key_id, SUM(press_count) AS press_count, "
            "SUM(duration_total_ms) AS duration_total_ms, "
            "MAX(duration_max_ms) AS duration_max_ms "
            "FROM agg_key_day WHERE bucket BETWEEN ? AND ? GROUP BY key_id",
            (start_day, end_day),
        )
        return {row["key_id"]: _metrics(row) for row in rows}

    def app_heatmap(self, app_id: int) -> dict[str, dict]:
        """★ 某应用的键盘热力图：**一次主键范围查**。

        旧 KeyTrace 走的是"HTTP 取该应用全部历史区间 → 区间合并 → 按月分组 → 对每个
        区间在原始表上做范围扫 → Python 侧逐行累加"，复杂度 O(区间数 × 区间内事件数)。
        这里是 O(该应用活跃键数)，通常 ≤ 118 行。
        """
        rows = self._conn().execute(
            "SELECT key_id, press_count, duration_total_ms, duration_max_ms "
            "FROM agg_app_key_total WHERE app_id = ?",
            (app_id,),
        )
        return {row["key_id"]: _metrics(row) for row in rows}

    def app_heatmap_range(self, app_id: int, start_day: str, end_day: str) -> dict[str, dict]:
        """带日期区间的应用热力图——合并之后才可能存在的能力。"""
        rows = self._conn().execute(
            "SELECT key_id, SUM(press_count) AS press_count, "
            "SUM(duration_total_ms) AS duration_total_ms, "
            "MAX(duration_max_ms) AS duration_max_ms "
            "FROM agg_key_app_day WHERE app_id = ? AND day_bucket BETWEEN ? AND ? "
            "GROUP BY key_id",
            (app_id, start_day, end_day),
        )
        return {row["key_id"]: _metrics(row) for row in rows}

    def apps_for_key(self, key_id: str, limit: int = 10) -> list[dict]:
        """★ 反向查询：某个键主要被哪些应用按。合并前完全无法回答。"""
        rows = self._conn().execute(
            "SELECT app_id, SUM(press_count) AS press_count "
            "FROM agg_key_app_day WHERE key_id = ? GROUP BY app_id "
            "ORDER BY press_count DESC LIMIT ?",
            (key_id, limit),
        )
        return [
            {"app_id": int(row["app_id"]), "press_count": int(row["press_count"])}
            for row in rows
        ]

    def hourly(self, day: str) -> list[dict]:
        rows = self._conn().execute(
            "SELECT hour, SUM(press_count) AS press_count, "
            "SUM(duration_total_ms) AS duration_total_ms "
            "FROM agg_key_hour WHERE day_bucket = ? GROUP BY hour ORDER BY hour",
            (day,),
        )
        return [
            {
                "hour": int(row["hour"]),
                "press_count": int(row["press_count"]),
                "duration_total_ms": float(row["duration_total_ms"]),
            }
            for row in rows
        ]

    def press_total(self) -> int:
        row = self._conn().execute("SELECT SUM(press_count) FROM agg_key_total").fetchone()
        return int(row[0] or 0)

    def top_keys(self, limit: int = 10) -> list[dict]:
        rows = self._conn().execute(
            "SELECT key_id, press_count, duration_total_ms, duration_max_ms "
            "FROM agg_key_total ORDER BY press_count DESC LIMIT ?",
            (limit,),
        )
        return [{"key_id": row["key_id"], **_metrics(row)} for row in rows]


def _metrics(row) -> dict:
    total = float(row["duration_total_ms"] or 0.0)
    count = int(row["press_count"] or 0)
    return {
        "press_count": count,
        "duration_total_ms": total,
        # 平均值在这里算而不是让前端算：分母为 0 的路径只该存在一处。
        "duration_avg_ms": (total / count) if count else 0.0,
        "duration_max_ms": float(row["duration_max_ms"] or 0.0),
    }


__all__ = ["KeyRepository"]
