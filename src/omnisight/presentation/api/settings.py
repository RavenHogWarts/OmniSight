"""设置、自启与暂停（05 文档 §7）。

``GET`` 返回**足以生成表单**的元数据（取值、默认值、可选项、是否可用及原因），因此设置页
不含任何"哪个开关在哪个平台上要隐藏"的前端知识。

``PATCH`` 的响应分三档：``applied`` / ``requires_restart`` / ``rejected``。谎称已生效是
这里最糟的失败模式——用户会以为自己关掉了某项采集。
"""

from __future__ import annotations

from typing import Any

from flask import Flask, jsonify

from ...services.settings import CapabilityMissing
from ..errors import ApiError, CapabilityUnavailable
from ..validators import body_bool, json_body, parse_int, require_same_site
from . import envelope


def register(app: Flask, context: Any) -> None:
    @app.get("/api/v1/settings")
    def settings_get():
        return jsonify({**envelope(context), **context.services.settings.describe()})

    @app.patch("/api/v1/settings")
    def settings_patch():
        require_same_site()
        body = json_body()
        updates = body.get("settings") if isinstance(body.get("settings"), dict) else body
        if not isinstance(updates, dict) or not updates:
            raise ApiError("请求体需要至少一项设置", field="settings")
        result = context.services.settings.patch(updates)
        # 部分成功也返回 200：``rejected`` 里逐项说明原因，前端按字段标红。整体 4xx 会让
        # "三项里有一项越界"变成"什么都没改"，而实际上另两项已经生效了。
        return jsonify({**envelope(context), **result})

    @app.post("/api/v1/settings/autostart")
    def settings_autostart():
        require_same_site()
        enabled = body_bool(json_body(), "enabled")
        try:
            state = context.services.settings.set_autostart(enabled)
        except CapabilityMissing as exc:
            # 能力缺失本身不是错误，但"此刻就执行不了"的写操作是 422（05 文档 §1.5）。
            raise CapabilityUnavailable(exc.capability, exc.message) from exc
        except OSError as exc:
            raise ApiError(
                f"写入自启项失败：{exc}", code="internal_error", status=500
            ) from exc
        return jsonify({**envelope(context), **state})

    @app.post("/api/v1/settings/autostart-elevated")
    def settings_autostart_elevated():
        """「登录时以管理员身份启动」（Windows 的 ``/RL HIGHEST`` 登录任务，10 文档 §5.3）。

        与上面那个端点分开而不是加一个 ``elevated`` 字段：两者的机制、所需权限与失败
        原因都不同，合成一个端点会让 422 的 ``capability`` 说不清是哪一条不可用。
        """
        require_same_site()
        enabled = body_bool(json_body(), "enabled")
        try:
            state = context.services.settings.set_autostart_elevated(enabled)
        except CapabilityMissing as exc:
            raise CapabilityUnavailable(exc.capability, exc.message) from exc
        except PermissionError as exc:
            # 适配器最里面那道闸（见 logon_task.set_enabled）。走到这里说明服务层的检查
            # 与适配器的判断不一致，如实报 422 而不是 500——用户能做的事是一样的。
            raise CapabilityUnavailable("autostart_elevated", str(exc)) from exc
        except OSError as exc:
            raise ApiError(
                f"设置登录任务失败：{exc}", code="internal_error", status=500
            ) from exc
        return jsonify({**envelope(context), **state})

    @app.post("/api/v1/capture/pause")
    def capture_pause():
        """暂停/恢复采集。``duration_minutes`` 只是给 UI 显示的意图，本次运行不自动恢复。"""
        require_same_site()
        body = json_body()
        paused = body_bool(body, "paused")
        minutes = parse_int(body, "duration_minutes", default=None, minimum=1, maximum=1440)
        result = context.services.settings.patch({"capture.paused": paused})
        state = context.services.settings.set_paused(paused)
        return jsonify(
            {
                **envelope(context),
                **state,
                "duration_minutes": minutes,
                "requires_restart": result["requires_restart"],
                "auto_resume": False,
            }
        )


__all__ = ["register"]
