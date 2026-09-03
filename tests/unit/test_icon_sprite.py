"""图标精灵表的三处一致性与两条形态约束（14 文档 §3.5、15 文档 §6 的 B1）。

图标现在有三份东西必须对得上，而它们分属三种语言：

1. ``tools/icons.py`` 的 ``ICON_SOURCES``——我们的 id → lucide 图标名，**唯一人工维护点**；
2. ``templates/_icon_sprite.html``——生成物，浏览器实际加载的那份 ``<symbol>``；
3. ``static/js/components/icon.js`` 的 ``ICON_NAMES``——JS 侧动态创建图标时用的清单。

在这之前，1 是手抄进 2 的，2 与 3 靠 ``icon.js`` 里一句"改这里之前先改模板"约束——
也就是没有约束。少一个 id 的症状是**图标位置空白但页面照常渲染**，没有报错。

**大部分用例不需要 Node。** 只有"生成物与 lucide-static 一致"那一条需要（要读
node_modules），它按 ``tests/unit/test_frontend_js.py`` 的同一条原则跳过。id 一致性、
形态约束、引用完整性三类都是纯文本比对，任何机器上都会跑。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import icons  # noqa: E402

PRESENTATION = ROOT / "src" / "omnisight" / "presentation"
SPRITE = PRESENTATION / "templates" / "_icon_sprite.html"
TEMPLATES = PRESENTATION / "templates"
JS = PRESENTATION / "static" / "js"

_SYMBOL = re.compile(
    r'<symbol id="i-(?P<name>[a-z-]+)" viewBox="(?P<box>[^"]+)">(?P<body>.*?)</symbol>'
)
_REFERENCE = re.compile(r'href="#i-(?P<name>[a-z-]+)"')


@pytest.fixture(scope="module")
def sprite_text() -> str:
    assert SPRITE.is_file(), f"{SPRITE} 不存在——跑 `python tools/icons.py`"
    return SPRITE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def symbols(sprite_text: str) -> dict[str, tuple[str, str]]:
    """精灵表里的 ``id -> (viewBox, 内容)``。"""
    return {
        m.group("name"): (m.group("box"), m.group("body")) for m in _SYMBOL.finditer(sprite_text)
    }


def _js_icon_names() -> list[str]:
    """``icon.js`` 的 ``ICON_NAMES``。正则读而不是执行 JS——不引 Node。"""
    text = (JS / "components" / "icon.js").read_text(encoding="utf-8")
    match = re.search(r"ICON_NAMES = Object\.freeze\(\[(?P<body>.*?)\]\)", text, re.DOTALL)
    assert match, "icon.js 里找不到 ICON_NAMES（改了写法就把这条正则一起改）"
    return re.findall(r"'([a-z-]+)'", match.group("body"))


def test_the_three_sources_declare_the_same_icons(symbols):
    """映射表、生成物、JS 清单三者的 id 集合必须相同。"""
    assert set(symbols) == set(icons.ICON_SOURCES), (
        "生成物与 ICON_SOURCES 不一致，跑 tools/icons.py"
    )
    assert set(_js_icon_names()) == set(icons.ICON_SOURCES), (
        "icon.js 的 ICON_NAMES 与 tools/icons.py 的 ICON_SOURCES 不一致"
    )


def test_the_declaration_order_matches_so_diffs_stay_readable(symbols):
    """顺序也对齐：三份清单同序，改一个图标的 diff 才只有一行。"""
    assert list(symbols) == list(icons.ICON_SOURCES)
    assert _js_icon_names() == list(icons.ICON_SOURCES)


def test_every_symbol_uses_the_24_grid(symbols):
    """14 §3.5 定的是 24×24 视框。混进一个 20×20 的图标会比邻居小一圈。"""
    for name, (box, _body) in symbols.items():
        assert box == "0 0 24 24", f"i-{name} 的 viewBox 是 {box}"


@pytest.mark.parametrize("attribute", ["fill=", "stroke=", "stroke-width=", "class="])
def test_symbols_carry_no_presentation_attributes(symbols, attribute):
    """笔重与颜色由 ``base.css`` 的 ``.icon`` 统一控制，元素上不能有副本。

    lucide 的源文件每个都自带 ``stroke-width="2"``；属性会盖过外部样式表，于是笔重
    变成 2（规格是 1.5），``currentColor`` 也不再跟随主题。``tools/icons.py``
    的 ``STRIP_ATTRS`` 负责剥掉它们，这条用例负责发现剥漏了。
    """
    for name, (_box, body) in symbols.items():
        assert attribute not in body, f"i-{name} 带着 {attribute}，会盖过 .icon 的样式"


def test_every_symbol_has_geometry(symbols):
    """探针：正则一旦匹配到空 symbol，上面几条会在空内容上通过。"""
    for name, (_box, body) in symbols.items():
        assert re.search(r"<(path|circle|rect|line|polyline|polygon|ellipse)\b", body), (
            f"i-{name} 里没有任何几何元素"
        )


def test_every_referenced_icon_exists_in_the_sprite(symbols):
    """模板与 JS 里 ``#i-x`` 引用的图标都得在精灵表里。

    引用一个不存在的 id 时浏览器**不报错**，只是那个位置什么都不画——所以这条只能
    靠静态检查发现。
    """
    referenced: set[str] = set()
    for path in [*TEMPLATES.rglob("*.html"), *JS.rglob("*.js")]:
        if path == SPRITE:
            continue
        text = path.read_text(encoding="utf-8")
        referenced |= {m.group("name") for m in _REFERENCE.finditer(text)}
    assert referenced, "一个 #i- 引用都没找到，检查这条用例自己的路径"
    missing = sorted(referenced - set(symbols))
    assert not missing, f"引用了精灵表里没有的图标：{missing}"


def test_dynamic_icon_calls_name_a_declared_icon():
    """``icon('x')`` 的 x 必须在 ICON_NAMES 里。M7 批次 5 抓到过同类缺陷。

    ``icon()`` 拿到未声明的名字时同样静默——它照常建出 ``<use href="#i-typo">``。
    """
    declared = set(_js_icon_names())
    for path in JS.rglob("*.js"):
        if path.name == "icon.js":
            continue
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"\bicon\(\s*'(?P<name>[a-z-]+)'", text):
            name = match.group("name")
            assert name in declared, f"{path.name} 调用了未声明的图标 icon('{name}')"


def test_the_isc_notice_travels_with_the_sprite(sprite_text):
    """ISC 要求副本保留版权与许可声明。这份文件随产物分发，声明就在它里面。"""
    assert "ISC License" in sprite_text
    assert "Lucide Contributors" in sprite_text
    assert "permission notice appear in all copies" in sprite_text


def test_the_generated_file_is_not_stale():
    """生成物与装着的 lucide-static 一致。**没装就跳过**（同 test_frontend_js.py）。"""
    if not (icons.ICONS / "settings.svg").is_file():
        pytest.skip("lucide-static 不在（跑 `pnpm install`）")
    assert icons.main(["--check"]) == 0, "精灵表已过期，跑 `python tools/icons.py`"


def test_a_missing_upstream_icon_fails_loudly():
    """探针：映射表点了一个 lucide 没有的名字时必须抛，而不是产出空 symbol。"""
    with pytest.raises(icons.MissingSource):
        icons.geometry_of("definitely-not-a-lucide-icon-xyz")


def test_the_include_reaches_the_rendered_page(api_context):
    """**功能判据**：`{% include %}` 真的被 Jinja 解析，15 个 symbol 到了页面上。

    精灵表从 `dashboard.html` 里搬进独立片段之后，"include 路径写错"这一类错误的
    症状是页面照常 200、样式照常、只有图标全部消失——而模板层的其它测试都不会红。
    这条走真实的 Flask 渲染，因此它同时覆盖 `template_folder` 的解析。
    """
    from omnisight.presentation.web import create_app

    app = create_app(api_context)
    app.config.update(TESTING=True)
    body = app.test_client().get("/").get_data(as_text=True)

    assert '<svg class="icon-sprite"' in body, "精灵表没进页面——include 没解析？"
    for name in icons.ICON_SOURCES:
        assert f'<symbol id="i-{name}"' in body, f"页面里没有 i-{name}"
    # Jinja 注释不该出现在页面上；HTML 注释（ISC 声明）应该出现。
    assert "本文件由 tools/icons.py" not in body
    assert "ISC License" in body
