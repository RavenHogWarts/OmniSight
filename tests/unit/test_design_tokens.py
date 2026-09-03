"""设计令牌的对比度与色彩可辨性（06 文档 §13、14 文档 §8.1）。

这条判据只有算出来才算数。文档给的值本身就不达标——`--text-secondary: #77777d`
在白底上是 4.45:1、在 `--surface-sunken` 上只有 3.84:1，而 `--text-tertiary: #9a9aa3`
只有 2.4:1。tokens.css 因此用了更深/更亮的值，这个测试是那次调整的依据。

**对比度不足以判断颜色能不能分开。** `--cat-productivity: #2f7cf6` 与
`--cat-development: #7c62e0` 各自对卡片都有 3:1 以上，但两者之间在绿色盲下的
OKLab ΔE 只有 3.4——目标用户机器上最大的两个类别，实际不可辨（14 文档 §2.2）。
因此这里除了 WCAG 对比度，还算两件事：

1. **CVD 分离**：Machado 2009 的色觉缺陷模拟矩阵，protan / deutan / tritan 三种，
   模拟后在 OKLab 里量 ΔE。
2. **序数色阶**：单调、相邻明度差、最浅档对表面的对比度。

两者都是纯数值代码、无第三方依赖。移进仓库是因为**判据应该在仓库里可复跑**——
在这之前它依赖一个外部技能脚本。

**这个测试检查的是令牌层，不是每一处实际渲染。** 它保证"任何文字色配任何表面色"
都达标，于是组件层怎么组合都不会掉到 4.5:1 以下；但它测不出"某处用了硬编码颜色"
——那由 check_frontend 的模式检查与人工验收覆盖。
"""

from __future__ import annotations

import re
from itertools import combinations, pairwise
from pathlib import Path

import pytest

TOKENS = (
    Path(__file__).resolve().parents[2]
    / "src" / "omnisight" / "presentation" / "static" / "css" / "tokens.css"
)

#: WCAG 2.1 AA：正文 4.5:1，大字与图形 3:1。
TEXT_MINIMUM = 4.5
GRAPHIC_MINIMUM = 3.0

#: 红绿色觉缺陷（protan / deutan）下的 OKLab ΔE 下限。这两种合计约占男性 8%，
#: 是硬门槛。
CVD_DELTA_MINIMUM = 6.0
#: 蓝黄色觉缺陷（tritan）下的下限，刻意更低。
#:
#: **这是一个有依据的取舍，不是把门槛调到能过为止。** tritanopia 会把蓝与青压到
#: 一起，而"效率 = 蓝、沟通 = 青"这两个色相是 protan/deutan 那 8% 最依赖的一对；
#: 要让它们在 tritan 下也分开，就得把其中一个移出蓝青区，代价是红绿缺陷者反而更难
#: 分辨。tritanopia 的患病率约 0.01%（比红绿缺陷低三个数量级），因此这里保住多数，
#: 并用**非颜色编码**兜住少数：类别永远带文字标签，构成条带内联标签与悬停读数，
#: 键面带数值与表格视图（14 文档 §6 的"色阶的非颜色编码"）。
TRITAN_DELTA_MINIMUM = 3.5
#: 正常视觉下的 ΔE 下限。这是硬门槛：低于它连全色觉的人都难分辨。
NORMAL_DELTA_MINIMUM = 15.0
#: 序数色阶相邻档的最小明度差（OKLab L）。
ORDINAL_STEP_MINIMUM = 0.06
#: 序数色阶最浅档对承载面的最小对比度。
ORDINAL_LIGHT_END_MINIMUM = 2.0

TEXT_TOKENS = ("--text-primary", "--text-secondary", "--text-tertiary")
SURFACE_TOKENS = ("--surface-page", "--surface-card", "--surface-sunken")
#: 承载文字的强调色与状态色。填充色（--status-ok 等）不在此列，它们只做色块。
ACCENT_TEXT_TOKENS = (
    "--accent-text", "--status-ok-text", "--status-warn-text", "--status-error-text",
)

#: 四个**带彩度的身份色**。它们两两都可能并置（环形/列表/应用行的顺序由数据决定），
#: 所以要过 all-pairs 而不只是相邻对。
IDENTITY_TOKENS = (
    "--cat-development",
    "--cat-productivity",
    "--cat-communication",
    "--cat-entertainment",
)
#: 两个**去强调灰**。它们刻意不带彩度——职责就是不承载身份，因此不参与 CVD 检查，
#: 只要求彼此的明度拉得开（14 文档 §2.3）。
NEUTRAL_CATEGORY_TOKENS = ("--cat-system", "--cat-uncategorized")

#: 色阶的五个档。零态不在其中：它是承载面本身（键面 = 卡片色，格子 = --heat-0）。
HEAT_STEPS = tuple(f"--heat-{level}" for level in range(1, 6))


# ── 颜色空间 ──────────────────────────────────────────────────────────
def _linear(channel: int) -> float:
    value = channel / 255
    return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4


def _rgb(hex_color: str) -> tuple[int, int, int]:
    text = hex_color.lstrip("#")
    return tuple(int(text[index : index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]


def luminance(hex_color: str) -> float:
    red, green, blue = _rgb(hex_color)
    return 0.2126 * _linear(red) + 0.7152 * _linear(green) + 0.0722 * _linear(blue)


def contrast(first: str, second: str) -> float:
    high, low = sorted((luminance(first), luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def oklab(hex_color: str) -> tuple[float, float, float]:
    """sRGB → OKLab。感知均匀，因此这里的欧氏距离才对应"看起来差多少"。"""
    red, green, blue = (_linear(channel) for channel in _rgb(hex_color))
    long_ = (0.4122214708 * red + 0.5363325363 * green + 0.0514459929 * blue) ** (1 / 3)
    medium = (0.2119034982 * red + 0.6806995451 * green + 0.1073969566 * blue) ** (1 / 3)
    short = (0.0883024619 * red + 0.2817188376 * green + 0.6299787005 * blue) ** (1 / 3)
    return (
        0.2104542553 * long_ + 0.7936177850 * medium - 0.0040720468 * short,
        1.9779984951 * long_ - 2.4285922050 * medium + 0.4505937099 * short,
        0.0259040371 * long_ + 0.7827717662 * medium - 0.8086757660 * short,
    )


def delta_e(first: str, second: str) -> float:
    """OKLab 欧氏距离 ×100。与 dataviz 校验器同一把尺子，数值可以直接对照。"""
    left, right = oklab(first), oklab(second)
    return 100 * sum((a - b) ** 2 for a, b in zip(left, right, strict=True)) ** 0.5


#: Machado / Oliveira / Fernandes 2009 的色觉缺陷模拟矩阵（严重度 1.0）。
#: 在**线性** sRGB 上作用。
CVD_MATRICES: dict[str, tuple[tuple[float, ...], ...]] = {
    "protan": (
        (0.152286, 1.052583, -0.204868),
        (0.114503, 0.786281, 0.099216),
        (-0.003882, -0.048116, 1.051998),
    ),
    "deutan": (
        (0.367322, 0.860646, -0.227968),
        (0.280085, 0.672501, 0.047413),
        (-0.011820, 0.042940, 0.968881),
    ),
    "tritan": (
        (1.255528, -0.076749, -0.178779),
        (-0.078411, 0.930809, 0.147602),
        (0.004733, 0.691367, 0.303900),
    ),
}


def simulate(hex_color: str, kind: str) -> str:
    """把一个颜色变成"色觉缺陷者看到的样子"，仍以十六进制返回。"""
    channels = [_linear(channel) for channel in _rgb(hex_color)]
    matrix = CVD_MATRICES[kind]
    mixed = [sum(row[i] * channels[i] for i in range(3)) for row in matrix]
    out = []
    for value in mixed:
        clamped = min(1.0, max(0.0, value))
        srgb = (
            12.92 * clamped
            if clamped <= 0.0031308
            else 1.055 * clamped ** (1 / 2.4) - 0.055
        )
        out.append(round(min(255, max(0, srgb * 255))))
    return "#%02x%02x%02x" % tuple(out)


# ── tokens.css 解析 ───────────────────────────────────────────────────
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


# ── WCAG 对比度 ───────────────────────────────────────────────────────
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


# ── 身份色的可辨性 ────────────────────────────────────────────────────
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_identity_colors_are_distinguishable_in_all_pairs(theme: str):
    """四个身份色**两两**都要能分开，不只是相邻对。

    环形图的扇区顺序、应用列表的行序都由数据决定，所以任意两个类别色都可能并置
    ——这是 all-pairs 场景（14 文档 §2.2）。

    红绿缺陷按 6.0 卡，tritan 按 3.5——理由见 TRITAN_DELTA_MINIMUM 的注释。
    """
    tokens = THEMES[theme]
    colors = {name: _resolve(tokens, name) for name in IDENTITY_TOKENS}
    for left, right in combinations(colors, 2):
        first, second = colors[left], colors[right]
        normal = delta_e(first, second)
        assert normal >= NORMAL_DELTA_MINIMUM, (
            f"{theme}: {left} {first} 与 {right} {second} 正常视觉 ΔE 仅 {normal:.1f}"
        )
        for kind in CVD_MATRICES:
            floor = TRITAN_DELTA_MINIMUM if kind == "tritan" else CVD_DELTA_MINIMUM
            simulated = delta_e(simulate(first, kind), simulate(second, kind))
            assert simulated >= floor, (
                f"{theme}: {left} 与 {right} 在 {kind} 下 ΔE 仅 {simulated:.1f}（下限 {floor}）"
            )


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_muted_category_greys_are_far_apart_in_lightness(theme: str):
    """系统 / 未分类是两个去强调灰。它们不承载身份，但**必须彼此分得开**。

    现状两者正常视觉 ΔE 只有 13.3（14 文档 §2.3），在图例里读起来是同一个灰。
    """
    tokens = THEMES[theme]
    first, second = (_resolve(tokens, name) for name in NEUTRAL_CATEGORY_TOKENS)
    value = delta_e(first, second)
    assert value >= NORMAL_DELTA_MINIMUM, (
        f"{theme}: 两个去强调灰 {first} / {second} 的 ΔE 仅 {value:.1f}"
    )


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_category_colors_stay_distinguishable_from_the_card(theme: str):
    """分类色是图形编码（图例色块 + 图表填充），按 3:1 要求。

    这条断言曾经是 `>= 1.4`——为了让 `--cat-entertainment: #f2933c`（对白底 2.33:1）
    通过，于是它不检查它声称检查的东西（14 文档 §2.15）。现在门槛与 docstring 一致。
    """
    tokens = THEMES[theme]
    names = [name for name in tokens if name.startswith("--cat-")]
    assert len(names) >= 6
    for name in names:
        ratio = contrast(_resolve(tokens, name), _resolve(tokens, "--surface-card"))
        assert ratio >= GRAPHIC_MINIMUM, f"{theme}: {name} 对卡片只有 {ratio:.2f}:1"


# ── 色阶 ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_heat_scale_is_monotonic_in_luminance(theme: str):
    """热力标尺必须单调：色阶不单调时"更深 = 更多"这个直觉就失效了。"""
    tokens = THEMES[theme]
    steps = [_resolve(tokens, name) for name in HEAT_STEPS]
    values = [luminance(step) for step in steps]
    direction = -1 if values[0] > values[-1] else 1
    for previous, current in pairwise(values):
        assert (current - previous) * direction > 0, f"{theme}: 热力标尺不单调 {steps}"


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_heat_steps_are_far_enough_apart(theme: str):
    """相邻档的明度差 ≥ 0.06（OKLab L）。太近时五档看起来像三档。"""
    tokens = THEMES[theme]
    steps = [_resolve(tokens, name) for name in HEAT_STEPS]
    lightness = [oklab(step)[0] for step in steps]
    for (index, previous), current in zip(
        enumerate(lightness), lightness[1:], strict=False
    ):
        gap = abs(current - previous)
        assert gap >= ORDINAL_STEP_MINIMUM, (
            f"{theme}: --heat-{index + 1} 与 --heat-{index + 2} 的明度差仅 {gap:.3f}"
        )


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_lightest_heat_step_is_visible_against_its_surface(theme: str):
    """最浅档对承载面 ≥ 2:1。

    这一条是"按过一次"与"从没按过"能不能分开的判据。现状用 color-mix 连续插值时
    `--heat-0` 与 `--heat-1` 只差 1.07:1，两者实际同色（14 文档 §2.4）。
    键面的零态是卡片色，格子的零态是 --heat-0，两个都要过。
    """
    tokens = THEMES[theme]
    lightest = _resolve(tokens, "--heat-1")
    for surface_token in ("--surface-card", "--heat-0"):
        ratio = contrast(lightest, _resolve(tokens, surface_token))
        assert ratio >= ORDINAL_LIGHT_END_MINIMUM, (
            f"{theme}: --heat-1 对 {surface_token} 只有 {ratio:.2f}:1"
        )


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_every_heat_step_can_carry_a_readable_number(theme: str):
    """**每一档**都要有一侧墨色达到正文级 4.5:1。

    键面数字是这张热图唯一的非颜色编码（06 文档 §7 改进 2）。现状只验最深两档，
    而按真实渲染算，浅色下第 3 档白字只有 3.11:1（14 文档 §3.2）。
    """
    tokens = THEMES[theme]
    ink = _resolve(tokens, "--heat-ink")
    body = _resolve(tokens, "--text-primary")
    for index, name in enumerate(HEAT_STEPS, start=1):
        step = _resolve(tokens, name)
        best = max(contrast(ink, step), contrast(body, step))
        assert best >= TEXT_MINIMUM, (
            f"{theme}: --heat-{index} 上两种墨色最好也只有 {best:.2f}:1"
        )


def test_dark_overrides_are_identical_in_both_selectors():
    """深色令牌写了两遍（媒体查询 + data-theme）。两份不一致会让"跟随系统"与"深色"长得不一样。"""
    text = TOKENS.read_text(encoding="utf-8")
    media = re.search(r':root:not\(\[data-theme="light"\]\) \{(.*?)\n  \}', text, re.DOTALL)
    explicit = re.search(r':root\[data-theme="dark"\] \{(.*?)\n\}', text, re.DOTALL)
    assert media and explicit
    assert _pairs(media.group(1)) == _pairs(explicit.group(1))
