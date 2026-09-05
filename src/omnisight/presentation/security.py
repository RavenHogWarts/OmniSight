"""本机绑定与访问控制（08 文档 §3）。

威胁模型只有两个真实对手，都来自浏览器：

1. **任意网页**向 ``http://127.0.0.1:6100/api/...`` 发请求。对策是会话令牌 +
   自定义请求头——自定义头会触发 CORS 预检，而我们不返回任何
   ``Access-Control-Allow-*``，跨源请求在浏览器层就失败。
2. **DNS rebinding**：恶意域名解析到 127.0.0.1，绕过同源策略。对策是校验
   ``Host`` 头，只接受回环名称。

同机恶意程序不在对策范围内：它有本用户的文件权限，能直接读数据库文件，令牌
拦不住它（08 文档 §3.3 已就此说明为何不做数据库加密）。
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import secrets
import stat
from pathlib import Path

from flask import Flask, request
from werkzeug.exceptions import Unauthorized

logger = logging.getLogger(__name__)

ALLOWED_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "[::1]"})
TOKEN_HEADER = "X-OmniSight-Token"
RUNTIME_FILENAME = "runtime.json"

CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self'; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'none'; "
    "form-action 'none'"
)

#: 无需令牌的端点：只有**页面外壳**与静态资源。它们不返回任何统计数据。
#:
#: 三个外壳都在里面（18 文档 批 1）：令牌只在打开时经 URL 交接一次，而校验外壳会让用户
#: 点托盘打开的链接被自己拦掉——那条路上令牌还没交接。缺令牌时页面自己显示一张说明卡
#: （pages/shell.tsx 的 MissingToken），数据接口照旧一律要令牌。
PUBLIC_ENDPOINTS = frozenset(
    {"static", "index", "settings_page", "about_page", "favicon", "healthz"}
)


def _is_token_exempt(endpoint: str | None) -> bool:
    """旧接口兼容层（05 文档 §8）按端点名前缀豁免令牌。

    旧 KeyTrace 的 HTTP 客户端不知道 OmniSight 的会话令牌——迁移期共存
    （12 文档 M5 判据）要求这些端点能被它直接调用。这不削弱威胁模型：
    令牌防的是网页，而网页跨源读不到这些响应（上面没有任何
    ``Access-Control-Allow-*`` 头）；能直连它们的本地进程本来就能读数据库文件。
    Host 校验对所有端点依然生效。前缀约定由 ``presentation/api/legacy.py``
    的视图函数命名（``legacy_*``）保证。
    """
    return endpoint is not None and endpoint.startswith("legacy_")


def new_token() -> str:
    return secrets.token_urlsafe(32)


def write_runtime_file(directory: Path, *, port: int, token: str) -> Path:
    """把端口与令牌写进 ``runtime.json``，供本机工具（冒烟测试、第二实例）读取。

    这**不削弱**上面的威胁模型：令牌防的是网页，而网页读不到本地文件；能读到这个
    文件的程序本来就能直接读数据库。换来的是"无头启动后仍可访问自己的 API"，
    否则每次冒烟测试都要另开一条后门。文件权限收紧到仅当前用户可读写。
    """
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / RUNTIME_FILENAME
    payload = {"port": port, "token": token, "pid": os.getpid()}
    path.write_text(json.dumps(payload), encoding="utf-8")
    try:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:  # pragma: no cover - FAT32 等无权限概念的文件系统
        logger.debug("无法收紧 %s 的权限（文件系统不支持）", path)
    return path


def read_runtime_file(directory: Path) -> dict[str, object] | None:
    path = directory / RUNTIME_FILENAME
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def remove_runtime_file(directory: Path) -> None:
    with contextlib.suppress(OSError):  # pragma: no cover
        (directory / RUNTIME_FILENAME).unlink(missing_ok=True)


def install(app: Flask, *, token: str) -> None:
    """挂上 Host 校验、令牌校验与安全响应头。"""

    @app.before_request
    def _reject_foreign_host():
        host = (request.host or "").rsplit(":", 1)[0]
        if host not in ALLOWED_HOSTS:
            # 421 而非 403：语义是"这个请求被送错了地方"。
            return {"error": {"code": "misdirected_request", "message": "仅接受本机访问"}}, 421
        return None

    @app.before_request
    def _require_token():
        if request.endpoint in PUBLIC_ENDPOINTS or request.endpoint is None:
            return None
        if _is_token_exempt(request.endpoint):
            return None
        supplied = request.headers.get(TOKEN_HEADER, "")
        if not supplied:
            supplied = request.args.get("token", "")
        if not secrets.compare_digest(supplied, token):
            raise Unauthorized(description="缺少或无效的访问令牌")
        return None

    @app.after_request
    def _security_headers(response):
        response.headers.setdefault("Content-Security-Policy", CSP)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        # 不设置任何 Access-Control-Allow-*：跨源请求一律失败。
        return response
