"""应用时长服务（05 文档 §3）。

三个和现状不同的地方，都是合并才可能做到的：

* **``presses`` 与时长在同一行**。旧 TimeLens 只有时长，KeyTrace 只有按键，"看视频的
  两小时"和"写代码的两小时"在任何一张列表里都长得一样。
* **``longest_session_seconds`` 是真的最长一次访问**，不是最长的心跳段
  （见 ``migrations/m002_query_support``）。
* **小时分布查预聚合表**。旧 ``query_hourly_app_distribution()`` 在 ``total`` 视图下
  是全表扫描 + O(会话数 × 跨越小时数) 的 Python 循环。
"""

from __future__ import annotations

from . import categories, formatting
from .apps import AppService
from .context import ServiceContext
from .period import Period

#: 排序键 → 取值函数。``name`` 用展示名，其余用数值倒序。
_SORT_KEYS: dict[str, str] = {
    "seconds": "duration_ms",
    "presses": "presses",
    "sessions": "session_count",
    "name": "display_name",
}


class UsageService:
    __slots__ = ("_apps", "_ctx")

    def __init__(self, ctx: ServiceContext, apps: AppService) -> None:
        self._ctx = ctx
        self._apps = apps

    # ── 应用榜单 ────────────────────────────────────────────────────────
    def app_rows(self, period: Period) -> list[dict]:
        """折叠后的应用行（时长 + 访问次数 + 最长访问 + 按键数），按时长倒序。

        缓存键含周期与 ``data_version``；当前周期的 ``data_version`` 每秒都在变，因此
        实际上只有历史周期会命中——这正是我们想要的（见 :mod:`.cache`）。
        """
        return self._ctx.cached(
            ("usage.app_rows", period.range, period.day_range),
            lambda: self._app_rows(period),
        )

    def _app_rows(self, period: Period) -> list[dict]:
        lens = self._apps.lens()
        if period.range == "total":
            raw = self._ctx.usage_repo.app_durations_total()
            presses = self._ctx.insight_repo.app_presses_all_time()
        else:
            raw = self._ctx.usage_repo.app_durations(period.start_day, period.end_day)
            presses = self._ctx.insight_repo.app_presses(period.start_day, period.end_day)
        folded = lens.fold(
            raw,
            sum_fields=("duration_ms", "session_count"),
            max_fields=("longest_visit_ms", "last_used_ts_ns"),
        )
        press_by_root = lens.fold_counts(presses)
        rows: list[dict] = []
        for row in folded:
            app_id = row["app_id"]
            meta = lens.meta(app_id)
            duration_ms = int(row.get("duration_ms") or 0)
            count = press_by_root.get(app_id, 0)
            rows.append(
                {
                    "app_id": app_id,
                    "display_name": lens.name(app_id),
                    "process_name": meta.process_name if meta else "",
                    "user_alias": meta.user_alias if meta else None,
                    "app_key": meta.app_key if meta else "",
                    "category": lens.category(app_id),
                    "duration_ms": duration_ms,
                    "session_count": int(row.get("session_count") or 0),
                    "longest_visit_ms": int(row.get("longest_visit_ms") or 0),
                    "presses": count,
                    "kpm": formatting.ratio_per_minute(count, duration_ms),
                    "first_seen_at": meta.first_seen_at if meta else None,
                    "last_seen_at": meta.last_seen_at if meta else None,
                    "icon_url": self._apps.icon_url(meta) if meta else None,
                }
            )
        rows.sort(key=lambda item: item["duration_ms"], reverse=True)
        return rows

    def period_apps(
        self,
        period: Period,
        *,
        sort: str = "seconds",
        category: str | None = None,
        query: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, object]:
        rows = self.app_rows(period)
        if category:
            rows = [row for row in rows if row["category"] == category]
        if query:
            rows = _search(rows, query)
        total_ms = sum(row["duration_ms"] for row in rows)
        rows = _sorted(rows, sort)
        running = self._apps.running_app_keys()
        page = rows[offset : offset + limit]
        return {
            "total_seconds": round(total_ms / 1000, 1),
            "total_seconds_formatted": formatting.format_duration(total_ms / 1000),
            "app_count": len(rows),
            "apps": [self._app_payload(row, total_ms, running) for row in page],
            "pagination": {"total": len(rows), "limit": limit, "offset": offset},
            # 前端要知道搜索是在服务端做的，否则"周期里 500 个应用"的上限会让人觉得
            # 搜索结果也不全（M3 已知限制 3 的修复）。
            "filtered_by": query or None,
            # 行内 KPM 的分母口径（12 文档 M4 判据：分母口径在 UI 上有说明）。
            "kpm_basis": "各应用的前台时长（不含空闲与无前台时段）",
        }

    def _app_payload(
        self, row: dict, total_ms: int, running: frozenset[str]
    ) -> dict[str, object]:
        seconds = row["duration_ms"] / 1000
        return {
            "app_id": row["app_id"],
            "display_name": row["display_name"],
            "process_name": row["process_name"],
            "user_alias": row["user_alias"],
            "category": row["category"],
            "seconds": round(seconds, 1),
            "seconds_formatted": formatting.format_duration(seconds),
            "percent": formatting.percent(row["duration_ms"], total_ms),
            "session_count": row["session_count"],
            "longest_session_seconds": round(row["longest_visit_ms"] / 1000, 1),
            "first_seen_at": row["first_seen_at"],
            "last_seen_at": row["last_seen_at"],
            "presses": row["presses"],
            "kpm": row["kpm"],
            "icon_url": row["icon_url"],
            "is_running": row["app_key"] in running if row["app_key"] else False,
        }

    # ── 概览用的汇总 ────────────────────────────────────────────────────
    def screen_time(self, period: Period) -> dict[str, object]:
        rows = self.app_rows(period)
        total_ms = sum(row["duration_ms"] for row in rows)
        previous = self._ctx.previous_period(period)
        previous_ms = (
            sum(row["duration_ms"] for row in self.app_rows(previous)) if previous else 0
        )
        seconds = total_ms / 1000
        return {
            "total_seconds": round(seconds, 1),
            "total_formatted": formatting.format_duration(seconds),
            "app_count": len(rows),
            "daily_average_seconds": round(seconds / max(period.days, 1), 1),
            "delta_vs_previous": (
                {
                    "seconds": formatting.delta(total_ms, previous_ms)["value"] / 1000,
                    "percent": formatting.delta(total_ms, previous_ms)["percent"],
                }
                if previous
                else None
            ),
        }

    def category_breakdown(self, period: Period) -> list[dict[str, object]]:
        rows = self.app_rows(period)
        total_ms = sum(row["duration_ms"] for row in rows)
        buckets: dict[str, dict[str, float]] = {}
        for row in rows:
            slot = buckets.setdefault(row["category"], {"duration_ms": 0, "presses": 0})
            slot["duration_ms"] += row["duration_ms"]
            slot["presses"] += row["presses"]
        ordered = sorted(buckets.items(), key=lambda item: item[1]["duration_ms"], reverse=True)
        return [
            {
                "id": category,
                "name": categories.name_of(category),
                "seconds": round(values["duration_ms"] / 1000, 1),
                "seconds_formatted": formatting.format_duration(values["duration_ms"] / 1000),
                "percent": formatting.percent(values["duration_ms"], total_ms),
                "presses": int(values["presses"]),
            }
            for category, values in ordered
        ]

    # ── 小时分布 ────────────────────────────────────────────────────────
    def timeline(self, period: Period, *, top: int = 5) -> dict[str, object]:
        """按小时的应用分布。跨多天时同一小时相加（"我一般几点在用什么"）。"""
        lens = self._apps.lens()
        raw = self._ctx.usage_repo.hourly_apps(period.start_day, period.end_day)
        presses = self._ctx.key_repo.hourly_metrics(period.start_day, period.end_day)
        per_hour: dict[int, dict[int, int]] = {}
        for row in raw:
            app_id = row["app_id"]
            if not lens.is_real_app(app_id):
                continue
            per_hour.setdefault(row["hour"], {})
            root = lens.root(app_id)
            bucket = per_hour[row["hour"]]
            bucket[root] = bucket.get(root, 0) + row["duration_ms"]

        hours: list[dict[str, object]] = []
        for hour in range(24):
            apps = per_hour.get(hour, {})
            total_ms = sum(apps.values())
            ordered = sorted(apps.items(), key=lambda item: item[1], reverse=True)
            head, tail = ordered[:top], ordered[top:]
            by_category: dict[str, float] = {}
            for app_id, duration_ms in ordered:
                category = lens.category(app_id)
                by_category[category] = by_category.get(category, 0) + duration_ms / 1000
            hours.append(
                {
                    "hour": hour,
                    "total_seconds": round(total_ms / 1000, 1),
                    "categories": {
                        name: round(value, 1) for name, value in sorted(by_category.items())
                    },
                    "apps": [
                        {
                            "app_id": app_id,
                            "display_name": lens.name(app_id),
                            "seconds": round(duration_ms / 1000, 1),
                            "percent": formatting.percent(duration_ms, total_ms),
                        }
                        for app_id, duration_ms in head
                    ],
                    "other_seconds": round(sum(value for _id, value in tail) / 1000, 1),
                    "presses": int((presses.get(hour) or {}).get("press_count") or 0),
                }
            )
        return {"hours": hours}

    # ── 会话明细 ────────────────────────────────────────────────────────
    def sessions(
        self,
        period: Period,
        *,
        app_id: int | None = None,
        limit: int = 200,
        offset: int = 0,
        include_titles: bool = False,
        visits_only: bool = True,
    ) -> dict[str, object]:
        """会话/访问列表。

        **``window_title`` 的两道闸**：既要 ``include_titles=true``，又要设置允许记录标题。
        默认不返回是为了避免标题进入浏览器缓存与前端内存（05 文档 §3、08 文档 §2）。
        判断只在这一处，且有一条覆盖全部端点的回归测试盯住它。
        """
        titles_allowed = include_titles and self._ctx.config.privacy.record_window_titles
        lens = self._apps.lens()
        rows = self._ctx.usage_repo.sessions(
            period.start_day,
            period.end_day,
            app_id=app_id,
            visits_only=visits_only,
            limit=limit,
            offset=offset,
        )
        total = self._ctx.usage_repo.session_total(
            period.start_day, period.end_day, app_id=app_id, visits_only=visits_only
        )
        return {
            "sessions": [self._session_payload(row, lens, titles_allowed) for row in rows],
            "pagination": {"total": total, "limit": limit, "offset": offset},
            "titles_included": titles_allowed,
        }

    def _session_payload(self, row: dict, lens, titles_allowed: bool) -> dict[str, object]:
        """**不含 ``presses``。** 05 文档 §3 的示例里每条会话带按键数，但那要按会话的时间
        区间去数原始事件——一页 200 条就是 200 次范围查询，而常规查询不许扫原始表
        （01 文档 §4.1）。退而给"该应用该周期的按键数"是另一个数字戴着同一个名字，
        比不给更糟。按键与时长的交叉分析由 ``/api/v1/insights/app-keyboard`` 提供。
        """
        seconds = row["visit_duration_ms"] / 1000
        return {
            "id": row["id"],
            "app_id": row["app_id"],
            "display_name": lens.name(row["app_id"]),
            "start": _iso(row["visit_start_ts_ns"], self._ctx),
            "end": _iso(row["end_ts_ns"], self._ctx),
            "seconds": round(seconds, 1),
            "seconds_formatted": formatting.format_duration(seconds),
            "window_title": (row["window_title"] or None) if titles_allowed else None,
            "end_reason": row["end_reason"],
            "idle_trimmed": row["idle_trimmed"],
        }

    # ── 趋势 ────────────────────────────────────────────────────────────
    def trend_seconds(self, period: Period) -> dict[str, float]:
        """趋势桶 → 秒。粒度由后端按 ``range`` 决定（05 文档 §2）。"""
        if period.granularity == "hour":
            rows = self._ctx.usage_repo.hourly_apps(period.start_day, period.end_day)
            lens = self._apps.lens()
            per_hour: dict[str, float] = {}
            for row in rows:
                if not lens.is_real_app(row["app_id"]):
                    continue
                bucket = f"{row['hour']:02d}"
                per_hour[bucket] = per_hour.get(bucket, 0) + row["duration_ms"] / 1000
            return {bucket: round(value, 1) for bucket, value in per_hour.items()}
        totals = self._ctx.usage_repo.bucket_totals(
            period.granularity, *_bucket_bounds(period)
        )
        return {bucket: round(value / 1000, 1) for bucket, value in totals.items()}


def _sorted(rows: list[dict], sort: str) -> list[dict]:
    field = _SORT_KEYS.get(sort, "duration_ms")
    if field == "display_name":
        return sorted(rows, key=lambda row: (row["display_name"] or "").casefold())
    return sorted(rows, key=lambda row: row.get(field) or 0, reverse=True)


def _search(rows: list[dict], query: str) -> list[dict]:
    """按展示名 / 别名 / 进程名过滤，不区分大小写。

    在**周期口径的折叠结果**上过滤，而不是去查 ``app`` 表——搜索结果必须与列表同一套
    数字（合并过的应用是一个整体、被排除的不出现），否则"搜出来的时长"和"列表里的
    时长"是两个口径（M3 偏离 67 踩的就是这个）。行数只有几十到几百，Python 过滤足够。
    """
    needle = query.casefold()
    return [
        row
        for row in rows
        if needle in (row["display_name"] or "").casefold()
        or needle in (row.get("user_alias") or "").casefold()
        or needle in (row.get("process_name") or "").casefold()
    ]


def _bucket_bounds(period: Period) -> tuple[str, str]:
    """桶列的比较边界。月桶是 ``YYYY-MM``、年桶是 ``YYYY``，直接拿日期比会漏掉边界桶。"""
    if period.granularity == "month":
        return (period.start_day[:7], period.end_day[:7])
    if period.granularity == "year":
        return (period.start_day[:4], period.end_day[:4])
    return period.day_range


def _iso(ts_ns: int, ctx: ServiceContext) -> str:
    from datetime import datetime

    return datetime.fromtimestamp(ts_ns / 1_000_000_000, tz=ctx.timezone).isoformat(
        timespec="seconds"
    )


__all__ = ["UsageService"]
