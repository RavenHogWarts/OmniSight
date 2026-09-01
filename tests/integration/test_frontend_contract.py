"""前端与后端的路径契约（11 文档 §4.3 的延伸）。

零构建的代价是没有类型检查：前端写 `/usage/priod` 只会在运行时静默 404，而那个面板
恰好也有"无数据"这个合法状态，于是拼错的端点看起来像"这段时间没有记录"。这组测试
把所有 JS 里出现的 API 路径与 Flask 的 `url_map` 对一遍。

同时固定住页面外壳与 main.js 之间的挂载点约定：模板改了 id 而 JS 没跟着改，
表现是整页空白且控制台一片安静（因为 `getElementById` 返回 null 不报错）。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PRESENTATION = ROOT / "src" / "omnisight" / "presentation"
JS = PRESENTATION / "static" / "js"
CSS = PRESENTATION / "static" / "css"
TEMPLATE = PRESENTATION / "templates" / "dashboard.html"

#: main.js / components 用 getElementById 找的挂载点。少一个就是一块界面消失。
MOUNT_POINTS = (
    "app", "banners", "tabs", "status-host",
    "periodbar", "view-root", "toasts", "overlays",
)

#: 路由标签的 id 约定（syncTabs 按 `tab-<route>` 拼）。
ROUTES = ("overview", "apps", "keyboard", "insights")

_API_LITERAL = re.compile(r"['\"`](/(?:api/v1/)?[a-z][a-z0-9/_$\-{}.]*)['\"`]")


def _js_api_paths() -> set[str]:
    """JS 里出现的 API 路径。模板串里的 `${...}` 归一成 `*`。"""
    found: set[str] = set()
    for path in sorted(JS.rglob("*.js")):
        text = path.read_text(encoding="utf-8")
        for match in _API_LITERAL.finditer(text):
            raw = match.group(1)
            if raw.startswith("/static/") or raw.startswith("/favicon"):
                continue
            # api.js 里的 BASE 常量本身不是端点。
            if raw.rstrip("/") in {"/api/v1", "/api"}:
                continue
            normalised = re.sub(r"\$\{[^}]*\}", "*", raw)
            found.add(normalised)
    return found


def _rule_patterns(app) -> set[str]:
    """url_map 的规则归一成同一种形态：`<int:app_id>` -> `*`。"""
    patterns = set()
    for rule in app.url_map.iter_rules():
        patterns.add(re.sub(r"<[^>]+>", "*", str(rule)))
    return patterns


def test_every_api_path_in_the_frontend_exists_in_the_url_map(api_client):
    app = api_client.application
    patterns = _rule_patterns(app)
    unknown = []
    for path in sorted(_js_api_paths()):
        candidate = path if path.startswith("/api/v1") else f"/api/v1{path}"
        if candidate not in patterns:
            unknown.append(candidate)
    assert not unknown, f"前端引用了不存在的端点：{unknown}\n可用：{sorted(patterns)}"


def test_the_extractor_actually_finds_paths():
    """探针：正则写坏时上面那条会空跑通过。"""
    paths = _js_api_paths()
    assert len(paths) >= 10, f"只提取到 {len(paths)} 条路径：{sorted(paths)}"
    assert "/overview" in paths
    assert "/keyboard/layout" in paths


@pytest.mark.parametrize("element_id", MOUNT_POINTS)
def test_shell_has_every_mount_point(api_client, element_id: str):
    body = api_client.get("/").get_data(as_text=True)
    assert f'id="{element_id}"' in body


@pytest.mark.parametrize("route", ROUTES)
def test_shell_has_a_tab_per_route(api_client, route: str):
    body = api_client.get("/").get_data(as_text=True)
    assert f'id="tab-{route}"' in body
    assert f'data-route="{route}"' in body


def test_shell_is_reachable_without_a_token(api_client):
    """外壳免令牌（08 文档 §3.2b）：否则托盘打开的链接会被自己拦掉。"""
    fresh = api_client.application.test_client()
    assert fresh.get("/").status_code == 200
    assert fresh.get("/favicon.svg").status_code == 200
    # 但数据一律要令牌。
    assert fresh.get("/api/v1/status").status_code == 401


def test_shell_carries_no_statistics(api_client):
    """模板零数据（06 文档 §14）。注入一份 capabilities 就等于多一个会过期的副本。"""
    body = api_client.get("/").get_data(as_text=True)
    for leak in ("press_count", "capabilities", "total_seconds", "app_id"):
        assert leak not in body


def test_every_css_import_resolves(api_client):
    """app.css 用 @import 汇总；漏一个文件表现为"某个组件没有样式"而不是报错。"""
    text = (CSS / "app.css").read_text(encoding="utf-8")
    targets = re.findall(r'@import url\("([^"]+)"\)', text)
    assert len(targets) >= 15
    missing = [target for target in targets if not (CSS / target).is_file()]
    assert not missing, f"app.css 引用了不存在的样式文件：{missing}"
    # 反向：每个样式文件都要被汇总进来，否则它写了也不生效。
    on_disk = {
        path.relative_to(CSS).as_posix()
        for path in CSS.rglob("*.css")
        if path.name != "app.css"
    }
    assert on_disk == set(targets), f"未被 app.css 汇总：{sorted(on_disk - set(targets))}"


def test_static_assets_referenced_by_the_shell_are_served(api_client):
    body = api_client.get("/").get_data(as_text=True)
    for asset in re.findall(r'(?:href|src)="(/static/[^"]+)"', body):
        assert api_client.get(asset).status_code == 200, asset


def test_module_graph_is_reachable_over_http(api_client):
    """浏览器按相对路径逐个加载模块。任何一个 404 都会让整页停在骨架屏上。"""
    for path in sorted(JS.rglob("*.js")):
        url = "/static/js/" + path.relative_to(JS).as_posix()
        assert api_client.get(url).status_code == 200, url


def test_modules_are_served_with_a_javascript_mime_type(api_client):
    """ES 模块对 MIME 类型是严格的：不是 JS 类型，浏览器整页拒绝执行。

    Windows 的 ``mimetypes`` 会读注册表，而某些安装程序把 ``.js`` 写成
    ``text/plain``。症状是空白页 + 一条控制台报错，且只在那台机器上出现——
    ``create_app`` 因此显式注册类型，这条用例盯住它。
    """
    response = api_client.get("/static/js/main.js")
    assert response.status_code == 200
    assert response.headers["Content-Type"].split(";")[0] in {
        "text/javascript",
        "application/javascript",
    }
    css = api_client.get("/static/css/app.css")
    assert css.headers["Content-Type"].startswith("text/css")
    icon = api_client.get("/favicon.svg")
    assert icon.headers["Content-Type"].startswith("image/svg+xml")
