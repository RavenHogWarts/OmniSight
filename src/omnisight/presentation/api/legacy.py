"""旧接口兼容层（05 文档 §8、09 文档 §4，M5 交付）。

迁移期保留一个大版本：老用户可能写了脚本消费 TimeLens / KeyTrace 的公开端点，
公开记录过的接口不该无声消失。**每个端点都是新服务之上的薄适配器**——只做
参数方言 → 新参数、新响应 → 旧形状的两头改写，不允许出现自己的查询逻辑；
一旦兼容层开始自己查库，它就会在重构中被遗忘并逐渐给出与主接口不一致的答案。

令牌豁免：旧 KeyTrace 的 HTTP 客户端不知道 OmniSight 的会话令牌，这些端点按
端点名前缀（``legacy_``）免令牌。威胁模型不变（08 文档 §3）：令牌防的是网页，
而网页跨源读不到这些响应（无 CORS 头）；能直连它们的本地进程本来就能读数据库
文件。Host 校验对所有端点依然生效。

响应头统一带 ``Deprecation: true`` 与 ``Sunset``，并记录调用来源——谁还在用、
用了多少次，是"什么时候可以删"的唯一依据。
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any

from flask import Flask, Response, jsonify, request

from ... import __version__
from ...services.formatting import format_duration
from ...services.legacy import SUNSET_DATE
from ...services.period import PeriodRequest
from ..errors import ApiError
from . import resolved_period

logger = logging.getLogger(__name__)

#: TimeLens 的 ``view`` 方言 → 新 ``range``。``weekly`` 不在其中：它要保持
#: "选中日往前 6 天"的旧语义（05 文档 §8），映射成 custom。
_LEGACY_VIEWS: dict[str, str] = {
    "daily": "day",
    "monthly": "month",
    "yearly": "year",
    "total": "total",
}
_LEGACY_VIEW_NAMES = ("daily", "weekly", "monthly", "yearly", "total")

_KEYTRACE_RANGES = ("day", "week", "month", "year", "total")
_KEYTRACE_VIEWS = ("hours", "days", "months", "years")


def _date_arg(name: str = "date") -> date:
    raw = request.args.get("date", "")
    if not raw:
        return date.today()
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ApiError("date 必须使用 YYYY-MM-DD 格式", code="invalid_param",
                       field="date") from exc


def _period_for(context: Any, range_name: str, anchor: date) -> Any:
    """旧参数 → 新 :class:`PeriodRequest` 展开后的 :class:`Period`。"""
    return resolved_period(
        context, {"range": range_name, "date": anchor.isoformat()}
    )


def _legacy(payload: Any, status: int = 200) -> Response:
    response = jsonify(payload)
    response.status_code = status
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = SUNSET_DATE
    logger.info(
        "旧接口调用 %s 来自 %s",
        request.path,
        request.headers.get("User-Agent", "unknown"),
    )
    return response


def register(app: Flask, context: Any) -> None:
    services = context.services

    # ── TimeLens 方言 ─────────────────────────────────────────────────

    @app.get("/api/daily")
    def legacy_daily():
        day = _date_arg()
        return _legacy(_timelens_period_payload(context, "day", day, services))

    @app.get("/api/weekly")
    def legacy_weekly():
        """旧语义是"最近 7 天"（今天收尾的滚动窗口），不是自然周。"""
        today = _date_arg()
        period = resolved_period(
            context,
            {
                "range": "custom",
                "start": (today - timedelta(days=6)).isoformat(),
                "end": today.isoformat(),
            },
        )
        payload = _timelens_period_payload(context, "custom", today, services, period=period)
        payload["view"] = "weekly"
        return _legacy(payload)

    @app.get("/api/period")
    def legacy_period():
        view = request.args.get("view", "daily")
        if view not in _LEGACY_VIEW_NAMES:
            view = "daily"
        day = _date_arg()
        if view == "weekly":
            period = resolved_period(
                context,
                {
                    "range": "custom",
                    "start": (day - timedelta(days=6)).isoformat(),
                    "end": day.isoformat(),
                },
            )
            payload = _timelens_period_payload(context, "custom", day, services, period=period)
            payload["view"] = view
            return _legacy(payload)
        return _legacy(_timelens_period_payload(context, _LEGACY_VIEWS[view], day, services))

    @app.get("/api/hourly")
    def legacy_hourly():
        view = request.args.get("view", "daily")
        if view not in _LEGACY_VIEW_NAMES:
            view = "daily"
        day = _date_arg()
        range_name = _LEGACY_VIEWS[view]
        period = _period_for(context, range_name, day)
        timeline = services.usage.timeline(period)
        hours = [
            {
                "hour": item["hour"],
                "apps": [
                    {
                        "app_name": app["display_name"],
                        "total_seconds": app["seconds"],
                        "percentage": app["percent"],
                    }
                    for app in item["apps"]
                ],
                "categories": item["categories"],
                "total_seconds": item["total_seconds"],
            }
            for item in timeline["hours"]
        ]
        return _legacy(
            {
                "date": day.isoformat(),
                "view": view,
                "start_date": period.start_day,
                "end_date": period.end_day,
                "hours": hours,
            }
        )

    @app.get("/api/keyboard")
    def legacy_keyboard():
        view = request.args.get("view", "daily")
        if view not in _LEGACY_VIEW_NAMES:
            view = "daily"
        day = _date_arg()
        range_name = _LEGACY_VIEWS[view]
        period = _period_for(context, range_name, day)
        heatmap = services.keyboard.heatmap(period)
        timeline = services.keyboard.timeline(
            ("hours", "days"), anchor=PeriodRequest(range_name, anchor=day)
        )
        hours_view = timeline["views"]["hours"]
        hours = [
            {"hour": bucket["bucket"], "press_count": bucket.get("presses", 0)}
            for bucket in hours_view.get("buckets", [])
        ]
        daily = [
            {"date": bucket["bucket"], "press_count": bucket.get("presses", 0)}
            for bucket in timeline["views"]["days"].get("buckets", [])
        ]
        peak = max(hours, key=lambda item: item["press_count"], default=None)
        return _legacy(
            {
                "date": day.isoformat(),
                "view": view,
                "start_date": period.start_day,
                "end_date": period.end_day,
                "total_presses": heatmap["totals"]["press_count"],
                "active_keys": heatmap["totals"]["active_keys"],
                "keys": [
                    {"key_name": item["label"], "press_count": item["press_count"]}
                    for item in heatmap["keys"]
                ],
                "hours": hours,
                "daily_activity": daily,
                "peak_hour": peak["hour"] if peak and peak["press_count"] else None,
            }
        )

    @app.get("/api/dates")
    def legacy_dates():
        first, last = services.context.usage_repo.data_range()
        return _legacy({"min_date": first, "max_date": last})

    @app.get("/api/icon/<path:process_name>")
    def legacy_icon(process_name: str):
        return _icon_response(process_name, services)

    # ── KeyTrace 方言 ──────────────────────────────────────────────────

    @app.get("/api/status")
    def legacy_status():
        return _legacy(
            {
                "app": "OmniSight（KeyTrace 兼容层）",
                "version": __version__,
                "port": request.host.rsplit(":", 1)[-1] if ":" in request.host else "",
                "listener_running": True,
                "database": str(context.database.path),
                "schema_version": context.schema_version,
                "deprecation": "本接口将在 v2.0 移除，请改用 /api/v1/status",
            }
        )

    @app.get("/api/heatmap")
    def legacy_heatmap():
        range_name = request.args.get("range", "day")
        if range_name not in _KEYTRACE_RANGES:
            raise ApiError(
                "range 必须是 day、week、month、year 或 total", code="invalid_range"
            )
        day = _date_arg()
        period = _period_for(context, range_name, day)
        heatmap = services.keyboard.heatmap(period)
        return _legacy(
            {
                "range": range_name,
                "selected_date": day.isoformat(),
                "period_start": period.start_day,
                "period_end": period.end_day,
                "keys": heatmap["keys"],
            }
        )

    @app.get("/api/timeline")
    def legacy_timeline():
        view = request.args.get("view", "hours")
        if view not in _KEYTRACE_VIEWS:
            raise ApiError(
                "view 必须是 hours、days、months 或 years", code="invalid_param"
            )
        day = _date_arg()
        timeline = services.keyboard.timeline((view,), anchor=PeriodRequest("day", anchor=day))
        return _legacy(
            {
                "view": view,
                "selected_date": day.isoformat(),
                **timeline["views"][view],
            }
        )

    @app.get("/api/apps/catalog")
    def legacy_apps_catalog():
        return _legacy(_catalog_payload(services))

    @app.get("/api/apps/heatmap")
    def legacy_apps_heatmap():
        process_name = (request.args.get("process_name") or "").strip()
        if not process_name or len(process_name) > 260:
            raise ApiError("process_name 不能为空且不能超过 260 个字符",
                           code="invalid_param")
        meta = _find_by_process(services, process_name)
        period = _period_for(context, "total", _date_arg())
        heatmap = services.keyboard.heatmap(period, app_id=meta["app_id"])
        keys = [item for item in heatmap["keys"] if item["press_count"]]
        total_presses = sum(item["press_count"] for item in keys)
        duration_total = sum(item["duration_total_ms"] for item in keys)
        return _legacy(
            {
                "app": _integration_app(meta, services),
                "keys": keys,
                "total_presses": total_presses,
                "duration_total_ms": round(duration_total, 3),
                "duration_max_ms": max(
                    (item["duration_max_ms"] for item in keys), default=0.0
                ),
            }
        )

    @app.get("/api/apps/icon/<path:process_name>")
    def legacy_apps_icon(process_name: str):
        return _icon_response(process_name, services)

    # ── 集成协议（09 文档 §4：迁移期共存的关键，12 文档 M5 判据 6）────────

    @app.get("/api/integrations/keytrace/apps")
    def legacy_integration_apps():
        limit = _limit_arg(24)
        catalog = _catalog_payload(services)
        return _legacy(
            {
                "generated_at": datetime.now().astimezone().isoformat(),
                "recent": catalog["recent"][:limit],
                "most_used": catalog["most_used"][:limit],
                "running": catalog["running"][:limit],
            }
        )

    @app.get("/api/integrations/keytrace/sessions")
    def legacy_integration_sessions():
        process_name = (request.args.get("process_name") or "").strip()
        if not process_name or len(process_name) > 260:
            raise ApiError("process_name 不能为空且不能超过 260 个字符",
                           code="invalid_param")
        meta = _find_by_process(services, process_name)
        period = _period_for(context, "total", _date_arg())
        sessions = services.usage.sessions(period, app_id=meta["app_id"], limit=1000)
        intervals = _merge_intervals(
            (item["start"], item["end"]) for item in sessions["sessions"]
        )
        return _legacy(
            {
                "app": _integration_app(meta, services),
                "sessions": [
                    {"start_ts_ns": start, "end_ts_ns": end} for start, end in intervals
                ],
            }
        )


# ── 形状改写助手（不是查询逻辑）──────────────────────────────────────────


def _timelens_period_payload(
    context: Any, range_name: str, day: date, services: Any, *, period: Any = None
) -> dict[str, Any]:
    period = period or _period_for(context, range_name, day)
    apps_block = services.usage.period_apps(period, limit=500)
    total_seconds = apps_block["total_seconds"]
    apps = [
        {
            "app_name": item["display_name"],
            "process_name": item["process_name"],
            "exe_path": "",
            "total_seconds": item["seconds"],
            "session_count": item["session_count"],
            "percentage": item["percent"],
            "formatted": format_duration(item["seconds"]),
            "category": item["category"],
        }
        for item in apps_block["apps"]
    ]
    trend = services.usage.trend_seconds(period)
    grain = period.granularity
    bars = [
        {"label": bucket, "date": bucket, "total_seconds": trend.get(bucket, 0.0)}
        for bucket in trend
    ]
    return {
        "view": range_name,
        "date": day.isoformat(),
        "title": (
            f"{period.start_day} → {period.end_day}"
            if range_name != "day"
            else day.isoformat()
        ),
        "total_seconds": total_seconds,
        "total_formatted": format_duration(total_seconds),
        "app_count": apps_block["app_count"],
        "apps": apps,
        "bars": bars,
        "granularity": grain,
    }


def _catalog_payload(services: Any) -> dict[str, Any]:
    listing = services.apps.list_apps(sort="recent", limit=100)
    apps = listing["apps"]
    running_keys = {app["app_key"] for app in services.apps.running_apps()}
    by_key = {app["process_name"].casefold(): app for app in apps}
    for app in apps:
        app.setdefault("is_running", app["process_name"].casefold() in running_keys)
    recent = sorted(apps, key=lambda item: item["last_seen_at"] or "", reverse=True)
    most_used = sorted(apps, key=lambda item: item["total_seconds"], reverse=True)
    running = [by_key[key] for key in sorted(by_key) if key in running_keys]
    return {
        "generated_at": datetime.now().astimezone().isoformat(),
        "recent": [_integration_app(app, services) for app in recent],
        "most_used": [_integration_app(app, services) for app in most_used],
        "running": [_integration_app(app, services, running=True) for app in running],
    }


def _integration_app(
    item: dict[str, Any], services: Any, *, running: bool = False
) -> dict[str, Any]:
    process_name = item.get("process_name") or ""
    app_name = item.get("display_name") or process_name
    return {
        "app_name": app_name,
        "process_name": process_name,
        "exe_path": "",
        "last_used_at": item.get("last_used_at") or item.get("last_seen_at"),
        "total_seconds": item.get("total_seconds", 0) or item.get("seconds", 0),
        "session_count": item.get("session_count", 0),
        "is_running": bool(item.get("is_running", running)),
    }


def _find_by_process(services: Any, process_name: str) -> dict[str, Any]:
    listing = services.apps.list_apps(limit=1000)
    needle = process_name.casefold()
    for app in listing["apps"]:
        if (app.get("process_name") or "").casefold() == needle:
            return app
    raise ApiError("未找到该应用", code="app_not_found", status=404)


def _limit_arg(default: int) -> int:
    try:
        return max(1, min(100, int(request.args.get("limit", default))))
    except ValueError as exc:
        raise ApiError("limit 必须是整数", code="invalid_param") from exc


def _icon_response(process_name: str, services: Any) -> Response:
    meta = _find_by_process(services, process_name)
    png = services.apps.icon_bytes(meta["app_id"])
    if not png:
        response = _legacy("", status=204)
        response.headers["Cache-Control"] = "public, max-age=604800, immutable"
        return response
    response = Response(png, mimetype="image/png")
    response.headers["Cache-Control"] = "public, max-age=604800, immutable"
    return _legacy_attach(response)


def _legacy_attach(response: Response) -> Response:
    response.headers.setdefault("Deprecation", "true")
    response.headers.setdefault("Sunset", SUNSET_DATE)
    return response


def _merge_intervals(pairs: Any) -> list[list[int]]:
    """相邻/重叠的访问区间合并（09 文档 §4.3 的语义）。"""
    import datetime as dt

    intervals: list[list[int]] = []
    for start_iso, end_iso in sorted(
        pairs, key=lambda pair: pair[0]
    ):
        try:
            start = int(
                dt.datetime.fromisoformat(start_iso).timestamp() * 1_000_000_000
            )
            end = int(dt.datetime.fromisoformat(end_iso).timestamp() * 1_000_000_000)
        except (TypeError, ValueError):  # pragma: no cover - 形状防御
            continue
        if end <= start:
            continue
        if intervals and start <= intervals[-1][1]:
            intervals[-1][1] = max(intervals[-1][1], end)
        else:
            intervals.append([start, end])
    return intervals


__all__ = ["register"]
