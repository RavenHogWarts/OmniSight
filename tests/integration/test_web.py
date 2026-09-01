"""状态接口与本机安全约束（05 文档 §7、08 文档 §3）。

这里固定的是三件在 M0 就必须成立、且日后极易被重构悄悄破坏的事：

* ``/api/v1/status`` 的形状（``platform`` / ``capabilities`` / ``degraded`` 分段）
* 令牌校验真的在拦请求
* ``Host`` 头校验挡住 DNS rebinding
"""

from __future__ import annotations

import pytest
from flask.testing import FlaskClient

from omnisight.core.config import default_config
from omnisight.presentation import security
from omnisight.presentation.web import AppContext, create_app
from omnisight.storage.migrations import TARGET_VERSION

TOKEN = "test-token-value"


@pytest.fixture
def context(database, full_capabilities, tmp_path):
    return AppContext(
        config=default_config(),
        database=database,
        capabilities=full_capabilities,
        token=TOKEN,
        started_at="2026-08-31T22:15:03+08:00",
        data_dir=tmp_path,
        schema_version=TARGET_VERSION,
    )


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


def test_placeholder_page_has_no_inline_script(client: FlaskClient):
    """CSP 的 ``script-src 'self'`` 禁止内联脚本——这与 07 文档的前端决定互为前提。"""
    body = client.get("/").get_data(as_text=True)
    assert "<script type=\"module\" src=" in body
    assert "onclick=" not in body


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
