"""Flask 应用工厂与内嵌服务器。

用工厂而非模块级全局 app（KeyTrace 做对了，TimeLens 没有）：测试要能拿到互不
干扰的实例，而模块级全局意味着"导入即建库"。

**表现层拿到的是服务，不是仓储。** :class:`AppContext` 里没有 ``UsageRepository`` 这类
对象——分层要求表现层无法绕过服务直接查库（02 文档 §1）。M1 时它直接持有仓储，M2 起
换成 :class:`~omnisight.services.Services`。
"""

from __future__ import annotations

import json
import logging
import mimetypes
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from flask import Flask, render_template, request, send_from_directory
from werkzeug.serving import make_server

from ..core import paths
from . import errors, security, stream
from .api import apps as apps_api
from .api import export as export_api
from .api import insights as insights_api
from .api import keyboard as keyboard_api
from .api import legacy as legacy_api
from .api import legacy_import as legacy_import_api
from .api import onboarding as onboarding_api
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
    onboarding_api,
    legacy_import_api,
    legacy_api,
)


#: Vite 产物的清单。键是相对 Vite `root`（= `frontend/`）的源码路径。
#:
#: **为什么读清单而不是写死文件名**：产物名带内容哈希，因此改一行前端不需要用户清缓存，
#: 也不会出现"新页面配旧 chunk"。代价是多这十几行——比"教用户按 Ctrl+F5"便宜。
#:
#: 位置是 `dist/manifest.json`（vite.config.ts 显式指定），不是 Vite 默认的
#: `dist/.vite/manifest.json`：setuptools 的 `**/*` 对点开头的目录不保证展开，
#: 而这份清单必须进 wheel——少了它页面就只有"产物缺失"那张卡。
BUNDLE_MANIFEST = ("dist", "manifest.json")

#: 三个页面的入口在清单里的键，也就是**相对 Vite root（`frontend/`）的源码路径**
#: （见 vite.config.ts 的 rollupOptions.input）。写在这里而不是散在三个视图函数里：
#: 改了源码路径就要同时改这三行，而它们挨着放，漏改一行会立刻看得出来。
ENTRY_DASHBOARD = "src/main.tsx"
ENTRY_SETTINGS = "src/settings.tsx"
ENTRY_ABOUT = "src/about.tsx"


@dataclass(frozen=True, slots=True)
class Bundle:
    """页面外壳需要的三样东西：入口 URL、要预载的分包 URL、样式表 URL。

    ``missing`` 为真表示还没构建（或 wheel 里没带上产物）。这时页面外壳会显示一张
    说明卡而不是白屏——白屏是最难查的一种失败，而它的成因往往只是忘了 `pnpm build`。
    那张卡的样式来自 ``static/css/shell.css``（模板只在这一种情况下加载它）：15 文档
    §11.4 之后样式表也在产物里，产物缺了它一起缺，说明卡会变成一段裸文字。
    """

    entry: str = ""
    preload: tuple[str, ...] = ()
    styles: tuple[str, ...] = ()

    @property
    def missing(self) -> bool:
        return not self.entry


def read_bundle(static_dir: Path, entry: str = ENTRY_DASHBOARD) -> Bundle:
    """从 Vite 清单里取**某一页**的入口与它的直接依赖。

    ``entry`` 是清单里的键（``ENTRY_*`` 那三个常量之一）。18 文档 批 1 之前这里按
    ``isEntry`` 取第一条——那时只有一个入口，而现在有三个："第一条"取到哪一页取决于
    Rollup 的输出顺序，也就是**三页可能都拿到同一个入口**，而症状是"设置页画出了仪表盘"。

    失败一律退化成 ``Bundle()``（``missing`` 为真）而不是抛：API 与静态资源仍然可用，
    只有页面外壳换成说明卡。构建产物缺失是**部署问题**，不该让进程起不来。
    """
    path = static_dir.joinpath(*BUNDLE_MANIFEST)
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.warning("读不到前端产物清单 %s——页面外壳会显示构建缺失说明", path)
        return Bundle()
    record = manifest.get(entry)
    if not isinstance(record, dict) or not record.get("isEntry") or not record.get("file"):
        logger.warning("产物清单 %s 里没有入口 %s——那一页会显示构建缺失说明", path, entry)
        return Bundle()
    # 入口的静态依赖用 modulepreload 提前拉，省掉"下载入口 → 解析 → 再下载依赖"这一跳。
    # 只取一层：更深的依赖由浏览器在解析 import 时自然发现，全铺开反而挤占首屏带宽。
    preload = [
        manifest[key]["file"]
        for key in record.get("imports", [])
        if isinstance(manifest.get(key), dict) and manifest[key].get("file")
    ]
    # 样式表在清单里有两种落法，两种都认：
    #
    #   * `cssCodeSplit: false`（当前配置，理由见 vite.config.ts）——整份 CSS 是一个
    #     独立资产，清单里自成一条 `style.css` 记录，**入口记录上没有 `css` 字段**。
    #   * `cssCodeSplit: true`——每个 chunk 的样式挂在自己那条记录的 `css` 数组上。
    #
    # 先读入口的 `css`（那是有序且权威的一份），没有就退回扫所有 .css 记录。不写死
    # `"style.css"` 这个键名：它是 Vite 的实现细节。三个入口共用同一份样式表
    # （`cssCodeSplit: false`，见 vite.config.ts），因此"清单里的 css 就是这一页要的 css"
    # 在多入口下仍然成立——那份 CSS 本来就是三页合并出来的。
    styles = [name for name in record.get("css", []) if isinstance(name, str)]
    if not styles:
        styles = sorted(
            value["file"]
            for value in manifest.values()
            if isinstance(value, dict) and str(value.get("file", "")).endswith(".css")
        )
    prefix = "/static/dist/"
    return Bundle(
        entry=prefix + record["file"],
        preload=tuple(prefix + f for f in preload),
        styles=tuple(prefix + f for f in styles),
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
    #: 进程级动作（重启 / 退出 / 打开目录，18 文档 批 5）。与 ``capture`` 同理用 ``Any``
    #: 持有：它的实现在 ``core.lifecycle``，而表现层导入那一层会形成环。为 ``None`` 时
    #: 对应的三个端点如实回 503——测试里的应用工厂就没有它。
    system: Any = None


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
    def shell(template: str, entry: str):
        """三个页面共用的外壳渲染（18 文档 批 1）。**零数据、零内联脚本**——数据一律经
        API 取（06 文档 §14）。

        令牌通过 URL 交给页面，页面存进 sessionStorage 后续用请求头带上
        （08 文档 §3.2b）。这里不校验，否则用户点托盘打开的链接会被自己拦掉；三个外壳
        因此都在 ``security.PUBLIC_ENDPOINTS`` 里。

        模板里不注入 capabilities：前端只信 ``/api/v1/status``，注入一份就等于
        多一个可能过期的副本（07 文档 §10）。

        ``bundle`` 是这一页的 Vite 入口（15 文档 §3.1）。**每次请求都重读清单**：开发期
        `pnpm dev` 会在后台重新构建并换掉哈希，缓存住清单就得重启进程才能看到改动。
        清单是个 4 KB 的本地文件，这一次读远比"为什么我的改动没生效"便宜。

        ``theme`` 与 ``heat`` **由服务端渲染进 ``<html>`` 的属性**（15 文档 §11.3、18 文档
        批 3）。这两档原先由一个阻塞的普通脚本 ``static/js/theme.js`` 设置：深色偏好用户
        否则会看到一帧白底（06 文档 §3.2），而 Vite 的产物一律是 ``type="module"``——模块
        天然 defer，放进构建图就等于放弃防闪白。配置里本来就有 ``ui.theme``，18 批 3 起
        又有了 ``ui.heat``（前端切换时双写，见 ``core/theme.ts``），因此让模板直接渲染
        它们：那个文件、以及它与前端重复的两个 localStorage 键名，一起消失了。
        """
        theme = context.config.ui.theme
        heat = context.config.ui.heat
        return render_template(
            template,
            # 只有显式的 light/dark 才渲染属性。``system`` 那一档由 tokens.css 的
            # ``@media (prefers-color-scheme: dark)`` 处理——写成属性反而会把它钉死在
            # 某一色，而那正是"跟随系统"要避免的。热力色同理：``blue`` 是默认值，
            # 只有 ``warm`` 需要属性（tokens.css 里 ``[data-heat="warm"]`` 是唯一选择器）。
            theme=theme if theme in ("light", "dark") else "",
            heat="warm" if heat == "warm" else "",
            token=request.args.get("token", ""),
            bundle=read_bundle(Path(app.static_folder or "."), entry),
        )

    @app.get("/")
    def index():
        """仪表盘。"""
        return shell("dashboard.html", ENTRY_DASHBOARD)

    @app.get("/settings")
    def settings_page():
        """设置页（18 文档 批 1）。

        原先是仪表盘上的一个右侧抽屉。做成独立页面之后它有了地址：托盘能直接打开它、
        段落能深链（``/settings#privacy``），而仪表盘那四条居中控件带不必为一个不看数据的
        表单让位——一个顶着日期导航的设置页正是抽屉方案换成页面的原因。
        """
        return shell("settings.html", ENTRY_SETTINGS)

    @app.get("/about")
    def about_page():
        """关于与隐私说明（18 文档 批 4、08 文档 §6.1）。

        首次运行那一次仍然是仪表盘上的模态（必须点「开始使用」才算确认）；这一页是"之后
        仍然找得到"那一半，托盘与设置页都指向它。两者共用同一份正文。
        """
        return shell("about.html", ENTRY_ABOUT)

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
