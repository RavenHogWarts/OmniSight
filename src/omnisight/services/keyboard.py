"""键盘服务：布局、热力图、时间线、单键详情、人体工学（05 文档 §4）。

**布局是数据。** 旧 KeyTrace 把 104 键写死成 860 行 HTML，欧洲键盘用户因此一直看着错误
的布局图。这里由 :mod:`omnisight.capture.layouts` 下发，前端零坐标数据。

**``keys`` 始终返回当前布局族的全部键位**（沿用 KeyTrace 的"全键返回"），未使用的键各
指标为 0——前端只按 ``id`` 匹配填色，不必处理缺项。而**有数据但不在布局里的键**进
``orphan_keys``：换过键盘、跨机器共用一个库、Mac 的 F13–F19 都会产生这类数据，旧设计会
让它们在 UI 上凭空消失且总数对不上账。

**``scale.p95``**：空格键往往是第二名的 3 倍，用最大值归一会把其余键压成一片浅色。
"""

from __future__ import annotations

from datetime import date, timedelta

from ..capture import keymap, layouts
from . import formatting
from .apps import AppService
from .context import ServiceContext
from .period import Period, PeriodRequest

METRICS: tuple[str, ...] = (
    "press_count",
    "duration_total_ms",
    "duration_avg_ms",
    "duration_max_ms",
)

TIMELINE_VIEWS: tuple[str, ...] = ("hours", "days", "months", "years")

#: ``days`` 视图回看多久。365 天正好铺满一张日历热图（06 文档 §7 的"近 365 天"）。
DAYS_VIEW_SPAN = 365
MONTHS_VIEW_SPAN = 12

_ZERO_METRICS: dict[str, float] = {
    "press_count": 0,
    "duration_total_ms": 0.0,
    "duration_avg_ms": 0.0,
    "duration_max_ms": 0.0,
}


class KeyboardService:
    __slots__ = ("_apps", "_ctx")

    def __init__(self, ctx: ServiceContext, apps: AppService) -> None:
        self._ctx = ctx
        self._apps = apps

    # ── 布局 ────────────────────────────────────────────────────────────
    def resolve_family(self, requested: str | None = None) -> tuple[str, str, list[dict]]:
        """返回 ``(family, source, warnings)``。

        ``source`` 让 UI 能说明"为什么显示这个布局"（05 文档 §4）。配置里若指定了一个
        **尚未实现**的族（``tkl87`` / ``mac_*`` 属于 M8/M9），如实退回平台默认值并给一条
        warning——静默换布局会让用户以为设置没保存。
        """
        warnings: list[dict] = []
        platform_default = layouts.default_family(self._ctx.capabilities.platform_id)
        configured = self._ctx.config.ui.keyboard_layout
        if requested:
            if requested not in layouts.FAMILIES:
                raise ValueError(requested)
            return (requested, "request_override", warnings)
        if configured and configured != "auto":
            if configured in layouts.FAMILIES:
                return (configured, "user_override", warnings)
            warnings.append(
                {
                    "code": "layout_not_implemented",
                    "message": f"布局族 {configured} 尚未实现，已回退到 {platform_default}",
                }
            )
        return (platform_default, "platform_default", warnings)

    def layout(self, requested: str | None = None) -> dict[str, object]:
        family, source, warnings = self.resolve_family(requested)
        payload = layouts.FAMILIES[family].to_dict(source=source)
        payload["warnings"] = warnings
        payload["available_families"] = list(layouts.IMPLEMENTED_FAMILIES)
        return payload

    # ── 指标取数 ────────────────────────────────────────────────────────
    def metrics(self, period: Period, app_id: int | None = None) -> dict[str, dict]:
        """键 → 四个指标。``app_id`` 走应用维度聚合表（合并的最大收益点）。

        合并过的应用要把成员的数据一并算进来：聚合表里成员仍是独立的 ``app_id``，
        折叠只发生在服务层（见 :class:`~omnisight.services.apps.AppLens`）。
        """
        key = ("keyboard.metrics", period.range, period.day_range, app_id)
        return self._ctx.cached(key, lambda: self._metrics(period, app_id))

    def _metrics(self, period: Period, app_id: int | None) -> dict[str, dict]:
        if app_id is None:
            if period.range == "total":
                return self._ctx.key_repo.metrics_total()
            return self._ctx.key_repo.metrics_for_range(period.start_day, period.end_day)
        merged: dict[str, dict] = {}
        for member in self._members(app_id):
            if period.range == "total":
                part = self._ctx.key_repo.metrics_total(app_id=member)
            else:
                part = self._ctx.key_repo.metrics_for_range(
                    period.start_day, period.end_day, app_id=member
                )
            _merge_metrics(merged, part)
        return merged

    def _members(self, app_id: int) -> set[int]:
        lens = self._apps.lens()
        return {app_id, *(member for member, root in lens.merges.items() if root == app_id)}

    # ── 热力图 ──────────────────────────────────────────────────────────
    def heatmap(
        self, period: Period, *, metric: str = "press_count", app_id: int | None = None
    ) -> dict[str, object]:
        family, source, warnings = self.resolve_family()
        layout = layouts.FAMILIES[family]
        data = self.metrics(period, app_id)
        layout_ids = layout.key_ids

        keys = [self._key_payload(key_id, data.get(key_id)) for key_id in sorted(layout_ids)]
        orphans = [
            self._key_payload(key_id, values)
            for key_id, values in sorted(data.items())
            if key_id not in layout_ids and (values.get("press_count") or 0) > 0
        ]
        _rank(keys + orphans, metric)
        total_presses = sum(int(item["press_count"]) for item in keys + orphans)
        total_duration = sum(float(item["duration_total_ms"]) for item in keys + orphans)
        values = [float(item[metric]) for item in keys + orphans if item[metric]]
        for item in keys + orphans:
            item["percent"] = formatting.percent(item["press_count"], total_presses)
        return {
            "metric": metric,
            "layout_family": family,
            "layout_source": source,
            "scope": self._scope(app_id),
            "totals": {
                "press_count": total_presses,
                "active_keys": sum(1 for item in keys + orphans if item["press_count"]),
                "duration_total_ms": round(total_duration, 1),
                "duration_avg_ms": formatting.average(total_duration, total_presses),
                "duration_max_ms": max(
                    (float(item["duration_max_ms"]) for item in keys + orphans), default=0.0
                ),
            },
            "scale": {
                "metric": metric,
                "min": 0,
                "max": round(max(values, default=0.0), 1),
                "p95": round(formatting.percentile(values, 0.95), 1),
            },
            "keys": keys,
            "orphan_keys": orphans,
            "warnings": warnings,
        }

    def _key_payload(self, key_id: str, values: dict | None) -> dict[str, object]:
        definition = keymap.KEY_BY_ID.get(key_id)
        metrics = values or _ZERO_METRICS
        return {
            "id": key_id,
            "label": keymap.label_for(key_id),
            "finger": definition.finger if definition else "unknown",
            "row": definition.row if definition else "unknown",
            "press_count": int(metrics.get("press_count") or 0),
            "duration_total_ms": round(float(metrics.get("duration_total_ms") or 0.0), 1),
            "duration_avg_ms": round(float(metrics.get("duration_avg_ms") or 0.0), 1),
            "duration_max_ms": round(float(metrics.get("duration_max_ms") or 0.0), 1),
        }

    def _scope(self, app_id: int | None) -> dict[str, object]:
        if app_id is None:
            return {"type": "all"}
        return {
            "type": "app",
            "app_id": app_id,
            "display_name": self._apps.lens().name(app_id),
        }

    # ── 时间线 ──────────────────────────────────────────────────────────
    def timeline(
        self,
        views: tuple[str, ...],
        *,
        anchor: PeriodRequest,
        metric: str = "press_count",
        app_id: int | None = None,
    ) -> dict[str, object]:
        """一次取回多个视图，把 KeyTrace 首屏的 4 个请求合成 1 个（05 文档 §4）。"""
        today = self._ctx.today()
        day = self._ctx.resolve_period(anchor).anchor
        payload: dict[str, object] = {"metric": metric, "views": {}}
        warnings: list[dict] = []
        for view in views:
            if view == "hours":
                block = self._hours_view(day, app_id, warnings)
            elif view == "days":
                block = self._range_view(
                    "day", day - timedelta(days=DAYS_VIEW_SPAN - 1), min(day, today), app_id
                )
            elif view == "months":
                block = self._months_view(day, app_id)
            else:
                block = self._years_view(app_id)
            payload["views"][view] = block
        payload["warnings"] = warnings
        return payload

    def _hours_view(self, day, app_id: int | None, warnings: list[dict]) -> dict[str, object]:
        """24 小时分布。

        限定应用时 ``agg_key_hour`` 没有应用维度，只能回溯原始事件——这是 01 文档 §4.1
        允许的例外（带单日时间窗上限）。原始事件被关掉时如实报"该视图不可用"，
        **不画一张全 0 的图**：那会让用户以为自己那天在这个应用里没按过键。
        """
        iso = day.isoformat()
        if app_id is None:
            metrics = self._ctx.key_repo.hourly_metrics(iso, iso)
            counts = {hour: values["press_count"] for hour, values in metrics.items()}
            durations = {hour: values["duration_total_ms"] for hour, values in metrics.items()}
        else:
            counts = {}
            durations = {}
            available = False
            for member in self._members(app_id):
                part = self._ctx.insight_repo.app_hourly_presses(
                    iso, member, self._ctx.timezone
                )
                if part is None:
                    continue
                available = True
                for hour, value in part.items():
                    counts[hour] = counts.get(hour, 0) + value
            if not available:
                warnings.append(
                    {
                        "code": "hour_view_unavailable_for_app",
                        "message": "按小时的应用维度分布需要原始按键事件，当前设置未保留",
                    }
                )
                return {"available": False, "period": {"start": iso, "end": iso}, "buckets": []}
        buckets = [
            {
                "bucket": f"{hour:02d}",
                "label": f"{hour}:00",
                "press_count": int(counts.get(hour, 0)),
                "duration_total_ms": round(float(durations.get(hour, 0.0)), 1),
                "duration_avg_ms": formatting.average(
                    float(durations.get(hour, 0.0)), int(counts.get(hour, 0))
                ),
            }
            for hour in range(24)
        ]
        return {
            "available": True,
            "period": {"start": iso, "end": iso},
            "buckets": buckets,
            "scale": _scale_of(buckets, "press_count"),
        }

    def _range_view(self, grain: str, start, end, app_id: int | None) -> dict[str, object]:
        from . import period as period_module

        if end < start:
            end = start
        request = PeriodRequest("custom", start=start, end=end)
        window = period_module.resolve(request, today=self._ctx.today())
        data = self._bucket_metrics(grain, window, app_id)
        # 桶列表必须按 ``grain`` 生成，不能按 ``window.granularity``——``custom`` 区间的
        # 粒度恒为 ``day``，用它去匹配月/年数据会让整个视图静默变成全 0。
        buckets = [
            {"bucket": bucket, "label": label, **_bucket_payload(data.get(bucket))}
            for bucket, label in period_module.buckets_for(
                grain, window.start, window.truncated_end
            )
        ]
        return {
            "available": True,
            "period": {"start": window.start_day, "end": window.end_day},
            "buckets": buckets,
            "scale": _scale_of(buckets, "press_count"),
        }

    def _bucket_metrics(self, grain: str, window: Period, app_id: int | None) -> dict[str, dict]:
        if app_id is None:
            return self._ctx.key_repo.bucket_metrics(
                grain, *_grain_bounds(grain, window)
            )
        merged: dict[str, dict] = {}
        for member in self._members(app_id):
            _merge_metrics(
                merged,
                self._ctx.key_repo.bucket_metrics(
                    grain, *_grain_bounds(grain, window), app_id=member
                ),
            )
        return merged

    def _months_view(self, day, app_id: int | None) -> dict[str, object]:
        from . import period as period_module

        start = period_module.month_start(day)
        for _ in range(MONTHS_VIEW_SPAN - 1):
            start = period_module.month_start(start - timedelta(days=1))
        return self._range_view("month", start, period_module.month_end(day), app_id)

    def _years_view(self, app_id: int | None) -> dict[str, object]:
        from . import period as period_module

        first, last = self._ctx.usage_repo.data_range()
        today = self._ctx.today()
        first_year = period_module.parse_date(first).year if first else today.year
        last_year = period_module.parse_date(last).year if last else today.year
        start = date(first_year, 1, 1)
        end = date(last_year, 12, 31)
        return self._range_view("year", start, min(end, today), app_id)

    # ── 单键详情 ────────────────────────────────────────────────────────
    def key_detail(
        self, key_id: str, period: Period, app_id: int | None = None
    ) -> dict[str, object]:
        """★ 反向分析："这个键主要在哪些应用里被按"。两个旧项目都做不到。

        ``app_id`` 让详情跟着热力图的范围走。**没有它就会出现一种无声的不一致**：
        范围切到 VS Code 时热图是 VS Code 的，点开某个键看到的数字却是全部应用的，
        而界面上没有任何提示（14 文档 §2.8）。

        范围限定时 ``by_app`` 只剩这一个应用——"这个键主要被哪些应用按"这个问题在
        范围限定后已经被范围本身回答了，再列全部应用会与 ``totals`` 对不上账。
        """
        definition = keymap.KEY_BY_ID.get(key_id)
        metrics = self.metrics(period, app_id).get(key_id) or dict(_ZERO_METRICS)
        lens = self._apps.lens()
        by_app_raw = self._ctx.key_repo.apps_for_key_range(
            key_id, period.start_day, period.end_day, limit=50
        )
        folded = lens.fold_counts(
            {row["app_id"]: row["press_count"] for row in by_app_raw}, keep_unknown=True
        )
        if app_id is not None:
            members = self._members(app_id)
            folded = {
                root: count
                for root, count in folded.items()
                if root == app_id or root in members
            }
        total = sum(folded.values())
        by_app = [
            {
                "app_id": row_app_id,
                "display_name": lens.name(row_app_id),
                "press_count": count,
                "percent": formatting.percent(count, total),
            }
            for row_app_id, count in sorted(folded.items(), key=lambda item: item[1], reverse=True)
        ]
        hourly = self._ctx.key_repo.hourly_metrics(
            period.start_day, period.end_day, key_id=key_id
        )
        return {
            "key": {
                "id": key_id,
                "label": keymap.label_for(key_id),
                "finger": definition.finger if definition else "unknown",
                "finger_name": keymap.FINGER_NAMES.get(
                    definition.finger if definition else "", ""
                ),
                "row": definition.row if definition else "unknown",
                "row_name": keymap.ROW_NAMES.get(definition.row if definition else "", ""),
                "hid_usage": definition.hid_usage if definition else None,
                "in_layout": key_id in layouts.FAMILIES[self.resolve_family()[0]].key_ids,
            },
            "scope": self._scope(app_id),
            "totals": {
                "press_count": int(metrics.get("press_count") or 0),
                "duration_total_ms": round(float(metrics.get("duration_total_ms") or 0.0), 1),
                "duration_avg_ms": round(float(metrics.get("duration_avg_ms") or 0.0), 1),
                "duration_max_ms": round(float(metrics.get("duration_max_ms") or 0.0), 1),
            },
            "by_app": by_app,
            "by_hour": [
                {"hour": hour, "press_count": int((hourly.get(hour) or {}).get("press_count") or 0)}
                for hour in range(24)
            ],
        }

    # ── 人体工学 ────────────────────────────────────────────────────────
    def ergonomics(self, period: Period, app_id: int | None = None) -> dict[str, object]:
        """左右手 / 手指 / 行分布 / 修饰键占比（05 文档 §4）。

        **``hands`` 不含空格。** 空格由拇指按下，通常是第一大键；把它算给某一只手会让
        "左右手负荷"这个指标失去意义。它单独计入 ``neutral``，因此
        ``left + right + neutral == 有指法归属的按键总数``，用户能对上账。

        **``modifier_ratio`` 的口径**：修饰键**自身**被按下的次数，不是"按某个键时按住了
        修饰键"。后者需要和弦信息，而我们不记录按键顺序（08 文档 §2）。
        """
        data = self.metrics(period, app_id)
        by_finger: dict[str, int] = {}
        by_row: dict[str, int] = {}
        hands = {"left": 0, "right": 0, "neutral": 0}
        modifier = 0
        total = 0
        for key_id, values in data.items():
            count = int(values.get("press_count") or 0)
            if count <= 0:
                continue
            total += count
            definition = keymap.KEY_BY_ID.get(key_id)
            if definition is None:
                continue
            by_finger[definition.finger] = by_finger.get(definition.finger, 0) + count
            by_row[definition.row] = by_row.get(definition.row, 0) + count
            hand = keymap.FINGER_HANDS.get(definition.finger, "neutral")
            hands[hand] = hands.get(hand, 0) + count
            if key_id in keymap.MODIFIER_KEYS:
                modifier += count
        sided = hands["left"] + hands["right"]
        return {
            "scope": self._scope(app_id),
            "hands": {
                "left": hands["left"],
                "right": hands["right"],
                "neutral": hands["neutral"],
                "balance_percent": formatting.percent(hands["left"], sided),
            },
            "fingers": [
                {
                    "id": finger,
                    "name": name,
                    "hand": keymap.FINGER_HANDS[finger],
                    "press_count": by_finger.get(finger, 0),
                    "percent": formatting.percent(by_finger.get(finger, 0), total),
                }
                for finger, name, _hand in keymap.FINGERS
            ],
            "rows": [
                {
                    "id": row,
                    "name": name,
                    "press_count": by_row.get(row, 0),
                    "percent": formatting.percent(by_row.get(row, 0), total),
                }
                for row, name in keymap.ROWS
            ],
            "modifier_ratio": {
                "with_modifier": modifier,
                "plain": total - modifier,
                "percent": formatting.percent(modifier, total),
                "basis": "modifier_keys_pressed",
            },
            "total_presses": total,
        }

    # ── 概览卡片 ────────────────────────────────────────────────────────
    def summary(self, period: Period) -> dict[str, object]:
        data = self.metrics(period)
        total = sum(int(values.get("press_count") or 0) for values in data.values())
        duration = sum(float(values.get("duration_total_ms") or 0.0) for values in data.values())
        active = sum(1 for values in data.values() if (values.get("press_count") or 0) > 0)
        peak = self._ctx.key_repo.minute_peak(period.start_day, period.end_day)
        previous = self._ctx.previous_period(period)
        previous_total = 0
        if previous is not None:
            previous_total = sum(
                int(values.get("press_count") or 0)
                for values in self.metrics(previous).values()
            )
        change = formatting.delta(total, previous_total)
        return {
            "total_presses": total,
            "active_keys": active,
            "duration_total_ms": round(duration, 1),
            "duration_avg_ms": formatting.average(duration, total),
            "kpm_peak": peak["press_count"] if peak else 0,
            "delta_vs_previous": (
                {"presses": int(change["value"]), "percent": change["percent"]}
                if previous is not None
                else None
            ),
        }


def _merge_metrics(target: dict[str, dict], part: dict[str, dict]) -> None:
    """把另一份"键 → 指标"合进来。次数与总时长相加，最大值取大，均值重算。"""
    for key_id, values in part.items():
        slot = target.get(key_id)
        if slot is None:
            target[key_id] = dict(values)
            continue
        slot["press_count"] += values.get("press_count") or 0
        slot["duration_total_ms"] += values.get("duration_total_ms") or 0.0
        slot["duration_max_ms"] = max(
            slot.get("duration_max_ms") or 0.0, values.get("duration_max_ms") or 0.0
        )
        slot["duration_avg_ms"] = formatting.average(
            slot["duration_total_ms"], slot["press_count"]
        )


def _rank(items: list[dict], metric: str) -> None:
    """按所选指标写 ``rank``。0 值不给排名——"并列第 87 名"没有信息量。"""
    ordered = sorted(items, key=lambda item: float(item.get(metric) or 0), reverse=True)
    for index, item in enumerate(ordered, start=1):
        item["rank"] = index if float(item.get(metric) or 0) > 0 else None


def _bucket_payload(values: dict | None) -> dict[str, object]:
    metrics = values or _ZERO_METRICS
    return {
        "press_count": int(metrics.get("press_count") or 0),
        "duration_total_ms": round(float(metrics.get("duration_total_ms") or 0.0), 1),
        "duration_avg_ms": round(float(metrics.get("duration_avg_ms") or 0.0), 1),
        "duration_max_ms": round(float(metrics.get("duration_max_ms") or 0.0), 1),
    }


def _scale_of(buckets: list[dict], metric: str) -> dict[str, float]:
    values = [float(bucket[metric]) for bucket in buckets if bucket.get(metric)]
    return {
        "min": 0,
        "max": round(max(values, default=0.0), 1),
        "p95": round(formatting.percentile(values, 0.95), 1),
    }


def _grain_bounds(grain: str, window: Period) -> tuple[str, str]:
    if grain == "month":
        return (window.start_day[:7], window.end_day[:7])
    if grain == "year":
        return (window.start_day[:4], window.end_day[:4])
    return window.day_range


__all__ = ["DAYS_VIEW_SPAN", "METRICS", "MONTHS_VIEW_SPAN", "TIMELINE_VIEWS", "KeyboardService"]
