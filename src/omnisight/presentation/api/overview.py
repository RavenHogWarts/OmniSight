"""``GET /api/v1/overview`` —— 首屏唯一的数据请求（05 文档 §2）。

旧 TimeLens 首屏发 3 个请求、旧 KeyTrace 发 5 个，且它们返回的数据高度重叠。这里合成
一个，并支持 ``?include=`` 裁剪：轮询时只取变化的段，而不是每次重算整屏。

它不属于 ``usage.py`` 也不属于 ``keyboard.py``——概览横跨三个服务，因此单独一个模块
（02 文档 §2 的目录树里没有它，是实现时才浮现的需求）。
"""

from __future__ import annotations

from typing import Any

from flask import Flask, jsonify, request

from ...services import OVERVIEW_SECTIONS
from ..validators import parse_include
from . import envelope, resolved_period


def register(app: Flask, context: Any) -> None:
    @app.get("/api/v1/overview")
    def overview():
        period = resolved_period(context, request.args)
        include = parse_include(request.args, OVERVIEW_SECTIONS)
        payload = context.services.overview(period, include=include)
        return jsonify({**envelope(context, period), **payload, "included": list(include)})


__all__ = ["register"]
