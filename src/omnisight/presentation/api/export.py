"""导出（05 文档 §7）。流式响应，不在内存里拼整个文件。"""

from __future__ import annotations

from typing import Any

from flask import Flask, Response, request

from ...services.export import FORMATS, SCOPES
from ..validators import parse_choice
from . import resolved_period


def register(app: Flask, context: Any) -> None:
    @app.get("/api/v1/export")
    def export():
        period = resolved_period(context, request.args)
        scope = parse_choice(request.args, "scope", SCOPES, "usage")
        fmt = parse_choice(request.args, "format", FORMATS, "csv")
        service = context.services.export
        if fmt == "csv":
            stream = service.stream_csv(scope, period)
            mimetype = "text/csv; charset=utf-8"
        else:
            stream = service.stream_json(scope, period)
            mimetype = "application/json; charset=utf-8"
        filename = service.filename(scope, period, fmt)
        response = Response(stream, mimetype=mimetype)
        # 文件名里没有中文，因此不需要 RFC 5987 编码；有的话再加。
        response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        response.headers["Cache-Control"] = "no-store"
        return response


__all__ = ["register"]
