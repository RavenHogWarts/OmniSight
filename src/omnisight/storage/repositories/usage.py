"""应用使用时长查询（M1 起最小可用，M2 补齐 05 文档要求的全部字段）。

**"某日总时长"必须走 ``agg_app_day``，不能走 ``SUM(usage_session.duration_ms)``**：
后者把跨日会话整段算给起始日（``usage_session.day_bucket`` 是起始日）。切分已经在写入
时做好，查询侧只要别绕过它。这是 03 文档 §3.3 点明的易错点，也是这段注释存在的理由。
"""

from __future__ import annotations

from sqlite3 import Connection

from ..database import Database

#: 一次访问 = 不是心跳切段的那一行。抽成模块级常量，长 SQL 里可直接内插。
VISIT_SQL = "end_reason <> 'heartbeat'"


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

        **四个标量子查询而不是 ``UNION ALL`` 再取极值。** 后者读不到主键的有序性，
        三年数据要全扫 ``agg_key_day``（120k 行，实测 13–25ms）；而 ``range=total``
        的每个请求都要先算它，于是这 20ms 加在所有全期查询上。拆开之后每一项都是
        SQLite 对 ``MIN``/``MAX`` 的索引优化路径（O(log n)），并集在 Python 里取。
        """
        row = self._conn().execute(
            "SELECT (SELECT MIN(bucket)     FROM agg_key_day) AS key_min,"
            "       (SELECT MAX(bucket)     FROM agg_key_day) AS key_max,"
            "       (SELECT MIN(day_bucket) FROM agg_app_day) AS app_min,"
            "       (SELECT MAX(day_bucket) FROM agg_app_day) AS app_max"
        ).fetchone()
        if row is None:  # pragma: no cover - 标量子查询恒返回一行
            return (None, None)
        lows = [value for value in (row["key_min"], row["app_min"]) if value]
        highs = [value for value in (row["key_max"], row["app_max"]) if value]
        return (min(lows) if lows else None, max(highs) if highs else None)

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


    # ── M2：周期查询 ────────────────────────────────────────────────────
    #: 一次访问在库里就是 ``end_reason <> 'heartbeat'`` 的那一行，它自带完整跨度。
    #: 心跳落盘每 10 秒切一段，所以"会话段数"与"用了几次"差两个数量级——查询侧必须
    #: 分清这两件事（理由见 ``migrations/m002_query_support``）。
    VISIT_FILTER = VISIT_SQL

    def app_durations(self, start_day: str, end_day: str) -> list[dict]:
        """周期内各应用的时长、访问次数与最长一次访问。走 ``agg_app_day``。"""
        rows = self._conn().execute(
            "SELECT app_id, SUM(duration_ms) AS duration_ms, "
            "       SUM(session_count) AS session_count, "
            "       MAX(longest_visit_ms) AS longest_visit_ms "
            "FROM agg_app_day WHERE day_bucket BETWEEN ? AND ? GROUP BY app_id",
            (start_day, end_day),
        )
        return [_duration_row(row) for row in rows]

    def app_durations_total(self) -> list[dict]:
        """全部历史。``longest_visit_ms`` 仍取自日聚合——月/年/总的最长访问就是各日之最大。"""
        rows = self._conn().execute(
            "SELECT t.app_id, t.duration_ms, t.session_count, t.last_used_ts_ns, "
            "       (SELECT MAX(d.longest_visit_ms) FROM agg_app_day d "
            "        WHERE d.app_id = t.app_id) AS longest_visit_ms "
            "FROM agg_app_total t"
        )
        return [
            {**_duration_row(row), "last_used_ts_ns": int(row["last_used_ts_ns"] or 0)}
            for row in rows
        ]

    def day_totals(self, start_day: str, end_day: str) -> dict[str, int]:
        rows = self._conn().execute(
            "SELECT day_bucket, SUM(duration_ms) AS duration_ms FROM agg_app_day "
            "WHERE day_bucket BETWEEN ? AND ? GROUP BY day_bucket",
            (start_day, end_day),
        )
        return {row["day_bucket"]: int(row["duration_ms"] or 0) for row in rows}

    def bucket_app_totals(self, grain: str, start: str, end: str) -> list[dict]:
        """趋势桶 × 应用的时长。``grain`` ∈ ``day`` | ``month`` | ``year``。

        趋势图的桶高与类别构成都由服务层从这里折出来（活动带上面板按类别堆叠，
        14 文档 §4.3）。**没有"只要桶总和"的那个方法**：整桶 ``SUM(duration_ms)`` 不认识
        合并与排除，用它算出的柱高会比同一屏的英雄数值大一截（见 ``UsageService.
        trend_composition``）。多一个应用维度的代价只有行数：日粒度看一个月是 31 ×
        应用数行，仍然是同一次主键范围扫，没有新的表也没有新的索引。
        """
        table, column = _BUCKET_TABLES[grain]
        rows = self._conn().execute(
            f"SELECT {column} AS bucket, app_id, SUM(duration_ms) AS duration_ms "
            f"FROM {table} WHERE {column} BETWEEN ? AND ? GROUP BY {column}, app_id",
            (start, end),
        )
        return [
            {
                "bucket": str(row["bucket"]),
                "app_id": int(row["app_id"]),
                "duration_ms": int(row["duration_ms"] or 0),
            }
            for row in rows
        ]

    def hourly_apps(self, start_day: str, end_day: str) -> list[dict]:
        """``(hour, app_id, duration_ms)``，跨日时同一小时相加。

        **性能改进**：旧 ``query_hourly_app_distribution()`` 把区间内所有会话行读进
        Python 再逐小时切分，``total`` 视图下是全表扫描。切分已在写入时做过一次
        （``agg_app_hour``），这里只剩一次主键范围扫。
        """
        rows = self._conn().execute(
            "SELECT hour, app_id, SUM(duration_ms) AS duration_ms FROM agg_app_hour "
            "WHERE day_bucket BETWEEN ? AND ? GROUP BY hour, app_id",
            (start_day, end_day),
        )
        return [
            {
                "hour": int(row["hour"]),
                "app_id": int(row["app_id"]),
                "duration_ms": int(row["duration_ms"] or 0),
            }
            for row in rows
        ]

    def app_day_series(self, app_id: int, start_day: str, end_day: str) -> dict[str, int]:
        rows = self._conn().execute(
            "SELECT day_bucket, duration_ms FROM agg_app_day "
            "WHERE app_id = ? AND day_bucket BETWEEN ? AND ?",
            (app_id, start_day, end_day),
        )
        return {row["day_bucket"]: int(row["duration_ms"] or 0) for row in rows}

    # ── M2：会话与访问 ──────────────────────────────────────────────────
    def sessions(
        self,
        start_day: str,
        end_day: str,
        *,
        app_id: int | None = None,
        visits_only: bool = True,
        limit: int = 200,
        offset: int = 0,
    ) -> list[dict]:
        """会话明细。默认只返回**访问**（合并掉心跳切段）。

        ``visits_only=False`` 才返回原始段，那是导出与排障用的：05 文档 §3 的"所有使用
        记录"面板要的是访问，否则用户会看到一屏 10 秒一条的记录。
        """
        clauses = ["day_bucket BETWEEN ? AND ?"]
        params: list[object] = [start_day, end_day]
        if visits_only:
            clauses.append(self.VISIT_FILTER)
        if app_id is not None:
            clauses.append("app_id = ?")
            params.append(app_id)
        where = " AND ".join(clauses)
        rows = self._conn().execute(
            "SELECT id, app_id, window_title, start_ts_ns, end_ts_ns, duration_ms, "
            "       day_bucket, idle_trimmed, end_reason, visit_start_ts_ns "
            f"FROM usage_session WHERE {where} "
            "ORDER BY start_ts_ns DESC LIMIT ? OFFSET ?",
            (*params, limit, offset),
        )
        return [_session_row(row) for row in rows]

    def session_total(
        self,
        start_day: str,
        end_day: str,
        *,
        app_id: int | None = None,
        visits_only: bool = True,
    ) -> int:
        clauses = ["day_bucket BETWEEN ? AND ?"]
        params: list[object] = [start_day, end_day]
        if visits_only:
            clauses.append(self.VISIT_FILTER)
        if app_id is not None:
            clauses.append("app_id = ?")
            params.append(app_id)
        where = " AND ".join(clauses)
        row = self._conn().execute(
            f"SELECT COUNT(*) FROM usage_session WHERE {where}", tuple(params)
        ).fetchone()
        return int(row[0] or 0)

    def switch_count(self, start_day: str, end_day: str) -> int:
        """注意力碎片化程度：主动切走的次数（05 文档 §5）。

        只数 ``end_reason = 'switch'``——空闲、关机、被排除都不是"用户切走了"。
        """
        row = self._conn().execute(
            "SELECT COUNT(*) FROM usage_session "
            "WHERE day_bucket BETWEEN ? AND ? AND end_reason = 'switch'",
            (start_day, end_day),
        ).fetchone()
        return int(row[0] or 0)

    def longest_visits(
        self, start_day: str, end_day: str, *, limit: int = 20, min_ms: int = 0
    ) -> list[dict]:
        """最长的几次访问，供"专注时段"用。

        走部分索引 ``idx_session_visits``：扫的是访问数（几百行/天）而不是会话段数
        （心跳每 10 秒一段，重度用户 8000 行/天）。
        """
        rows = self._conn().execute(
            "SELECT app_id, visit_start_ts_ns, start_ts_ns, end_ts_ns, end_reason, "
            "       (end_ts_ns - CASE WHEN visit_start_ts_ns > 0 "
            "                         THEN visit_start_ts_ns ELSE start_ts_ns END) AS span_ns "
            f"FROM usage_session WHERE day_bucket BETWEEN ? AND ? AND {VISIT_SQL} "
            "AND span_ns >= ? ORDER BY span_ns DESC LIMIT ?",
            (start_day, end_day, min_ms * 1_000_000, limit),
        )
        return [
            {
                "app_id": int(row["app_id"]),
                "start_ts_ns": int(row["visit_start_ts_ns"] or row["start_ts_ns"]),
                "end_ts_ns": int(row["end_ts_ns"]),
                "duration_ms": int(row["span_ns"]) // 1_000_000,
                "end_reason": row["end_reason"],
            }
            for row in rows
        ]


#: 趋势桶粒度 → (表, 桶列)。``hour`` 不在这里：它按 ``day_bucket + hour`` 存，
#: 由 :meth:`UsageRepository.hourly_apps` 处理。
_BUCKET_TABLES: dict[str, tuple[str, str]] = {
    "day": ("agg_app_day", "day_bucket"),
    "month": ("agg_app_month", "month_bucket"),
    "year": ("agg_app_year", "year_bucket"),
}


def _duration_row(row) -> dict:
    return {
        "app_id": int(row["app_id"]),
        "duration_ms": int(row["duration_ms"] or 0),
        "session_count": int(row["session_count"] or 0),
        "longest_visit_ms": int(row["longest_visit_ms"] or 0),
    }


def _session_row(row) -> dict:
    """**窗口标题原样带出**，由服务层按 ``include_titles`` 与隐私设置决定是否下发。

    仓储不做隐私判断是刻意的：判断散落在多处必然有一处漏掉，而这一档是 08 文档里最
    敏感的。服务层是唯一的过滤点，且有一条覆盖全部端点的回归测试盯住它。
    """
    visit_start = int(row["visit_start_ts_ns"] or 0) or int(row["start_ts_ns"])
    return {
        "id": int(row["id"]),
        "app_id": int(row["app_id"]),
        "window_title": row["window_title"] or "",
        "start_ts_ns": int(row["start_ts_ns"]),
        "visit_start_ts_ns": visit_start,
        "end_ts_ns": int(row["end_ts_ns"]),
        "duration_ms": int(row["duration_ms"]),
        "visit_duration_ms": (int(row["end_ts_ns"]) - visit_start) // 1_000_000,
        "day_bucket": row["day_bucket"],
        "idle_trimmed": bool(row["idle_trimmed"]),
        "end_reason": row["end_reason"] or "switch",
    }


def _ranking_row(row) -> dict:
    return {
        "app_id": int(row["app_id"]),
        "name": row["name"] or "未知",
        "duration_ms": int(row["duration_ms"] or 0),
        "session_count": int(row["session_count"] or 0),
    }


__all__ = ["VISIT_SQL", "UsageRepository"]
