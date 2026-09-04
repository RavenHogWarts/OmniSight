"""前端与后端的路径契约（11 文档 §4.3 的延伸）。

零构建的代价是没有类型检查：前端写 `/usage/priod` 只会在运行时静默 404，而那个面板
恰好也有"无数据"这个合法状态，于是拼错的端点看起来像"这段时间没有记录"。这组测试
把所有 JS 里出现的 API 路径与 Flask 的 `url_map` 对一遍。

同时固定住页面外壳与 main.js 之间的挂载点约定：模板改了 id 而 JS 没跟着改，
表现是整页空白且控制台一片安静（因为 `getElementById` 返回 null 不报错）。
"""

from __future__ import annotations

import json
import pathlib
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PRESENTATION = ROOT / "src" / "omnisight" / "presentation"
JS = ROOT / "frontend" / "src"
DIST = PRESENTATION / "static" / "dist"
#: 样式源码。15 文档 §11.4 把它搬进 `frontend/styles` 并接进 Vite；`static/css` 下只剩
#: `shell.css`（产物缺失时的兜底）。
CSS = ROOT / "frontend" / "styles"
SHELL_CSS = PRESENTATION / "static" / "css" / "shell.css"
TEMPLATE = PRESENTATION / "templates" / "dashboard.html"

#: main.js / components 用 getElementById 找的挂载点。少一个就是一块界面消失。
MOUNT_POINTS = (
    "app", "banners", "tabs", "status-host",
    "periodbar", "view-root", "toasts", "overlays",
)

#: 路由标签的 id 约定（syncTabs 按 `tab-<route>` 拼）。
ROUTES = ("overview", "apps", "keyboard", "insights")

_API_LITERAL = re.compile(r"['\"`](/(?:api/v1/)?[a-z][a-z0-9/_$\-{}.]*)['\"`]")


def _sources() -> list[pathlib.Path]:
    """前端的**运行时**源码。

    两种后缀都收着（迁移已完成，但多一个 glob 比"哪天加回一个 .js 就静默漏查"便宜）；
    `.d.ts` 刻意排除——它只有类型，一行运行时代码都没有，而它的文档注释里有形如
    `/apps/{id}` 的路径占位符，会被端点提取器当成真的调用。
    """
    found: list[pathlib.Path] = []
    for pattern in ("*.ts", "*.tsx", "*.js"):
        found.extend(path for path in JS.rglob(pattern) if not path.name.endswith(".d.ts"))
    return sorted(found)

def _js_api_paths() -> set[str]:
    """JS 里出现的 API 路径。模板串里的 `${...}` 归一成 `*`。"""
    found: set[str] = set()
    for path in _sources():
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
    """`app.css` 用 @import 汇总那 30 个文件；漏一个的表现是"某个组件没有样式"。

    15 文档 §11.4 之后 Vite 会内联这些 @import，所以**引用了不存在的文件**已经变成构建
    失败——那半条现在是白拿的。反过来那半条仍然只有这里管：一个写好却没被汇总进来的
    样式文件既不报错也不生效，构建看不出，浏览器里也只表现为"这个组件长得不对"。
    """
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


def test_the_fallback_stylesheet_stays_out_of_the_bundle(api_client):
    """`shell.css` 只在产物缺失时加载，因此**不能**进构建图（15 文档 §11.4）。

    它进了构建图就会跟着产物一起消失，而它存在的全部理由是产物消失时那张说明卡还能
    读——自带颜色与字体、不引用任何令牌，正是为此。

    正常情况下页面不该引用它：多一份样式表就要为两份的级联顺序负责，而那是白拿的
    复杂度（模板里用 `{% if bundle.missing %}` 分流）。
    """
    assert SHELL_CSS.is_file(), "兜底样式表不在了"
    text = SHELL_CSS.read_text(encoding="utf-8")
    assert "var(--surface-" not in text and "var(--text-" not in text, (
        "shell.css 引用了 tokens.css 的令牌——那份文件现在也在产物里，缺的时候一起缺"
    )
    assert not (CSS / "shell.css").exists(), "shell.css 不该同时存在于样式源码目录"
    body = api_client.get("/").get_data(as_text=True)
    assert "shell.css" not in body, "产物在位时不该引用兜底样式表"
    assert api_client.get("/static/css/shell.css").status_code == 200


def test_the_shell_links_the_built_stylesheet(api_client):
    """样式表也带内容哈希，因此地址由后端从清单读（web.py:read_bundle）。

    这条盯的是"清单里的 CSS 真的被铺进了 `<head>`"。它坏掉的症状是整页无样式而
    控制台一片安静——没有 404（文件在），只是没人引用它。
    """
    body = api_client.get("/").get_data(as_text=True)
    links = re.findall(r'<link rel="stylesheet" href="(/static/dist/[^"]+\.css)">', body)
    assert len(links) == 1, f"应当恰好有一份产物样式表（cssCodeSplit 是 false）：{links}"
    response = api_client.get(links[0])
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("text/css")
    # 它必须在入口脚本之前：样式晚到就是一帧无样式的内容（FOUC）。
    assert body.index(links[0]) < body.index('type="module"')


def test_the_smoke_markers_match_the_real_shell(api_client):
    """`tools/smoke.py` 的外壳标记与真实页面对得上。

    **那个工具跑在打包产物上**——它 Popen 的是 PyInstaller 出来的 EXE，所以本机没有
    EXE 时它根本起不来。于是标记写错只会在发布流水线上炸，而那时的报错长这样：
    "首页缺少 /static/css/app.css"。它看起来像页面坏了，其实是标记过期了——这一轮
    把样式表搬进产物（15 文档 §11.4）、把主题引导脚本删掉（§11.3），两处都动了那张表。

    这条把检查提前到 pytest：同一个 `_check_shell`，喂给 Flask 直接渲染的外壳。
    """
    import sys as _sys

    if str(ROOT / "tools") not in _sys.path:
        _sys.path.insert(0, str(ROOT / "tools"))
    import smoke

    body = api_client.get("/").get_data()
    assert not smoke._check_shell(body), smoke._check_shell(body)
    # 固定地址的那几个（产物缺失时的兜底样式、favicon）——它们平时不被页面引用，
    # 因此只有主动探一次才知道还在。
    for asset in smoke.SHELL_ASSETS:
        assert api_client.get(asset).status_code == 200, asset
    # 带哈希的那些从页面里抓：入口、样式表、modulepreload。
    found = smoke._bundle_assets(body)
    assert len(found) >= 2, f"页面里只抓到 {found}——入口与样式表至少该有两个"
    for asset in found:
        assert api_client.get(asset).status_code == 200, asset


def test_static_assets_referenced_by_the_shell_are_served(api_client):
    body = api_client.get("/").get_data(as_text=True)
    for asset in re.findall(r'(?:href|src)="(/static/[^"]+)"', body):
        assert api_client.get(asset).status_code == 200, asset


def test_module_graph_is_reachable_over_http(api_client):
    """产物里每个 chunk 都能取到。任何一个 404 都会让整页停在骨架屏上。

    15 文档选了方案 A 之后浏览器不再逐个加载源码模块，而是加载 Vite 的产物；
    因此这条从"遍历 static/js"改成"遍历产物清单"——它验证的仍然是同一件事，
    只是模块图的真源换了地方。
    """
    manifest = json.loads((DIST / "manifest.json").read_text(encoding="utf-8"))
    files = {record["file"] for record in manifest.values() if isinstance(record, dict)}
    assert files, "产物清单是空的——跑 `pnpm build`"
    for name in sorted(files):
        url = "/static/dist/" + name
        assert api_client.get(url).status_code == 200, url


def test_modules_are_served_with_a_javascript_mime_type(api_client):
    """ES 模块对 MIME 类型是严格的：不是 JS 类型，浏览器整页拒绝执行。

    Windows 的 ``mimetypes`` 会读注册表，而某些安装程序把 ``.js`` 写成
    ``text/plain``。症状是空白页 + 一条控制台报错，且只在那台机器上出现——
    ``create_app`` 因此显式注册类型，这条用例盯住它。
    """
    body = api_client.get("/").get_data(as_text=True)
    entry = re.search(r'<script type="module" src="([^"]+)"', body)
    assert entry, "页面外壳里没有入口 <script>——产物缺失？"
    response = api_client.get(entry.group(1))
    assert response.status_code == 200
    assert response.headers["Content-Type"].split(";")[0] in {
        "text/javascript",
        "application/javascript",
    }
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
    for path in _sources():
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
