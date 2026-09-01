"""洞察接口（05 文档 §5）——合并后的核心新能力。"""

from __future__ import annotations

from typing import Any

from flask import Flask, jsonify, request

from ..validators import parse_limit
from . import envelope, resolved_period


def register(app: Flask, context: Any) -> None:
    @app.get("/api/v1/insights/app-keyboard")
    def insights_app_keyboard():
        period = resolved_period(context, request.args)
        payload = context.services.insights.app_keyboard(
            period, limit=parse_limit(request.args, default=20, maximum=200)
        )
        return jsonify({**envelope(context, period), **payload})

    @app.get("/api/v1/insights/rhythm")
    def insights_rhythm():
        period = resolved_period(context, request.args)
        payload = context.services.insights.rhythm(period)
        return jsonify({**envelope(context, period), **payload})


__all__ = ["register"]
