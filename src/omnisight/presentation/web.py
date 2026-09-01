"""Flask 应用工厂与内嵌服务器。

用工厂而非模块级全局 app（KeyTrace 做对了，TimeLens 没有）：测试要能拿到互不
干扰的实例，而模块级全局意味着"导入即建库"。
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from flask import Flask, jsonify, render_template, request
from werkzeug.serving import make_server

from .. import __version__
from ..core import paths
from . import errors, security

if TYPE_CHECKING:  # pragma: no cover
    from ..core.config import Config
    from ..storage.database import Database

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AppContext:
    """交给表现层的运行时上下文。表现层只读它，不自己拼装依赖。"""

    config: Config
    database: Database
    capabilities: Any
    token: str
    started_at: str
    data_dir: Any
    schema_version: int = 0
    paused: bool = False


def create_app(context: AppContext) -> Flask:
    resources = paths.resource_dir() / "presentation"
    app = Flask(
        __name__,
        template_folder=str(resources / "templates"),
        static_folder=str(resources / "static"),
        static_url_path="/static",
    )
    app.config["OMNISIGHT"] = context
    # 响应里有中文（错误文案、降级说明），转义成 \uXXXX 会让接口难以直接阅读。
    app.json.ensure_ascii = False

    errors.register(app)
    security.install(app, token=context.token)
    _register_routes(app, context)
    return app


def _register_routes(app: Flask, context: AppContext) -> None:
    @app.get("/")
    def index():
        # 令牌通过 URL 交给页面，页面存进 sessionStorage 后续用请求头带上
        # （08 文档 §3.2b）。这里不校验，否则用户点托盘打开的链接会被自己拦掉。
        return render_template(
            "placeholder.html",
            version=__version__,
            token=request.args.get("token", ""),
            capabilities=context.capabilities,
        )

    @app.get("/healthz")
    def healthz():
        """无需令牌的存活探针，只回一个字面量，不泄露任何信息。"""
        return {"ok": True}

    @app.get("/api/v1/status")
    def status():
        return jsonify(build_status(context))


def build_status(context: AppContext) -> dict[str, Any]:
    """``/api/v1/status`` 的响应体（05 文档 §7）。

    ``capabilities`` 是前端**唯一**的降级依据；``platform`` 仅用于展示与排查，
    不参与任何逻辑分支。
    """
    caps = context.capabilities
    database_path = context.database.path
    return {
        "app": "OmniSight",
        "version": __version__,
        "port": context.config.server.port,
        "started_at": context.started_at,
        "platform": {
            "id": caps.platform_id,
            "tier": caps.tier,
            "os_version": caps.os_version,
        },
        "capabilities": caps.to_dict(),
        "capture": {
            "foreground": {"running": False, "backend": "none"},
            "keyboard": {"running": False, "backend": caps.keyboard_backend},
            "paused": context.paused,
            "queue_depth": 0,
            "dropped_events": 0,
        },
        "database": {
            "path": str(database_path),
            "schema_version": context.schema_version,
            "size_bytes": database_path.stat().st_size if database_path.exists() else 0,
        },
        "paths": paths.describe(),
        "data_range": {"min_date": None, "max_date": None},
        "data_version": int(context.database.meta_get("data_version", "0") or 0),
        "degraded": [_notice_to_dict(notice) for notice in caps.degraded],
        "warnings": [],
    }


def _notice_to_dict(notice: Any) -> dict[str, Any]:
    return {
        "code": notice.code,
        "severity": notice.severity,
        "title": notice.title,
        "detail": notice.detail,
        "hint": notice.hint,
        "docs": notice.docs,
    }


class WebServer:
    """在后台线程里跑 werkzeug 服务器。

    用 ``make_server`` 而不是 ``app.run()``：后者没有可编程的关闭入口，只能靠
    进程退出，而我们需要在托盘"退出"时干净地停下来（02 文档 §5.2）。
    """

    __slots__ = ("_app", "_server", "_thread")

    def __init__(self, app: Flask, host: str, port: int) -> None:
        self._app = app
        self._server = make_server(host, port, app, threaded=True)
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        return int(self._server.server_port)

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._server.serve_forever, name="web", daemon=True
        )
        self._thread.start()
        logger.info("Web 服务已监听 %s", self.port)

    def stop(self, timeout: float = 5.0) -> None:
        self._server.shutdown()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None
        self._server.server_close()
