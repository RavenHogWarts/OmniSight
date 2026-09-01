"""按键统计查询（M1 只做"够验证闭环"的量，M2 补齐 05 文档 §4 的全部端点）。

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

    # ── M2：周期查询 ────────────────────────────────────────────────────
    def metrics_for_range(
        self, start_day: str, end_day: str, *, app_id: int | None = None
    ) -> dict[str, dict]:
        """周期内的键盘指标。给 ``app_id`` 就走 ``agg_key_app_day``。

        **``app_id`` 这个参数是合并的最大收益点**：旧 KeyTrace 要先 HTTP 向 TimeLens 取
        该进程的全部前台区间，合并成不重叠区间列表，再按月分组、对每个区间在原始事件表
        上做范围扫、最后在 Python 里逐行累加——O(区间数 × 区间内事件数)。这里是一次
        范围扫，结果最多 118 行。
        """
        if app_id is None:
            return self.range_heatmap(start_day, end_day)
        return self.app_heatmap_range(app_id, start_day, end_day)

    def metrics_total(self, *, app_id: int | None = None) -> dict[str, dict]:
        if app_id is None:
            return self.heatmap(grain="total")
        return self.app_heatmap(app_id)

    def bucket_metrics(
        self, grain: str, start: str, end: str, *, app_id: int | None = None
    ) -> dict[str, dict]:
        """时间线的桶 → 指标。``grain`` ∈ ``day`` | ``month`` | ``year``。

        限定应用时只有 ``agg_key_app_day`` 这一份日粒度事实，月/年桶由它现场汇总——
        为"应用 × 键 × 月"再建两张表并不划算：一年只有 12 个桶，汇总 365 行的代价
        比多两张表的写入代价低。
        """
        if app_id is None:
            table = _GRAIN_TABLES.get(grain)
            if table is None:
                raise ValueError(f"未知的粒度：{grain!r}")
            rows = self._conn().execute(
                f"SELECT bucket, SUM(press_count) AS press_count, "
                f"SUM(duration_total_ms) AS duration_total_ms, "
                f"MAX(duration_max_ms) AS duration_max_ms "
                f"FROM {table} WHERE bucket BETWEEN ? AND ? GROUP BY bucket",
                (start, end),
            )
        else:
            length = {"day": 10, "month": 7, "year": 4}.get(grain)
            if length is None:
                raise ValueError(f"未知的粒度：{grain!r}")
            rows = self._conn().execute(
                "SELECT SUBSTR(day_bucket, 1, ?) AS bucket, "
                "SUM(press_count) AS press_count, "
                "SUM(duration_total_ms) AS duration_total_ms, "
                "MAX(duration_max_ms) AS duration_max_ms "
                "FROM agg_key_app_day WHERE app_id = ? AND day_bucket BETWEEN ? AND ? "
                "GROUP BY bucket",
                (length, app_id, start, end),
            )
        return {row["bucket"]: _metrics(row) for row in rows}

    def hourly_metrics(
        self, start_day: str, end_day: str, *, key_id: str | None = None
    ) -> dict[int, dict]:
        """24 小时分布（"我一般几点在敲键盘"）。旧版扫当月原始事件表再在 Python 里分桶。

        **两张表，按需要按不按键分**：不限定按键时读 ``agg_press_hour``（键无关，三年
        26k 行）；限定某个键时读 ``agg_key_hour`` 并走 ``idx_agg_key_hour_key``。同一个
        事实在 ``agg_key_hour`` 里按键拆开存，不限定按键还去读它意味着扫三年 2.9M 行
        （实测 200ms，是 M2 基准里最大的单项开销）。
        """
        if key_id is None:
            rows = self._conn().execute(
                "SELECT hour, SUM(press_count) AS press_count, "
                "SUM(duration_total_ms) AS duration_total_ms, 0 AS duration_max_ms "
                "FROM agg_press_hour WHERE day_bucket BETWEEN ? AND ? GROUP BY hour",
                (start_day, end_day),
            )
        else:
            rows = self._conn().execute(
                "SELECT hour, SUM(press_count) AS press_count, "
                "SUM(duration_total_ms) AS duration_total_ms, 0 AS duration_max_ms "
                "FROM agg_key_hour WHERE key_id = ? AND day_bucket BETWEEN ? AND ? "
                "GROUP BY hour",
                (key_id, start_day, end_day),
            )
        return {int(row["hour"]): _metrics(row) for row in rows}

    def apps_for_key_range(
        self, key_id: str, start_day: str, end_day: str, limit: int = 20
    ) -> list[dict]:
        """★ 反向视图：某个键在这段时间主要被哪些应用按。合并前完全无法回答。"""
        rows = self._conn().execute(
            "SELECT app_id, SUM(press_count) AS press_count, "
            "SUM(duration_total_ms) AS duration_total_ms "
            "FROM agg_key_app_day WHERE key_id = ? AND day_bucket BETWEEN ? AND ? "
            "GROUP BY app_id ORDER BY press_count DESC LIMIT ?",
            (key_id, start_day, end_day, limit),
        )
        return [
            {
                "app_id": int(row["app_id"]),
                "press_count": int(row["press_count"] or 0),
                "duration_total_ms": float(row["duration_total_ms"] or 0.0),
            }
            for row in rows
        ]

    def app_key_totals(self, start_day: str, end_day: str) -> dict[int, dict[str, int]]:
        """``app_id`` → ``{key_id: press_count}``，一次查完整个周期。

        洞察面板要为十几个应用各取 Top 键，逐个应用发一次查询就是 N+1。
        """
        rows = self._conn().execute(
            "SELECT app_id, key_id, SUM(press_count) AS press_count "
            "FROM agg_key_app_day WHERE day_bucket BETWEEN ? AND ? "
            "GROUP BY app_id, key_id",
            (start_day, end_day),
        )
        result: dict[int, dict[str, int]] = {}
        for row in rows:
            result.setdefault(int(row["app_id"]), {})[row["key_id"]] = int(row["press_count"] or 0)
        return result

    def app_key_totals_all_time(self) -> dict[int, dict[str, int]]:
        rows = self._conn().execute(
            "SELECT app_id, key_id, press_count FROM agg_app_key_total"
        )
        result: dict[int, dict[str, int]] = {}
        for row in rows:
            result.setdefault(int(row["app_id"]), {})[row["key_id"]] = int(row["press_count"] or 0)
        return result

    # ── M2：分钟级（``peak_kpm`` 与 ``active_hours`` 的唯一来源）───────────
    def minute_peak(self, start_day: str, end_day: str) -> dict | None:
        """峰值 KPM 及其发生的那一分钟。

        小时聚合只能给出"某小时的平均 KPM"，把平均值叫成峰值是在编数据——
        ``agg_press_minute`` 就是为这个字段存在的（05 文档 §5）。
        """
        row = self._conn().execute(
            "SELECT day_bucket, minute, press_count FROM agg_press_minute "
            "WHERE day_bucket BETWEEN ? AND ? ORDER BY press_count DESC, day_bucket, minute "
            "LIMIT 1",
            (start_day, end_day),
        ).fetchone()
        if row is None or not row["press_count"]:
            return None
        return {
            "day": row["day_bucket"],
            "minute": int(row["minute"]),
            "press_count": int(row["press_count"]),
        }

    def minute_bounds(self, start_day: str, end_day: str) -> tuple[int | None, int | None]:
        """周期内**最早与最晚的活跃时刻**（当日分钟序号 0–1439），供 ``active_hours`` 用。

        取的是"一天中的哪一分钟"而不是"哪一天的哪一分钟"：跨多天时用户想知道的是
        "我一般 9:12 开始、23:41 结束"，而不是区间首日的第一次按键。单日周期下两者等价。
        """
        row = self._conn().execute(
            "SELECT MIN(minute), MAX(minute) FROM agg_press_minute "
            "WHERE day_bucket BETWEEN ? AND ? AND press_count > 0",
            (start_day, end_day),
        ).fetchone()
        if row is None or row[0] is None:
            return (None, None)
        return (int(row[0]), int(row[1]))

    def presses_in_day_minutes(self, day: str, start_minute: int, end_minute: int) -> int:
        """某天 ``[start_minute, end_minute]`` 之间的按键数（闭区间）。

        专注时段的按键量由此得出：一次访问期间前台始终是同一个应用，因此"这段时间的
        按键总数"就是"这个应用在这段时间的按键数"。边界那一分钟整格计入——分钟是我们
        存的最细粒度，为了几秒的精度去扫原始事件不值当（05 文档 §5）。
        """
        row = self._conn().execute(
            "SELECT SUM(press_count) FROM agg_press_minute "
            "WHERE day_bucket = ? AND minute BETWEEN ? AND ?",
            (day, start_minute, end_minute),
        ).fetchone()
        return int(row[0] or 0)

    def press_total_range(self, start_day: str, end_day: str) -> int:
        row = self._conn().execute(
            "SELECT SUM(press_count) FROM agg_key_day WHERE bucket BETWEEN ? AND ?",
            (start_day, end_day),
        ).fetchone()
        return int(row[0] or 0)

    def active_key_count(self, start_day: str, end_day: str) -> int:
        row = self._conn().execute(
            "SELECT COUNT(DISTINCT key_id) FROM agg_key_day "
            "WHERE bucket BETWEEN ? AND ? AND press_count > 0",
            (start_day, end_day),
        ).fetchone()
        return int(row[0] or 0)

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
