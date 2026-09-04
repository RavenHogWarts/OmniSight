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


# ── 字段级契约：types/api.d.ts 对着真实响应核对 ──────────────────────────
#
# 07 文档 §10 列了三处前后端必须一致的内容并各自给了执行机制，**字段级形状原先不在
# 其中**：后端改一个字段名，前端只是静默显示空值，而"这段时间没有记录"恰好也是合法
# 状态。tools/check_types.py 让前端在类型上必须按 api.d.ts 取值；这一组测试保证
# api.d.ts 说的就是后端真的给的那些字段——两头一起钉住，中间才没有缝。
#
# 声明多一个必填字段、少一个后端会给的字段、把 number 写成 string 都会红。

import dts  # noqa: E402

API_TYPES = JS / "types" / "api.d.ts"

#: 端点 -> 声明的响应类型。seeded_client 的数据集见 tests/seeded.py（NOW = 2026-09-02）。
DAY = "range=day&date=2026-09-02"
ENDPOINT_TYPES: tuple[tuple[str, str], ...] = (
    (f"/api/v1/overview?{DAY}", "OverviewResponse"),
    # include=highlights 时只回结论段：验证那些"按参数出现"的字段真的是可选的。
    (f"/api/v1/overview?{DAY}&include=highlights", "OverviewResponse"),
    # range=total 会带出 coverage.gaps 与更长的趋势桶。
    ("/api/v1/overview?range=total", "OverviewResponse"),
    (f"/api/v1/usage/period?{DAY}&limit=500", "UsagePeriodResponse"),
    (f"/api/v1/usage/period?{DAY}&q=code", "UsagePeriodResponse"),
    (f"/api/v1/usage/timeline?{DAY}&top=5", "UsageTimelineResponse"),
    ("/api/v1/usage/timeline?range=total&top=5", "UsageTimelineResponse"),
    (f"/api/v1/usage/sessions?{DAY}&limit=50", "SessionsResponse"),
    ("/api/v1/apps?limit=500&include_excluded=true", "AppsResponse"),
    ("/api/v1/apps/running", "RunningAppsResponse"),
    ("/api/v1/apps/1", "AppDetailResponse"),
    ("/api/v1/keyboard/layout", "LayoutResponse"),
    # ISO 布局才有 shape=iso_enter 与跨行的 h——那两个字段只在这里出现。
    ("/api/v1/keyboard/layout?family=iso105", "LayoutResponse"),
    (f"/api/v1/keyboard/heatmap?{DAY}", "HeatmapResponse"),
    ("/api/v1/keyboard/heatmap?range=total", "HeatmapResponse"),
    (f"/api/v1/keyboard/heatmap?{DAY}&app_id=1", "HeatmapResponse"),
    (
        f"/api/v1/keyboard/timeline?{DAY}&view=hours,days,months,years",
        "KeyboardTimelineResponse",
    ),
    (f"/api/v1/keyboard/ergonomics?{DAY}", "ErgonomicsResponse"),
    (f"/api/v1/insights/app-keyboard?{DAY}&limit=20", "AppKeyboardResponse"),
    (f"/api/v1/insights/rhythm?{DAY}", "RhythmResponse"),
    ("/api/v1/status", "StatusResponse"),
    ("/api/v1/settings", "SettingsResponse"),
    ("/api/v1/onboarding", "OnboardingResponse"),
    ("/api/v1/import/detect", "DetectResponse"),
    ("/api/v1/import/progress", "ImportProgressResponse"),
)


@pytest.fixture(scope="module")
def declarations():
    return dts.parse(API_TYPES)


@pytest.mark.parametrize(("url", "interface"), ENDPOINT_TYPES)
def test_response_matches_the_declared_shape(seeded_client, declarations, url, interface):
    response = seeded_client.get(url)
    assert response.status_code == 200, f"{url} 返回 {response.status_code}"
    problems = dts.mismatches(declarations, interface, response.get_json(), interface)
    assert not problems, f"{url} 与 {interface} 不一致：\n" + "\n".join(
        f"  {problem}" for problem in problems
    )


def test_key_detail_matches_the_declared_shape(seeded_client, declarations):
    """键位明细的 URL 里有一个真实 key_id，因此从 heatmap 现取一个最热的。"""
    keys = seeded_client.get("/api/v1/keyboard/heatmap?range=total").get_json()["keys"]
    hottest = max(keys, key=lambda item: item["press_count"])
    assert hottest["press_count"] > 0, "数据集里没有任何按键，这条测试会空跑"
    response = seeded_client.get(f"/api/v1/keyboard/keys/{hottest['id']}?range=total")
    assert response.status_code == 200
    problems = dts.mismatches(
        declarations, "KeyDetailResponse", response.get_json(), "KeyDetailResponse"
    )
    assert not problems, "KeyDetailResponse 不一致：\n" + "\n".join(problems)


def test_error_body_matches_the_declared_shape(seeded_client, declarations):
    """错误响应也是契约的一部分：core/api.js 的 ApiError 从这三个字段取值。"""
    response = seeded_client.get("/api/v1/keyboard/keys/not-a-real-key")
    assert response.status_code == 400
    problems = dts.mismatches(
        declarations, "ErrorResponse", response.get_json(), "ErrorResponse"
    )
    assert not problems, "ErrorResponse 不一致：\n" + "\n".join(problems)


def test_every_data_map_entry_is_actually_requested_by_a_view(declarations):
    """DataMap 里躺着一个没人再用的 key，说明它随某次改动一起过期了。

    反方向（视图请求了 DataMap 里没有的 key）由 tsc 保证——`fetchInto` 的第一个参数
    是 `keyof DataMap`，写错的名字连类型检查都过不去。
    """
    used: set[str] = set()
    pattern = re.compile(r"(?:fetchInto\(\s*'(?P<a>\w+)'|key:\s*'(?P<b>\w+)')")
    for path in sorted(JS.rglob("*.js")):
        for match in pattern.finditer(path.read_text(encoding="utf-8")):
            used.add(match.group("a") or match.group("b"))
    declared = set(declarations.fields_of("DataMap"))
    assert declared <= used, f"DataMap 里没人请求的 key：{sorted(declared - used)}"


def test_every_declared_response_type_is_covered_by_an_endpoint(declarations):
    """探针：新增一个响应类型却忘了给它配端点时，上面那组测试不会变红。"""
    checked = {interface for _url, interface in ENDPOINT_TYPES}
    checked |= {"KeyDetailResponse", "ErrorResponse"}
    # DataMap 的每个值类型都必须有人核对过——那些正是视图直接读的响应。
    data_map_types = {item.type for item in declarations.fields_of("DataMap").values()}
    assert data_map_types <= checked, (
        f"DataMap 用到但没有端点核对的类型：{sorted(data_map_types - checked)}"
    )


def test_the_walker_understands_every_type_it_is_asked_about(declarations):
    """探针：api.d.ts 里出现解析器读不懂的写法时，比对会静默少查一层。"""
    unknown: set[str] = set()
    for _url, interface in ENDPOINT_TYPES:
        unknown |= dts.unchecked_types(declarations, interface)
    assert not unknown, f"tests/dts.py 认不出这些类型：{sorted(unknown)}"


def test_the_declarations_file_actually_parsed():
    """探针：正则写坏或文件改名时，上面全部会空跑通过。"""
    parsed = dts.parse(API_TYPES)
    assert len(parsed.interfaces) >= 50, f"只解析到 {len(parsed.interfaces)} 个 interface"
    assert "DataMap" in parsed.interfaces
    assert parsed.fields_of("PeriodMeta")["start"].type == "string"
