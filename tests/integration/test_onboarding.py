"""首启说明的接口契约（08 文档 §6.1；令牌/同站边界与 05 文档 §9 的其余端点一致）。

两条端点：``GET /onboarding`` 取内容，``POST /onboarding/ack`` 记已读。
后者是**写操作**，走 ``require_same_site``——与设置接口同一档。
"""

from __future__ import annotations

from omnisight.presentation.web import create_app


def test_get_returns_required_true_on_a_fresh_database(api_client):
    payload = api_client.get("/api/v1/onboarding").get_json()
    assert payload["required"] is True
    assert payload["acknowledged_at"] is None
    assert payload["version"] >= 1
    assert payload["records"]  # 全能力夹具下"会记录"不为空
    assert payload["not_records"]
    assert payload["pause"]["tray_item"] == "暂停记录"
    assert "platform" in payload and "paths" in payload


def test_ack_requires_same_site(api_client):
    """跨站请求必须 403：确认"我已读过"可以被网页伪造的话，首启说明就形同虚设。"""
    api_client.environ_base["HTTP_SEC_FETCH_SITE"] = "cross-site"
    response = api_client.post("/api/v1/onboarding/ack")
    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "cross_site_denied"


def test_ack_flips_the_requirement(api_client):
    stamp = api_client.post("/api/v1/onboarding/ack").get_json()["acknowledged_at"]
    assert stamp
    payload = api_client.get("/api/v1/onboarding").get_json()
    assert payload["required"] is False
    assert payload["acknowledged_at"] == stamp


def test_both_endpoints_require_the_token(api_context):
    """没有令牌的请求必须 401——说明页含数据位置等本机信息，不属于公开端点。"""
    client = create_app(api_context).test_client()
    assert client.get("/api/v1/onboarding").status_code == 401
    assert client.post("/api/v1/onboarding/ack").status_code == 401
