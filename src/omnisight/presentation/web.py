"""Flask 应用工厂与内嵌服务器。

用工厂而非模块级全局 app（KeyTrace 做对了，TimeLens 没有）：测试要能拿到互不
干扰的实例，而模块级全局意味着"导入即建库"。

**表现层拿到的是服务，不是仓储。** :class:`AppContext` 里没有 ``UsageRepository`` 这类
对象——分层要求表现层无法绕过服务直接查库（02 文档 §1）。M1 时它直接持有仓储，M2 起
换成 :class:`~omnisight.services.Services`。
"""

from __future__ import annotations

import logging
import mimetypes
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from flask import Flask, render_template, request, send_from_directory
from werkzeug.serving import make_server

from .. import __version__
from ..core import paths
from . import errors, security, stream
from .api import apps as apps_api
from .api import export as export_api
from .api import insights as insights_api
from .api import keyboard as keyboard_api
from .api import overview as overview_api
from .api import settings as settings_api
from .api import system as system_api
from .api import usage as usage_api
from .api.system import build_status

if TYPE_CHECKING:  # pragma: no cover
    from ..core.config import Config
    from ..services import Services
    from ..storage.database import Database

logger = logging.getLogger(__name__)

#: 注册顺序无关紧要，但集中成一张表让"新增一个面板要改哪里"只有一个答案。
API_MODULES = (
    system_api,
    overview_api,
    usage_api,
    keyboard_api,
    apps_api,
    insights_api,
    settings_api,
    export_api,
)


@dataclass(slots=True)
class AppContext:
    """交给表现层的运行时上下文。表现层只读它，不自己拼装依赖。

    ``capture`` 与 ``services`` 用 ``Any`` 持有而不是导入类型：表现层依赖
    ``core.lifecycle`` 会形成环，而它真正需要的只是 ``snapshot()`` 与服务对象。

    ``config`` 会被设置接口替换（``dataclasses.replace`` 产出新的 frozen 实例），
    因此本类**不能**是 frozen 的。
    """

    config: Config
    database: Database
    capabilities: Any
    token: str
    started_at: str
    data_dir: Any
    schema_version: int = 0
    paused: bool = False
    capture: Any = None
    services: Services | None = None
    stream: Any = None


#: 静态资源的 MIME 类型**显式注册**，不靠系统猜。
#:
#: Windows 的 ``mimetypes`` 会读 HKCR：某些安装程序把 ``.js`` 写成 ``text/plain``
#: 或 ``application/x-javascript``，而浏览器对 ES 模块严格要求 JavaScript MIME——
#: 类型不对就整页拒绝执行，症状是**空白页加一条控制台报错**，而且只在那台机器上出现。
#: 前端零构建、全靠原生模块，这条必须锁死（07 文档 §2 的代价之一）。
_STATIC_TYPES = (
    ("text/javascript", ".js"),
    ("text/css", ".css"),
    ("image/svg+xml", ".svg"),
    ("application/json", ".json"),
)


def create_app(context: AppContext) -> Flask:
    for mime_type, suffix in _STATIC_TYPES:
        mimetypes.add_type(mime_type, suffix)
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
    if context.services is not None:
        for module in API_MODULES:
            module.register(app, context)
        stream.register(app, context)
    return app


def _register_routes(app: Flask, context: AppContext) -> None:
    @app.get("/")
    def index():
        """页面外壳。**零数据、零内联脚本**——数据一律经 API 取（06 文档 §14）。

        令牌通过 URL 交给页面，页面存进 sessionStorage 后续用请求头带上
        （08 文档 §3.2b）。这里不校验，否则用户点托盘打开的链接会被自己拦掉。

        模板里不注入 capabilities：前端只信 ``/api/v1/status``，注入一份就等于
        多一个可能过期的副本（07 文档 §10）。
        """
        return render_template(
            "dashboard.html",
            version=__version__,
            token=request.args.get("token", ""),
        )

    @app.get("/favicon.svg")
    def favicon():
        """免令牌，因为它由 ``<link rel="icon">`` 发出——那条请求带不了自定义头。

        它不返回任何统计数据，因此在 ``PUBLIC_ENDPOINTS`` 里是安全的。
        """
        assets = paths.resource_dir() / "presentation" / "static" / "assets"
        return send_from_directory(str(assets), "favicon.svg")

    @app.get("/healthz")
    def healthz():
        """无需令牌的存活探针，只回一个字面量，不泄露任何信息。"""
        return {"ok": True}


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


__all__ = ["API_MODULES", "AppContext", "WebServer", "build_status", "create_app"]
