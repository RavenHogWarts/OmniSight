"""``ui.open_dashboard_on_start``：启动后自动用默认浏览器打开仪表盘。

开关存在的理由：macOS 上双击 .app 只是启动菜单栏常驻程序，不弹任何窗口，而令牌
每次启动都轮换、前端拿到后还会把它从地址栏抹掉——于是"双击就想看到页面"既不能靠
书签（裸地址永远缺令牌）也不能靠双击托盘（点第一下弹菜单、第二下又收回去）。

这里钉住的不是"浏览器开了没有"（那是 ``webbrowser`` 的事），而是**什么时候开、
用什么地址开**：开关关着绝不能开，开着必须用带令牌的 dashboard_url 开。
"""

from __future__ import annotations

from types import SimpleNamespace

from omnisight.core import lifecycle as lifecycle_mod
from omnisight.core.lifecycle import Lifecycle

OPENS: list[str] = []


def _runtime(open_on_start: bool) -> SimpleNamespace:
    return SimpleNamespace(
        context=object(),
        data_dir=None,
        token="tok",
        web=None,
        # _open_external 先问提权适配器（Windows 概念），macOS / 测试里没有。
        adapter_set=SimpleNamespace(elevation=None),
        config=SimpleNamespace(
            server=SimpleNamespace(host="127.0.0.1", port=6100),
            ui=SimpleNamespace(open_dashboard_on_start=open_on_start),
            dashboard_url=lambda token: f"http://127.0.0.1:6100/?token={token}",
        ),
    )


def _stub_web(monkeypatch) -> None:
    monkeypatch.setattr(lifecycle_mod, "create_app", lambda context: object())
    fake = SimpleNamespace(start=lambda: None, port=6100)
    monkeypatch.setattr(lifecycle_mod, "WebServer", lambda app, host, port: fake)
    monkeypatch.setattr(
        lifecycle_mod.security, "write_runtime_file", lambda *args, **kwargs: None
    )
    OPENS.clear()
    monkeypatch.setattr(
        lifecycle_mod.webbrowser, "open", lambda target: OPENS.append(target) or True
    )


def test_disabled_by_default_opens_nothing(monkeypatch):
    """默认关闭：随登录自启的后台工具不该每次都弹浏览器。"""
    _stub_web(monkeypatch)
    Lifecycle()._start_web(_runtime(open_on_start=False))
    assert OPENS == []


def test_enabled_opens_the_tokenised_dashboard(monkeypatch):
    """开启时必须带令牌打开 dashboard_url，而不是裸地址或设置页。"""
    _stub_web(monkeypatch)
    Lifecycle()._start_web(_runtime(open_on_start=True))
    assert OPENS == ["http://127.0.0.1:6100/?token=tok"]
