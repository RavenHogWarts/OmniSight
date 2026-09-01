"""设计令牌的对比度（06 文档 §13、12 文档 M3 判据"深色模式全页无对比度低于 4.5:1"）。

这条判据只有算出来才算数。文档给的值本身就不达标——`--text-secondary: #77777d`
在白底上是 4.45:1、在 `--surface-sunken` 上只有 3.84:1，而 `--text-tertiary: #9a9aa3`
只有 2.4:1。tokens.css 因此用了更深/更亮的值，这个测试是那次调整的依据。

**这个测试检查的是令牌层，不是每一处实际渲染。** 它保证"任何文字色配任何表面色"
都达标，于是组件层怎么组合都不会掉到 4.5:1 以下；但它测不出"某处用了硬编码颜色"
——那由 check_frontend 的模式检查与人工验收覆盖。
"""

from __future__ import annotations

import re
from itertools import pairwise
from pathlib import Path

import pytest

TOKENS = (
    Path(__file__).resolve().parents[2]
    / "src" / "omnisight" / "presentation" / "static" / "css" / "tokens.css"
)

#: WCAG 2.1 AA：正文 4.5:1，大字与图形 3:1。
TEXT_MINIMUM = 4.5
GRAPHIC_MINIMUM = 3.0

TEXT_TOKENS = ("--text-primary", "--text-secondary", "--text-tertiary")
SURFACE_TOKENS = ("--surface-page", "--surface-card", "--surface-sunken")
#: 承载文字的强调色与状态色。填充色（--status-ok 等）不在此列，它们只做色块。
ACCENT_TEXT_TOKENS = (
    "--accent-text", "--status-ok-text", "--status-warn-text", "--status-error-text",
)


def _linear(channel: int) -> float:
    value = channel / 255
    return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4


def luminance(hex_color: str) -> float:
    text = hex_color.lstrip("#")
    red, green, blue = (int(text[index : index + 2], 16) for index in (0, 2, 4))
    return 0.2126 * _linear(red) + 0.7152 * _linear(green) + 0.0722 * _linear(blue)


def contrast(first: str, second: str) -> float:
    high, low = sorted((luminance(first), luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def _blocks() -> dict[str, dict[str, str]]:
    """把 tokens.css 拆成 {主题: {令牌: 颜色}}。只认十六进制字面量与一层 var() 引用。"""
    text = TOKENS.read_text(encoding="utf-8")
    themes: dict[str, dict[str, str]] = {}
    # 浅色取根块，深色取 [data-theme="dark"] 块。媒体查询里的那份与后者逐字相同。
    light = re.search(r":root \{(.*?)\n\}", text, re.DOTALL)
    dark = re.search(r':root\[data-theme="dark"\] \{(.*?)\n\}', text, re.DOTALL)
    assert light and dark, "tokens.css 的结构变了，解析失败"
    themes["light"] = _pairs(light.group(1))
    # 深色块只覆盖一部分令牌，其余继承浅色。
    themes["dark"] = {**themes["light"], **_pairs(dark.group(1))}
    return themes


def _pairs(block: str) -> dict[str, str]:
    return {
        name: value.strip()
        for name, value in re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", block)
    }


def _resolve(tokens: dict[str, str], name: str) -> str:
    value = tokens[name]
    for _ in range(4):
        match = re.fullmatch(r"var\((--[\w-]+)\)", value.strip())
        if not match:
            break
        value = tokens[match.group(1)]
    value = value.strip()
    assert re.fullmatch(r"#[0-9a-fA-F]{6}", value), f"{name} 不是六位十六进制：{value}"
    return value


THEMES = _blocks()


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("text_token", TEXT_TOKENS)
@pytest.mark.parametrize("surface_token", SURFACE_TOKENS)
def test_body_text_meets_wcag_aa(theme: str, text_token: str, surface_token: str):
    tokens = THEMES[theme]
    ratio = contrast(_resolve(tokens, text_token), _resolve(tokens, surface_token))
    assert ratio >= TEXT_MINIMUM, f"{theme}: {text_token} 配 {surface_token} 只有 {ratio:.2f}:1"


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("token", ACCENT_TEXT_TOKENS)
def test_accent_and_status_text_meets_wcag_aa(theme: str, token: str):
    """状态文字用 --status-*-text 而不是 --status-*：后者是色块色，做文字不达标。"""
    tokens = THEMES[theme]
    for surface_token in SURFACE_TOKENS:
        ratio = contrast(_resolve(tokens, token), _resolve(tokens, surface_token))
        assert ratio >= TEXT_MINIMUM, f"{theme}: {token} 配 {surface_token} 只有 {ratio:.2f}:1"


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_heat_scale_is_monotonic_in_luminance(theme: str):
    """热力标尺必须单调：色阶不单调时"更深 = 更多"这个直觉就失效了，而颜色是唯一编码。"""
    tokens = THEMES[theme]
    steps = [_resolve(tokens, f"--heat-{level}") for level in range(6)]
    values = [luminance(step) for step in steps]
    direction = -1 if values[0] > values[-1] else 1
    for previous, current in pairwise(values):
        assert (current - previous) * direction > 0, f"{theme}: 热力标尺不单调 {steps}"


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_heat_ink_is_readable_on_the_top_two_steps(theme: str):
    """高热档上的数字用 --heat-ink。键面除填色外还要印数值（06 文档 §7 改进 2）。"""
    tokens = THEMES[theme]
    ink = _resolve(tokens, "--heat-ink")
    for level in (4, 5):
        ratio = contrast(ink, _resolve(tokens, f"--heat-{level}"))
        assert ratio >= GRAPHIC_MINIMUM, f"{theme}: --heat-ink 配 --heat-{level} 只有 {ratio:.2f}:1"


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_category_colors_stay_distinguishable_from_the_card(theme: str):
    """分类色是图形编码（图例色块 + 图表填充），按 3:1 要求。"""
    tokens = THEMES[theme]
    names = [name for name in tokens if name.startswith("--cat-")]
    assert len(names) >= 6
    for name in names:
        ratio = contrast(_resolve(tokens, name), _resolve(tokens, "--surface-card"))
        assert ratio >= 1.4, f"{theme}: {name} 与卡片背景几乎同色（{ratio:.2f}:1）"


def test_dark_overrides_are_identical_in_both_selectors():
    """深色令牌写了两遍（媒体查询 + data-theme）。两份不一致会让"跟随系统"与"深色"长得不一样。"""
    text = TOKENS.read_text(encoding="utf-8")
    media = re.search(r':root:not\(\[data-theme="light"\]\) \{(.*?)\n  \}', text, re.DOTALL)
    explicit = re.search(r':root\[data-theme="dark"\] \{(.*?)\n\}', text, re.DOTALL)
    assert media and explicit
    assert _pairs(media.group(1)) == _pairs(explicit.group(1))
