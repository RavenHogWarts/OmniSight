"""应用时长接口（05 文档 §3）。"""

from __future__ import annotations

from typing import Any

from flask import Flask, jsonify, request

from ..validators import (
    parse_app_id,
    parse_bool,
    parse_choice,
    parse_int,
    parse_limit,
    parse_offset,
    parse_sort,
)
from . import envelope, resolved_period

#: 会话明细的默认与上限（05 文档 §3）。
SESSION_LIMIT_DEFAULT = 200
SESSION_LIMIT_MAX = 1000


def register(app: Flask, context: Any) -> None:
    @app.get("/api/v1/usage/period")
    def usage_period():
        period = resolved_period(context, request.args)
        payload = context.services.usage.period_apps(
            period,
            sort=parse_sort(request.args),
            category=request.args.get("category") or None,
            limit=parse_limit(request.args, default=50),
            offset=parse_offset(request.args),
        )
        return jsonify({**envelope(context, period), **payload})

    @app.get("/api/v1/usage/timeline")
    def usage_timeline():
        period = resolved_period(context, request.args)
        top = int(parse_int(request.args, "top", default=5, minimum=1, maximum=20))
        payload = context.services.usage.timeline(period, top=top)
        return jsonify({**envelope(context, period), **payload})

    @app.get("/api/v1/usage/sessions")
    def usage_sessions():
        period = resolved_period(context, request.args)
        payload = context.services.usage.sessions(
            period,
            app_id=parse_app_id(request.args),
            limit=parse_limit(
                request.args, default=SESSION_LIMIT_DEFAULT, maximum=SESSION_LIMIT_MAX
            ),
            offset=parse_offset(request.args),
            include_titles=parse_bool(request.args, "include_titles"),
            visits_only=parse_choice(request.args, "granularity", ("visit", "segment"), "visit")
            == "visit",
        )
        return jsonify({**envelope(context, period), **payload})


__all__ = ["SESSION_LIMIT_DEFAULT", "SESSION_LIMIT_MAX", "register"]
