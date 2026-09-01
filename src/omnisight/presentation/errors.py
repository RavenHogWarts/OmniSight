"""统一错误响应（05 文档 §1.5）。

前端按 ``code`` 分支，不按文案分支。最重要的一条改进：**参数非法一律 400**，
不再像旧 TimeLens 的 ``_validate_date`` 那样静默回退到今天——那会同时掩盖前端
bug 与用户的真实意图。
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from flask import Flask, jsonify
from werkzeug.exceptions import HTTPException

logger = logging.getLogger(__name__)


class ApiError(Exception):
    """带结构化 ``code`` 的 API 错误。"""

    status = 400
    code = "invalid_param"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status: int | None = None,
        field: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status:
            self.status = status
        self.field = field
        self.extra = extra or {}

    def to_payload(self) -> dict[str, Any]:
        error: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.field:
            error["field"] = self.field
        error.update(self.extra)
        return {"error": error}


class CapabilityUnavailable(ApiError):
    """请求的操作依赖当前平台不具备的能力（05 文档 §1.5）。

    注意边界：**能力缺失本身不是错误**。周期查询在不支持应用归因的环境里仍返回
    200 与空数据 + ``coverage.gaps``；只有"此刻就执行不了"的写操作才用这个。
    """

    status = 422
    code = "capability_unavailable"

    def __init__(self, capability: str, message: str) -> None:
        super().__init__(message, extra={"capability": capability})


def register(app: Flask) -> None:
    @app.errorhandler(ApiError)
    def _api_error(exc: ApiError):
        return jsonify(exc.to_payload()), exc.status

    @app.errorhandler(HTTPException)
    def _http_error(exc: HTTPException):
        code = {
            400: "invalid_param",
            401: "unauthorized",
            404: "not_found",
            405: "method_not_allowed",
            421: "misdirected_request",
        }.get(exc.code or 500, "internal_error")
        payload = {"error": {"code": code, "message": exc.description or exc.name}}
        return jsonify(payload), exc.code or 500

    @app.errorhandler(Exception)
    def _unexpected(exc: Exception):
        trace_id = uuid.uuid4().hex[:12]
        # 带 trace_id 记日志、只把 id 返给前端：异常细节可能含路径等信息。
        logger.exception("未预期异常 trace_id=%s", trace_id)
        payload = {
            "error": {
                "code": "internal_error",
                "message": "服务器内部错误，详情见日志",
                "trace_id": trace_id,
            }
        }
        return jsonify(payload), 500
