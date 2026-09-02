"""首次运行说明（08 文档 §6.1，05 文档没有定义的新端点组）。

两条：``GET`` 取内容与"要不要显示"，``POST /ack`` 记下已读。

为什么"要不要显示"由后端判定而不是前端存 localStorage：localStorage 按浏览器与
用户配置文件隔离，换个浏览器打开仪表盘就会被再问一次，而"我已经知道这程序记录
什么了"是一条属于这台机器上这份数据的事实，不是属于某个浏览器的偏好。
（导入向导的横幅关闭状态用 localStorage 是对的——那只是一次提醒的去重。）

``ack`` 走 ``require_same_site``：它是写操作，与设置接口同一档。
"""

from __future__ import annotations

from typing import Any

from flask import Flask, jsonify

from ..validators import require_same_site
from . import envelope


def register(app: Flask, context: Any) -> None:
    @app.get("/api/v1/onboarding")
    def onboarding_get():
        return jsonify({**envelope(context), **context.services.onboarding.describe()})

    @app.post("/api/v1/onboarding/ack")
    def onboarding_ack():
        require_same_site()
        acknowledged_at = context.services.onboarding.acknowledge()
        return jsonify(
            {
                **envelope(context),
                "acknowledged_at": acknowledged_at,
                "required": False,
            }
        )


__all__ = ["register"]
