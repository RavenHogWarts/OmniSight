"""历史数据导入端点（09 文档 §2 的向导后端，M5）。

五个端点对应向导的四步加撤销：``detect/preview``（步骤 1/2）、``start/progress``
（步骤 3，``DELETE`` 语义的暂停走 ``progress`` 返回的 ``busy`` + ``cancel``）、
``report``（步骤 4）、``undo``。全部是**服务层之上的薄适配**，本模块不碰 SQL。
"""

from __future__ import annotations

import logging
from typing import Any

from flask import Flask, request

from ...services.legacy import LegacyService
from ...storage.migrations.m003_import_legacy import LegacyImportError
from ..errors import ApiError

logger = logging.getLogger(__name__)

_MAX_SOURCE_LENGTH = 1024


def register(app: Flask, context: Any) -> None:
    service: LegacyService = context.services.legacy

    def _service() -> LegacyService:
        if service is None:  # pragma: no cover - 组合根保证存在
            raise ApiError("导入服务不可用", code="import_unavailable", status=503)
        return service

    def _sources_from(body: dict[str, Any]) -> dict[str, str | None]:
        raw = body.get("sources") or {}
        if not isinstance(raw, dict):
            raise ApiError("sources 必须是对象", code="invalid_param", field="sources")
        sources: dict[str, str | None] = {}
        for name in ("timelens", "keytrace"):
            value = raw.get(name)
            if value in (None, ""):
                sources[name] = None
                continue
            if not isinstance(value, str) or not value.strip():
                raise ApiError(f"sources.{name} 必须是路径字符串", code="invalid_param",
                               field=f"sources.{name}")
            if len(value) > _MAX_SOURCE_LENGTH:
                raise ApiError("路径过长", code="invalid_param", field=f"sources.{name}")
            sources[name] = value.strip()
        return sources

    @app.get("/api/v1/import/detect")
    def import_detect():
        """默认路径探测。结果同时用于首页横幅与向导步骤 1。"""
        return {"detected": _service().detect()}

    @app.post("/api/v1/import/preview")
    def import_preview():
        body = _json_body()
        sources = _sources_from(body)
        try:
            preview = _service().preview(sources)
        except LegacyImportError as exc:
            raise ApiError(str(exc), code="invalid_source", status=400) from exc
        return preview

    @app.post("/api/v1/import/start")
    def import_start():
        body = _json_body()
        sources = _sources_from(body)
        losses = body.get("losses")
        if losses is not None and not isinstance(losses, list):
            raise ApiError("losses 必须是数组", code="invalid_param", field="losses")
        try:
            return _service().start(sources, losses=losses)
        except LegacyImportError as exc:
            raise ApiError(str(exc), code="import_conflict", status=409) from exc

    @app.get("/api/v1/import/progress")
    def import_progress():
        return _service().status()

    @app.post("/api/v1/import/cancel")
    def import_cancel():
        return _service().cancel()

    @app.post("/api/v1/import/undo")
    def import_undo():
        try:
            return _service().undo()
        except LegacyImportError as exc:
            raise ApiError(str(exc), code="undo_conflict", status=409) from exc

    @app.get("/api/v1/import/report")
    def import_report():
        report = _service().report()
        if report is None:
            raise ApiError("还没有可用的导入报告", code="report_unavailable", status=404)
        return report

    def _json_body() -> dict[str, Any]:
        body = request.get_json(silent=True)
        return body if isinstance(body, dict) else {}


__all__ = ["register"]
