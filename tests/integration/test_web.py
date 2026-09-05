"""状态接口与本机安全约束（05 文档 §7、08 文档 §3）。

这里固定的是三件在 M0 就必须成立、且日后极易被重构悄悄破坏的事：

* ``/api/v1/status`` 的形状（``platform`` / ``capabilities`` / ``degraded`` 分段）
* 令牌校验真的在拦请求
* ``Host`` 头校验挡住 DNS rebinding
"""

from __future__ import annotations

import pytest
from flask.testing import FlaskClient

from conftest import API_TOKEN as TOKEN  # 单一真源：令牌只在 conftest 里定义一次
from omnisight.presentation import security
from omnisight.presentation.web import create_app
from omnisight.storage.migrations import TARGET_VERSION


@pytest.fixture
def context(api_context):
    """复用 ``conftest`` 的上下文：M2 起 ``create_app`` 只在 ``services`` 就位时注册 API
    路由，自己拼一个不带服务层的上下文会让这里的鉴权用例全部撞上 404 而不是 401。"""
    return api_context


@pytest.fixture
def client(context) -> FlaskClient:
    app = create_app(context)
    app.config.update(TESTING=True)
    return app.test_client()


def _auth() -> dict[str, str]:
    return {security.TOKEN_HEADER: TOKEN}


def test_status_has_documented_shape(client: FlaskClient):
    payload = client.get("/api/v1/status", headers=_auth()).get_json()
    assert payload["app"] == "OmniSight"
    assert set(payload["platform"]) == {"id", "tier", "os_version"}
    assert payload["platform"]["id"] == "windows"
    assert payload["capabilities"]["keyboard_backend"] == "raw_input"
    assert payload["database"]["schema_version"] == TARGET_VERSION
    assert payload["degraded"] == []
    assert "capture" in payload and "data_version" in payload


def test_status_reports_degraded_notices(context, full_capabilities):
    """空数组与非空数组两条渲染路径都必须能产出，否则 M3 前端要重做。"""
    from dataclasses import replace

    from omnisight.adapters.ports import DegradedNotice

    notice = DegradedNotice(
        code="keyboard_backend_degraded",
        severity="warning",
        title="键盘采集降级",
        detail="左右修饰键会合并统计。",
        hint="重启可再次尝试专用后端",
    )
    context.capabilities = replace(full_capabilities, degraded=(notice,))
    app = create_app(context)
    payload = app.test_client().get("/api/v1/status", headers=_auth()).get_json()
    assert payload["degraded"][0]["code"] == "keyboard_backend_degraded"
    assert payload["degraded"][0]["hint"]


def test_api_requires_token(client: FlaskClient):
    response = client.get("/api/v1/status")
    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "unauthorized"


def test_wrong_token_is_rejected(client: FlaskClient):
    response = client.get("/api/v1/status", headers={security.TOKEN_HEADER: "nope"})
    assert response.status_code == 401


def test_token_may_arrive_as_query_parameter(client: FlaskClient):
    """托盘打开的链接把令牌放在 URL 里，页面随后转存到 sessionStorage。"""
    assert client.get(f"/api/v1/status?token={TOKEN}").status_code == 200


def test_index_and_healthz_are_public(client: FlaskClient):
    assert client.get("/").status_code == 200
    assert client.get("/healthz").get_json() == {"ok": True}


def test_foreign_host_is_rejected(client: FlaskClient):
    """DNS rebinding：恶意域名解析到 127.0.0.1 后绕过同源策略（08 文档 §3.2a）。"""
    response = client.get("/healthz", headers={"Host": "evil.example.com"})
    assert response.status_code == 421
    assert response.get_json()["error"]["code"] == "misdirected_request"


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "127.0.0.1:6100"])
def test_loopback_hosts_are_accepted(client: FlaskClient, host: str):
    assert client.get("/healthz", headers={"Host": host}).status_code == 200


def test_security_headers_present(client: FlaskClient):
    headers = client.get("/", headers={"Host": "127.0.0.1"}).headers
    assert "script-src 'self'" in headers["Content-Security-Policy"]
    assert "unsafe-inline" not in headers["Content-Security-Policy"]
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert "Access-Control-Allow-Origin" not in headers


def test_shell_page_has_no_inline_script(client: FlaskClient):
    """CSP 的 ``script-src 'self'`` 禁止内联脚本——这与 07 文档的前端决定互为前提。

    06 文档 §3.2 给的防闪白方案是内联 ``<script>``，那会被 CSP 直接拒掉。M3 改成同源的
    外部阻塞脚本 ``/static/js/theme.js``；15 文档 §11.3 又把它换成服务端渲染
    ``<html data-theme>``（见下一条），于是页面里只剩产物入口那一个 ``<script>``。
    """
    body = client.get("/").get_data(as_text=True)
    assert '<script type="module" src=' in body
    assert body.count("<script") == 1, "页面外壳只该有产物入口那一个 script"
    assert "onclick=" not in body


def test_shell_renders_the_configured_theme(client: FlaskClient, context):
    """``<html data-theme>`` 按 ``ui.theme`` 渲染（15 文档 §11.3）。

    这是防主题闪白的**唯一**机制了：阻塞的引导脚本已删除。它坏掉的症状是深色用户每次
    刷新闪一帧白底——没有报错、没有失败的请求，因此必须由测试盯着。

    ``system`` 那一档刻意**不渲染属性**：tokens.css 用
    ``@media (prefers-color-scheme: dark)`` 处理它，而写成属性会把"跟随系统"钉死在某一色。
    """
    from dataclasses import replace

    body = client.get("/").get_data(as_text=True)
    assert "data-theme" not in body, "默认 ui.theme 是 system，不该渲染属性"

    for theme in ("dark", "light"):
        context.config = replace(context.config, ui=replace(context.config.ui, theme=theme))
        body = client.get("/").get_data(as_text=True)
        assert f'<html lang="zh-CN" data-theme="{theme}">' in body


def test_shell_renders_the_configured_heat_scale(client: FlaskClient, context):
    """``<html data-heat>`` 按 ``ui.heat`` 渲染（18 文档 批 3）。

    热力色原先只存在前端的 localStorage 里：换一个浏览器打开，用户设的暖色就没了，而界面上
    没有任何地方说得出为什么。它现在与主题同一条路——配置是真源、服务端渲染那一档、前端切换
    时双写。``blue`` 是默认值，因此**不渲染属性**（tokens.css 里只有 ``[data-heat="warm"]``
    一个选择器）。
    """
    from dataclasses import replace

    body = client.get("/").get_data(as_text=True)
    assert "data-heat" not in body, "默认 ui.heat 是 blue，不该渲染属性"

    context.config = replace(context.config, ui=replace(context.config.ui, heat="warm"))
    body = client.get("/").get_data(as_text=True)
    assert 'data-heat="warm"' in body


def test_every_page_shell_renders_its_own_entry(client: FlaskClient):
    """三个页面各取自己的 Vite 入口（18 文档 批 1）。

    `read_bundle` 原先按 `isEntry` 取**第一条**——多入口之后那等于随构建顺序挑一份，而症状是
    "设置页画出了仪表盘"：页面 200、控制台安静，只是内容完全不对。
    """
    import json

    from omnisight.presentation import web

    manifest = json.loads(
        (web.paths.resource_dir() / "presentation" / "static" / "dist" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    wanted = {
        "/": web.ENTRY_DASHBOARD,
        "/settings": web.ENTRY_SETTINGS,
        "/about": web.ENTRY_ABOUT,
    }
    for path, key in wanted.items():
        body = client.get(path).get_data(as_text=True)
        entry = manifest[key]["file"]
        assert f'src="/static/dist/{entry}"' in body, f"{path} 应当加载 {key}"
        for other, other_key in wanted.items():
            if other_key == key:
                continue
            assert manifest[other_key]["file"] not in body, f"{path} 同时加载了 {other} 的入口"


def test_favicon_is_served_without_a_token(client: FlaskClient):
    """``<link rel="icon">`` 发出的请求带不了自定义头，因此这个端点必须免令牌。"""
    response = client.get("/favicon.svg")
    assert response.status_code == 200
    assert b"<svg" in response.get_data()


def test_unknown_route_returns_structured_error(client: FlaskClient):
    payload = client.get("/api/v1/nope", headers=_auth()).get_json()
    assert payload["error"]["code"] == "not_found"


def test_unexpected_exception_returns_trace_id(context):
    app = create_app(context)

    @app.get("/api/v1/_boom")
    def boom():
        raise RuntimeError("内部炸了")

    client = app.test_client()
    response = client.get("/api/v1/_boom", headers=_auth())
    assert response.status_code == 500
    error = response.get_json()["error"]
    assert error["code"] == "internal_error"
    assert error["trace_id"]
    # 异常细节可能含路径，不能回给前端。
    assert "内部炸了" not in response.get_data(as_text=True)
