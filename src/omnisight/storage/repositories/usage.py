"""应用使用时长的最小查询（M1 版，完整版在 M2）。

**"某日总时长"必须走 ``agg_app_day``，不能走 ``SUM(usage_session.duration_ms)``**：
后者把跨日会话整段算给起始日（``usage_session.day_bucket`` 是起始日）。切分已经在写入
时做好，查询侧只要别绕过它。这是 03 文档 §3.3 点明的易错点，也是这段注释存在的理由。
"""

from __future__ import annotations

from sqlite3 import Connection

from ..database import Database


class UsageRepository:
    __slots__ = ("_db",)

    def __init__(self, db: Database) -> None:
        self._db = db

    def _conn(self) -> Connection:
        return self._db.connect()

    def day_ranking(self, day: str, limit: int = 20) -> list[dict]:
        rows = self._conn().execute(
            "SELECT d.app_id, d.duration_ms, d.session_count, "
            "       COALESCE(a.user_alias, a.display_name) AS name "
            "FROM agg_app_day d LEFT JOIN app a ON a.id = d.app_id "
            "WHERE d.day_bucket = ? ORDER BY d.duration_ms DESC LIMIT ?",
            (day, limit),
        )
        return [_ranking_row(row) for row in rows]

    def range_ranking(self, start_day: str, end_day: str, limit: int = 20) -> list[dict]:
        rows = self._conn().execute(
            "SELECT d.app_id, SUM(d.duration_ms) AS duration_ms, "
            "       SUM(d.session_count) AS session_count, "
            "       COALESCE(a.user_alias, a.display_name) AS name "
            "FROM agg_app_day d LEFT JOIN app a ON a.id = d.app_id "
            "WHERE d.day_bucket BETWEEN ? AND ? GROUP BY d.app_id "
            "ORDER BY duration_ms DESC LIMIT ?",
            (start_day, end_day, limit),
        )
        return [_ranking_row(row) for row in rows]

    def totals(self, limit: int = 20) -> list[dict]:
        rows = self._conn().execute(
            "SELECT t.app_id, t.duration_ms, t.session_count, t.last_used_ts_ns, "
            "       COALESCE(a.user_alias, a.display_name) AS name "
            "FROM agg_app_total t LEFT JOIN app a ON a.id = t.app_id "
            "ORDER BY t.duration_ms DESC LIMIT ?",
            (limit,),
        )
        return [
            {**_ranking_row(row), "last_used_ts_ns": int(row["last_used_ts_ns"] or 0)}
            for row in rows
        ]

    def hourly(self, day: str) -> list[dict]:
        rows = self._conn().execute(
            "SELECT hour, app_id, duration_ms FROM agg_app_hour "
            "WHERE day_bucket = ? ORDER BY hour, duration_ms DESC",
            (day,),
        )
        return [
            {
                "hour": int(row["hour"]),
                "app_id": int(row["app_id"]),
                "duration_ms": int(row["duration_ms"]),
            }
            for row in rows
        ]

    def day_total_ms(self, day: str) -> int:
        row = self._conn().execute(
            "SELECT SUM(duration_ms) FROM agg_app_day WHERE day_bucket = ?", (day,)
        ).fetchone()
        return int(row[0] or 0)

    def data_range(self) -> tuple[str | None, str | None]:
        """有数据的日期范围，供 ``/api/v1/status`` 与周期选择器的可选区间使用。

        两张来源表取并集：只用过键盘的日子（没有前台归因）与只有会话的日子都算有数据。
        """
        row = self._conn().execute(
            "SELECT MIN(bucket), MAX(bucket) FROM ("
            "  SELECT bucket FROM agg_key_day UNION ALL "
            "  SELECT day_bucket AS bucket FROM agg_app_day)"
        ).fetchone()
        return (row[0], row[1]) if row else (None, None)

    def recent_sessions(self, limit: int = 20) -> list[dict]:
        """会话明细。**不返回窗口标题**——它是 08 文档里最敏感的一档，接口不外泄。"""
        rows = self._conn().execute(
            "SELECT id, app_id, start_ts_ns, end_ts_ns, duration_ms, day_bucket, idle_trimmed "
            "FROM usage_session ORDER BY start_ts_ns DESC LIMIT ?",
            (limit,),
        )
        return [
            {
                "id": int(row["id"]),
                "app_id": int(row["app_id"]),
                "start_ts_ns": int(row["start_ts_ns"]),
                "end_ts_ns": int(row["end_ts_ns"]),
                "duration_ms": int(row["duration_ms"]),
                "day_bucket": row["day_bucket"],
                "idle_trimmed": bool(row["idle_trimmed"]),
            }
            for row in rows
        ]


def _ranking_row(row) -> dict:
    return {
        "app_id": int(row["app_id"]),
        "name": row["name"] or "未知",
        "duration_ms": int(row["duration_ms"] or 0),
        "session_count": int(row["session_count"] or 0),
    }


__all__ = ["UsageRepository"]
