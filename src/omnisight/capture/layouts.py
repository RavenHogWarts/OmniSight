"""键盘布局族：**布局是数据，不是 DOM**（05 文档 §4、06 文档 §7.1）。

旧 KeyTrace 把 104 键写死成 860 行 HTML，换一种布局等于重写页面——欧洲用户因此一直
看着错误的键盘图，第 102 键无处显示。这里把布局变成服务端下发的数据，前端只有一个
渲染器：``iso105`` 与 ``ansi104`` 只是同一个渲染器的两份输入。

三条约束：

1. **``id`` 必须是 :mod:`omnisight.capture.keymap` 里的 ``key_id``**（除占位的
   ``gap``）。有测试固定这一点：布局里出现一个拼错的 id，那个键会永远显示 0 而不报错。
2. **几何在这里，标签不在这里。** 标签统一由 ``keymap.label_for`` 提供，否则同一个键
   在键盘图与 Top 榜里可能显示成两种写法。
3. **只声明已实现的族。** 配置允许 ``tkl87`` / ``mac_ansi`` / ``mac_iso``（它们是
   M8/M9 的事），但设置页的可选项只列 :data:`IMPLEMENTED_FAMILIES`——让用户选一个
   选完就报错的值，比不给这个选项更糟。
"""

from __future__ import annotations

from dataclasses import dataclass

from . import keymap

#: 占位空隙的 id。它只有宽度，没有数据。
GAP = "gap"


@dataclass(frozen=True, slots=True)
class KeySlot:
    """布局中的一个格子。``w`` / ``h`` 以"标准键宽"为单位，前端乘 ``--u`` 得像素。"""

    id: str
    w: float = 1.0
    h: float = 1.0
    #: 非矩形键。目前只有 ``iso_enter``——ISO 回车跨两行且是 L 形，无法用"矩形 + 宽度
    #: 倍数"表达。只为这一个键留一个形状标记，不引入通用多边形机制（06 文档 §7.1）。
    shape: str | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {"id": self.id, "w": self.w}
        if self.id != GAP:
            payload["label"] = keymap.label_for(self.id)
        if self.h != 1.0:
            payload["h"] = self.h
        if self.shape:
            payload["shape"] = self.shape
        return payload


def _k(key_id: str, w: float = 1.0, h: float = 1.0, shape: str | None = None) -> KeySlot:
    return KeySlot(key_id, w, h, shape)


def _gap(w: float) -> KeySlot:
    return KeySlot(GAP, w)


def _keys(*key_ids: str) -> tuple[KeySlot, ...]:
    return tuple(_k(key_id) for key_id in key_ids)


def _letters(letters: str) -> tuple[KeySlot, ...]:
    return _keys(*(f"key_{letter}" for letter in letters))


@dataclass(frozen=True, slots=True)
class Layout:
    family: str
    name: str
    rows: tuple[tuple[KeySlot, ...], ...]

    @property
    def key_ids(self) -> frozenset[str]:
        """布局里真正的键（不含 ``gap``）。热力图的 ``keys`` 数组以此为全集。"""
        return frozenset(slot.id for row in self.rows for slot in row if slot.id != GAP)

    @property
    def max_units(self) -> float:
        return max(sum(slot.w for slot in row) for row in self.rows)

    def to_dict(self, *, source: str) -> dict[str, object]:
        return {
            "family": self.family,
            "name": self.name,
            "source": source,
            "unit_hint": {"rows": len(self.rows), "max_units": self.max_units},
            "rows": [[slot.to_dict() for slot in row] for row in self.rows],
        }


# ── 各行的公共部分 ──────────────────────────────────────────────────────
#: 功能键行。主键区宽 15 单位，右侧 3 个键正对导航簇（06 文档 §7 的示意图）。
_FUNCTION_ROW: tuple[KeySlot, ...] = (
    _k("esc"),
    _gap(1),
    *_keys("f1", "f2", "f3", "f4"),
    _gap(0.5),
    *_keys("f5", "f6", "f7", "f8"),
    _gap(0.5),
    *_keys("f9", "f10", "f11", "f12"),
    _gap(0.5),
    *_keys("print_screen", "scroll_lock", "pause"),
    _gap(0.5),
    _gap(4),
)

_NUMBER_ROW: tuple[KeySlot, ...] = (
    _k("grave"),
    *_keys(*(f"digit{index}" for index in (*range(1, 10), 0))),
    *_keys("minus", "equal"),
    _k("backspace", 2),
    _gap(0.5),
    *_keys("insert", "home", "page_up"),
    _gap(0.5),
    *_keys("num_lock", "numpad_divide", "numpad_multiply", "numpad_subtract"),
)

_NAV_MID: tuple[KeySlot, ...] = (_gap(0.5), *_keys("delete", "end", "page_down"), _gap(0.5))

_MODIFIER_ROW: tuple[KeySlot, ...] = (
    _k("control_left", 1.25),
    _k("win_left", 1.25),
    _k("alt_left", 1.25),
    _k("space", 6.25),
    _k("alt_right", 1.25),
    _k("win_right", 1.25),
    _k("menu", 1.25),
    _k("control_right", 1.25),
    _gap(0.5),
    *_keys("arrow_left", "arrow_down", "arrow_right"),
    _gap(0.5),
    _k("numpad_0", 2),
    _k("numpad_decimal"),
    _gap(1),
)

#: 小键盘第 3、5 行。末尾那 1 单位空隙是双高键（``+`` / ``Enter``）占掉的位置——
#: 如实留出来，每行宽度才都是 23 单位，渲染器不必反推"这一行为什么短了一格"。
_NUMPAD_MID: tuple[KeySlot, ...] = (
    _gap(0.5),
    _gap(3),
    _gap(0.5),
    *_keys("numpad_4", "numpad_5", "numpad_6"),
    _gap(1),
)
_ARROW_UP: tuple[KeySlot, ...] = (_gap(0.5), _gap(1), _k("arrow_up"), _gap(1), _gap(0.5))

ANSI104 = Layout(
    family="ansi104",
    name="ANSI 104 键",
    rows=(
        _FUNCTION_ROW,
        _NUMBER_ROW,
        (
            _k("tab", 1.5),
            *_letters("qwertyuiop"),
            *_keys("bracket_left", "bracket_right"),
            _k("backslash", 1.5),
            *_NAV_MID,
            *_keys("numpad_7", "numpad_8", "numpad_9"),
            _k("numpad_add", 1, 2),
        ),
        (
            _k("caps_lock", 1.75),
            *_letters("asdfghjkl"),
            *_keys("semicolon", "quote"),
            _k("enter", 2.25),
            *_NUMPAD_MID,
        ),
        (
            _k("shift_left", 2.25),
            *_letters("zxcvbnm"),
            *_keys("comma", "period", "slash"),
            _k("shift_right", 2.75),
            *_ARROW_UP,
            *_keys("numpad_1", "numpad_2", "numpad_3"),
            _k("numpad_enter", 1, 2),
        ),
        _MODIFIER_ROW,
    ),
)

ISO105 = Layout(
    family="iso105",
    name="ISO 105 键",
    rows=(
        _FUNCTION_ROW,
        _NUMBER_ROW,
        (
            _k("tab", 1.5),
            *_letters("qwertyuiop"),
            *_keys("bracket_left", "bracket_right"),
            # L 形回车：上半部分在本行，下半部分由 CSS 伪元素补出（06 文档 §7.1）。
            _k("enter", 1.5, 2, shape="iso_enter"),
            *_NAV_MID,
            *_keys("numpad_7", "numpad_8", "numpad_9"),
            _k("numpad_add", 1, 2),
        ),
        (
            _k("caps_lock", 1.75),
            *_letters("asdfghjkl"),
            *_keys("semicolon", "quote", "backslash"),
            # 回车下半部分占据的位置：布局数据里如实留出空隙，渲染器才不会把
            # 后面的键顶进去（ISO 的这一行只有 13.75 单位是真键）。
            _gap(1.25),
            *_NUMPAD_MID,
        ),
        (
            _k("shift_left", 1.25),
            _k("iso_backslash"),
            *_letters("zxcvbnm"),
            *_keys("comma", "period", "slash"),
            _k("shift_right", 2.75),
            *_ARROW_UP,
            *_keys("numpad_1", "numpad_2", "numpad_3"),
            _k("numpad_enter", 1, 2),
        ),
        _MODIFIER_ROW,
    ),
)


#: 已实现的布局族。配置的取值范围更宽（含 M8/M9 的 ``tkl87`` / ``mac_*``），
#: 但设置页只应列出这里的值——见模块文档第 3 条。
FAMILIES: dict[str, Layout] = {ANSI104.family: ANSI104, ISO105.family: ISO105}

IMPLEMENTED_FAMILIES: tuple[str, ...] = tuple(FAMILIES)

#: 各平台的默认族。进程**无法可靠得知用户键盘的物理型号**（Windows 的输入法语言不等于
#: 键盘布局，笔记本外接 ISO 键盘更是常见），因此默认值只是一个猜测，用户可覆盖
#: （05 文档 §7）。
_PLATFORM_DEFAULT: dict[str, str] = {
    "windows": "ansi104",
    "linux_x11": "ansi104",
    "linux_wayland": "ansi104",
    "generic": "ansi104",
    # macOS 的 mac_ansi / mac_iso 排在 M9；在它到来之前如实退回 ansi104，
    # 而不是声明一个不存在的族。
    "macos": "ansi104",
}


def default_family(platform_id: str) -> str:
    return _PLATFORM_DEFAULT.get(platform_id, "ansi104")


def get(family: str) -> Layout | None:
    return FAMILIES.get(family)


def all_layout_key_ids() -> frozenset[str]:
    """全部已实现布局用到的键位并集，供 CI 断言它是 ``keymap`` 全集的子集。"""
    result: frozenset[str] = frozenset()
    for layout in FAMILIES.values():
        result |= layout.key_ids
    return result


__all__ = [
    "ANSI104",
    "FAMILIES",
    "GAP",
    "IMPLEMENTED_FAMILIES",
    "ISO105",
    "KeySlot",
    "Layout",
    "all_layout_key_ids",
    "default_family",
    "get",
]
