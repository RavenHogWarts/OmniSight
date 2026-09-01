"""键盘接口（05 文档 §4）。

``/keyboard/layout`` 是布局的唯一真源：前端不内置任何键位坐标。请求一个尚未实现的
布局族返回 400 并列出可选值——静默换成别的族会让"我明明选了 ISO"变成一个无法排查的
问题。
"""

from __future__ import annotations

from typing import Any

from flask import Flask, jsonify, request

from ...capture import layouts
from ..errors import ApiError
from ..validators import parse_app_id, parse_key_id, parse_metric, parse_period, parse_views
from . import envelope, resolved_period


def register(app: Flask, context: Any) -> None:
    @app.get("/api/v1/keyboard/layout")
    def keyboard_layout():
        requested = (request.args.get("family") or "").strip() or None
        try:
            payload = context.services.keyboard.layout(requested)
        except ValueError as exc:
            raise ApiError(
                "尚未实现的键盘布局族，可选："
                f"{'、'.join(layouts.IMPLEMENTED_FAMILIES)}",
                code="invalid_param",
                field="family",
                extra={"requested": str(exc)},
            ) from exc
        return jsonify(payload)

    @app.get("/api/v1/keyboard/heatmap")
    def keyboard_heatmap():
        period = resolved_period(context, request.args)
        payload = context.services.keyboard.heatmap(
            period,
            metric=parse_metric(request.args),
            app_id=parse_app_id(request.args),
        )
        warnings = payload.pop("warnings", [])
        return jsonify({**envelope(context, period, warnings=warnings), **payload})

    @app.get("/api/v1/keyboard/timeline")
    def keyboard_timeline():
        anchor = parse_period(request.args)
        payload = context.services.keyboard.timeline(
            parse_views(request.args),
            anchor=anchor,
            metric=parse_metric(request.args),
            app_id=parse_app_id(request.args),
        )
        warnings = payload.pop("warnings", [])
        return jsonify({**envelope(context, warnings=warnings), **payload})

    @app.get("/api/v1/keyboard/keys/<key_id>")
    def keyboard_key(key_id: str):
        period = resolved_period(context, request.args)
        payload = context.services.keyboard.key_detail(parse_key_id(key_id), period)
        return jsonify({**envelope(context, period), **payload})

    @app.get("/api/v1/keyboard/ergonomics")
    def keyboard_ergonomics():
        period = resolved_period(context, request.args)
        payload = context.services.keyboard.ergonomics(period, parse_app_id(request.args))
        return jsonify({**envelope(context, period), **payload})


__all__ = ["register"]
