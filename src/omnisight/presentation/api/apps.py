"""应用管理接口（05 文档 §6）。

写操作（``PATCH`` / ``POST`` / ``DELETE``）除令牌外还校验同源
（:func:`~omnisight.presentation.validators.require_same_site`，08 文档 §3.2d），
并让相关缓存失效、递增 ``data_version``——否则用户改完别名刷新页面看到的还是旧名字。
"""

from __future__ import annotations

from typing import Any

from flask import Flask, Response, jsonify, request

from ...services.categories import CATEGORY_IDS
from ...storage.repositories.apps import UNSET
from ..errors import ApiError
from ..validators import (
    json_body,
    parse_bool,
    parse_int,
    parse_limit,
    parse_offset,
    parse_query,
    parse_sort,
    require_same_site,
)
from . import envelope

#: 图标缓存一周。图标几乎不变，而每个应用一次请求的量级下这个头很值钱（05 文档 §1.6）。
ICON_CACHE_SECONDS = 604800


def _require_real_app(app_id: int) -> None:
    """``app_id = 0`` 是"前台未知"哨兵，不是应用（04 文档 §2.2）。

    路径上的 ``<int:app_id>`` 会痛快地接受 0，而 ``app`` 表里**确实有** id = 0 那一行
    （外键完整性需要它），于是详情页会正常返回一个叫"未知"的"应用"。查询参数那一侧
    ``parse_app_id`` 早就把 0 挡掉了，路径这一侧也必须挡。
    """
    if app_id < 1:
        raise _not_found(app_id)


def register(app: Flask, context: Any) -> None:
    @app.get("/api/v1/apps")
    def apps_list():
        payload = context.services.apps.list_apps(
            query=parse_query(request.args),
            category=request.args.get("category") or None,
            include_excluded=parse_bool(request.args, "include_excluded"),
            sort=parse_sort(request.args, kind="apps"),
            limit=parse_limit(request.args, default=50),
            offset=parse_offset(request.args),
        )
        return jsonify({**envelope(context), **payload})

    @app.get("/api/v1/apps/running")
    def apps_running():
        """当前有可见窗口的应用（← 旧 ``list_visible_apps``）。"""
        return jsonify({**envelope(context), "apps": context.services.apps.running_apps()})

    @app.get("/api/v1/apps/<int:app_id>")
    def app_detail(app_id: int):
        _require_real_app(app_id)
        payload = context.services.apps.detail(app_id)
        if payload is None:
            raise _not_found(app_id)
        return jsonify({**envelope(context), **payload})

    @app.patch("/api/v1/apps/<int:app_id>")
    def app_patch(app_id: int):
        _require_real_app(app_id)
        require_same_site()
        body = json_body()
        if context.services.apps.lens().meta(app_id) is None:
            raise _not_found(app_id)
        alias = _alias_of(body)
        category = _category_of(body)
        excluded = body.get("excluded", UNSET)
        if not isinstance(excluded, (bool, type(UNSET))):
            raise ApiError("excluded 必须是 true 或 false", field="excluded")
        payload = context.services.apps.patch(
            app_id, user_alias=alias, category=category, excluded=excluded
        )
        return jsonify({**envelope(context), **payload})

    @app.post("/api/v1/apps/<int:app_id>/merge")
    def app_merge(app_id: int):
        _require_real_app(app_id)
        require_same_site()
        body = json_body()
        into = parse_int(body, "into_app_id", minimum=1)
        if into is None:
            raise ApiError("需要 into_app_id", field="into_app_id")
        if into == app_id:
            raise ApiError("不能把应用合并到它自己", field="into_app_id")
        lens = context.services.apps.lens()
        if lens.meta(app_id) is None:
            raise _not_found(app_id)
        if lens.metas.get(into) is None:
            raise _not_found(into)
        return jsonify({**envelope(context), **context.services.apps.merge(app_id, into)})

    @app.delete("/api/v1/apps/<int:app_id>/merge")
    def app_unmerge(app_id: int):
        _require_real_app(app_id)
        require_same_site()
        return jsonify({**envelope(context), **context.services.apps.merge(app_id, None)})

    @app.get("/api/v1/apps/<int:app_id>/icon")
    def app_icon(app_id: int):
        """无图标返回 204（沿用现状）。

        204 而不是 404：应用是存在的，只是没有图标——前端据此显示首字母色块，
        而 404 会让它以为请求错了（05 文档 §6）。
        """
        _require_real_app(app_id)
        png = context.services.apps.icon_bytes(app_id)
        if not png:
            return Response(status=204)
        response = Response(png, mimetype="image/png")
        response.headers["Cache-Control"] = f"private, max-age={ICON_CACHE_SECONDS}, immutable"
        return response


def _alias_of(body: dict[str, Any]):
    if "user_alias" not in body:
        return UNSET
    alias = body["user_alias"]
    if alias is not None and not isinstance(alias, str):
        raise ApiError("user_alias 必须是字符串或 null", field="user_alias")
    if isinstance(alias, str) and len(alias) > 120:
        raise ApiError("user_alias 不能超过 120 个字符", field="user_alias")
    return alias


def _category_of(body: dict[str, Any]):
    if "category" not in body:
        return UNSET
    category = body["category"]
    if category not in CATEGORY_IDS:
        raise ApiError(
            f"category 必须是 {'、'.join(CATEGORY_IDS)}", field="category"
        )
    return category


def _not_found(app_id: int) -> ApiError:
    return ApiError(
        f"没有 app_id = {app_id} 的应用", code="app_not_found", status=404, field="app_id"
    )


__all__ = ["ICON_CACHE_SECONDS", "register"]
