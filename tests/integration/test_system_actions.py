"""进程级动作的三个端点（18 文档 批 5）。

它们与其他写操作同一档：令牌 + 同源校验。但有一条只属于这一组的要求——**装配层没给这条
能力时如实回 503**，而不是 500：那不是一次失败的操作，是这个实例根本没有进程控制入口
（以库的方式用它、或测试里的应用工厂就是这种情形）。

``restart`` 的语义也在这里钉住：起不来时**本实例什么都不改**，并且如实回 500——设置页要把
这件事说给用户听，而"先起后停"那半条由 tests/unit/test_restart.py 验。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from omnisight.presentation.web import create_app

TOKEN_HEADER = "X-OmniSight-Token"


def _client(context, *, system=None):
    context.system = system
    app = create_app(context)
    app.config.update(TESTING=True)
    client = app.test_client()
    client.environ_base["HTTP_" + TOKEN_HEADER.upper().replace("-", "_")] = "test-token-value"
    client.environ_base["HTTP_SEC_FETCH_SITE"] = "same-origin"
    return client


@pytest.fixture
def actions():
    """假的进程动作。记下调用顺序，而不是真的重启一个进程。"""
    calls: list[str] = []
    return SimpleNamespace(
        calls=calls,
        restart=lambda: (calls.append("restart"), True)[1],
        quit=lambda: calls.append("quit"),
        reveal=lambda target: (calls.append(f"reveal:{target}"), True)[1],
    )


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/api/v1/system/restart", {}),
        ("/api/v1/system/quit", {}),
        ("/api/v1/system/reveal", {"target": "data"}),
    ],
)
def test_without_a_composition_root_the_endpoints_say_so(api_context, path, body):
    response = _client(api_context).post(path, json=body)
    assert response.status_code == 503
    assert response.get_json()["error"]["code"] == "capability_unavailable"


def test_restart_answers_before_it_stops(api_context, actions):
    """202：动作还没做完——接班实例在启动，本实例马上停机。"""
    response = _client(api_context, system=actions).post("/api/v1/system/restart", json={})
    assert response.status_code == 202
    assert response.get_json()["restarting"] is True
    assert actions.calls == ["restart"]


def test_a_failed_restart_is_a_500_and_says_the_instance_is_still_running(api_context, actions):
    actions.restart = lambda: False
    response = _client(api_context, system=actions).post("/api/v1/system/restart", json={})
    assert response.status_code == 500
    assert response.get_json()["error"]["code"] == "restart_failed"


def test_quit_answers_before_it_stops(api_context, actions):
    response = _client(api_context, system=actions).post("/api/v1/system/quit", json={})
    assert response.status_code == 202
    assert response.get_json()["stopping"] is True
    assert actions.calls == ["quit"]


@pytest.mark.parametrize("target", ["data", "logs"])
def test_reveal_takes_a_word_from_the_whitelist(api_context, actions, target):
    response = _client(api_context, system=actions).post(
        "/api/v1/system/reveal", json={"target": target}
    )
    assert response.status_code == 200
    assert actions.calls == [f"reveal:{target}"]


def test_reveal_refuses_anything_that_is_not_on_the_whitelist(api_context, actions):
    """接受路径就等于把"用文件管理器打开任意位置"开放给页面。"""
    response = _client(api_context, system=actions).post(
        "/api/v1/system/reveal", json={"target": "C:/Windows"}
    )
    assert response.status_code == 400
    assert response.get_json()["error"]["field"] == "target"
    assert actions.calls == []


@pytest.mark.parametrize(
    "path",
    ["/api/v1/system/restart", "/api/v1/system/quit", "/api/v1/system/reveal"],
)
def test_cross_site_requests_cannot_stop_the_process(api_context, actions, path):
    """令牌防"网页能不能读"，同源校验防"网页能不能代替用户按下退出"（08 文档 §3.2d）。"""
    client = _client(api_context, system=actions)
    client.environ_base["HTTP_SEC_FETCH_SITE"] = "cross-site"
    response = client.post(path, json={"target": "data"})
    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "cross_site_denied"
    assert actions.calls == []
