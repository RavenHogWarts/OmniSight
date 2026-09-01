"""``key_id`` 的权威定义（← KeyTrace ``keys.py``），04 文档 §3.2。

本文件回答两个问题，且只回答这两个：

1. **有哪些键。** ``key_id`` 是数据库、接口与前端共用的稳定标识，一旦写入就不再
   改名——``agg_*`` 表以它为主键，改名等于数据迁移。
2. **每个键显示成什么。** 标签是展示用的，可以随 i18n 改；``key_id`` 不可以。

它**不**回答"某个原生码是哪个键"——那是各平台适配器的事（见 ``adapters/hid.py``
与 ``adapters/windows/keymap_native.py``）。这个方向是设计的核心约束：原设计里
``key_id`` 事实上是 Windows ``VK_MAP`` 的派生产物，跨平台后会变成隐藏耦合。

标签**故意有重复**：左右 Shift 都显示 "Shift"、小键盘数字与主键盘数字都显示
"1"。重复的是标签，``id`` 必须唯一——它对应键盘上的一个物理格子。
"""

from __future__ import annotations

from dataclasses import dataclass

from ..adapters import hid


@dataclass(frozen=True, slots=True)
class KeyDefinition:
    id: str
    label: str
    #: 该键对应的 USB HID Usage ID；``None`` 表示没有任何平台能报出它（应视为 bug，
    #: 由 ``test_keymap`` 固定住）。
    hid_usage: int | None = None
    #: 标准指法下按它的手指（05 文档 §4 的人体工学分析）。见 :data:`FINGERS`。
    finger: str = "unknown"
    #: 所在键盘分区，供"行分布"统计使用。见 :data:`ROWS`。
    row: str = "unknown"


def _define(pairs: tuple[tuple[str, str], ...]) -> tuple[KeyDefinition, ...]:
    return tuple(
        KeyDefinition(
            key_id,
            label,
            hid.hid_for_key_id(key_id),
            finger=_FINGER_BY_KEY.get(key_id, "unknown"),
            row=_ROW_BY_KEY.get(key_id, "unknown"),
        )
        for key_id, label in pairs
    )



#: 手指 id → (展示名, 左右手)。``neutral`` 的键不计入左右平衡：空格通常是第一大键，
#: 把它单方面算给某只手会让"左右手负荷"这个指标失去意义（05 文档 §4）。
FINGERS: tuple[tuple[str, str, str], ...] = (
    ("left_pinky", "左小指", "left"),
    ("left_ring", "左无名指", "left"),
    ("left_middle", "左中指", "left"),
    ("left_index", "左食指", "left"),
    ("left_thumb", "左拇指", "left"),
    ("thumb", "拇指", "neutral"),
    ("right_thumb", "右拇指", "right"),
    ("right_index", "右食指", "right"),
    ("right_middle", "右中指", "right"),
    ("right_ring", "右无名指", "right"),
    ("right_pinky", "右小指", "right"),
)

FINGER_NAMES: dict[str, str] = {finger: name for finger, name, _hand in FINGERS}
FINGER_HANDS: dict[str, str] = {finger: hand for finger, _name, hand in FINGERS}

#: 键盘分区 id → 展示名。``home`` 指主键行（05 文档 §4 的取值），与 ``home`` 这个
#: **键** id 同名但属于不同命名空间。
ROWS: tuple[tuple[str, str], ...] = (
    ("function", "功能行"),
    ("number", "数字行"),
    ("top", "上排"),
    ("home", "主键行"),
    ("bottom", "下排"),
    ("modifier", "修饰行"),
    ("navigation", "导航区"),
    ("numpad", "小键盘"),
)

ROW_NAMES: dict[str, str] = dict(ROWS)

#: 被视为修饰键的 key_id（``modifier_ratio`` 的分子）。
#: **口径**：这里数的是"修饰键自身被按下的次数"，不是"按某个键时按住了修饰键"——
#: 后者需要和弦信息，而我们既不记录按键顺序也不扫原始事件（08 文档 §2、01 文档 §4.1）。
MODIFIER_KEYS: frozenset[str] = frozenset(
    {
        "shift_left", "shift_right", "control_left", "control_right",
        "alt_left", "alt_right", "win_left", "win_right", "caps_lock", "menu",
    }
)

_FINGER_GROUPS: dict[str, tuple[str, ...]] = {
    "left_pinky": (
        "esc", "f1", "grave", "digit1", "tab", "key_q", "caps_lock", "key_a",
        "shift_left", "iso_backslash", "key_z", "control_left", "win_left",
    ),
    "left_ring": ("f2", "digit2", "key_w", "key_s", "key_x"),
    "left_middle": ("f3", "digit3", "key_e", "key_d", "key_c"),
    "left_index": (
        "f4", "f5", "digit4", "digit5", "key_r", "key_t",
        "key_f", "key_g", "key_v", "key_b",
    ),
    "left_thumb": ("alt_left",),
    "thumb": ("space",),
    "right_thumb": ("alt_right", "win_right", "numpad_0"),
    "right_index": (
        "f6", "f7", "digit6", "digit7", "key_y", "key_u", "key_h", "key_j",
        "key_n", "key_m", "print_screen", "insert", "delete", "arrow_left",
        "numpad_1", "numpad_4", "numpad_7",
        "f13", "f17", "f21",
    ),
    "right_middle": (
        "f8", "digit8", "key_i", "key_k", "comma", "scroll_lock",
        "home", "end", "arrow_up", "arrow_down",
        "numpad_2", "numpad_5", "numpad_8",
        "f14", "f18", "f22",
    ),
    "right_ring": (
        "f9", "digit9", "key_o", "key_l", "period", "pause",
        "page_up", "page_down", "arrow_right",
        "numpad_3", "numpad_6", "numpad_9", "numpad_decimal",
        "f15", "f19", "f23",
    ),
    "right_pinky": (
        "f10", "f11", "f12", "digit0", "minus", "equal", "backspace", "key_p",
        "bracket_left", "bracket_right", "backslash", "semicolon", "quote",
        "enter", "slash", "shift_right", "menu", "control_right",
        "num_lock", "numpad_divide", "numpad_multiply", "numpad_subtract",
        "numpad_add", "numpad_enter", "numpad_equal",
        "f16", "f20", "f24",
    ),
}

_ROW_GROUPS: dict[str, tuple[str, ...]] = {
    "function": (
        "esc", "print_screen", "scroll_lock", "pause",
        *(f"f{index}" for index in range(1, 25)),
    ),
    "number": (
        "grave", *(f"digit{index}" for index in (*range(1, 10), 0)),
        "minus", "equal", "backspace",
    ),
    "top": (
        "tab", *(f"key_{letter}" for letter in "qwertyuiop"),
        "bracket_left", "bracket_right", "backslash",
    ),
    "home": (
        "caps_lock", *(f"key_{letter}" for letter in "asdfghjkl"),
        "semicolon", "quote", "enter",
    ),
    "bottom": (
        "shift_left", "iso_backslash", *(f"key_{letter}" for letter in "zxcvbnm"),
        "comma", "period", "slash", "shift_right",
    ),
    "modifier": (
        "control_left", "win_left", "alt_left", "space",
        "alt_right", "win_right", "menu", "control_right",
    ),
    "navigation": (
        "insert", "home", "page_up", "delete", "end", "page_down",
        "arrow_up", "arrow_left", "arrow_down", "arrow_right",
    ),
    "numpad": (
        "num_lock", "numpad_divide", "numpad_multiply", "numpad_subtract",
        "numpad_add", "numpad_enter", "numpad_decimal", "numpad_equal",
        *(f"numpad_{index}" for index in range(0, 10)),
    ),
}


def _invert(groups: dict[str, tuple[str, ...]]) -> dict[str, str]:
    """展开分组表。同一个键出现在两个分组里是笔误，直接拒绝加载。"""
    result: dict[str, str] = {}
    for group, key_ids in groups.items():
        for key_id in key_ids:
            if key_id in result:
                raise AssertionError(f"{key_id!r} 同时属于 {result[key_id]!r} 与 {group!r}")
            result[key_id] = group
    return result


_FINGER_BY_KEY = _invert(_FINGER_GROUPS)
_ROW_BY_KEY = _invert(_ROW_GROUPS)

_DEFINITIONS: tuple[tuple[str, str], ...] = (
    # ── 功能键行 ──────────────────────────────────────────────────────────
    ("esc", "Esc"),
    *((f"f{index}", f"F{index}") for index in range(1, 13)),
    ("print_screen", "PrtSc"),
    ("scroll_lock", "ScrLk"),
    ("pause", "Pause"),
    # ── 数字行 ────────────────────────────────────────────────────────────
    ("grave", "~"),
    *((f"digit{index}", str(index)) for index in range(1, 10)),
    ("digit0", "0"),
    ("minus", "-"),
    ("equal", "="),
    ("backspace", "Backspace"),
    # ── 字母区 ────────────────────────────────────────────────────────────
    ("tab", "Tab"),
    *((f"key_{letter.lower()}", letter) for letter in "QWERTYUIOP"),
    ("bracket_left", "["),
    ("bracket_right", "]"),
    ("backslash", "\\"),
    ("caps_lock", "Caps Lock"),
    *((f"key_{letter.lower()}", letter) for letter in "ASDFGHJKL"),
    ("semicolon", ";"),
    ("quote", "'"),
    ("enter", "Enter"),
    ("shift_left", "Shift"),
    # ISO 105 键键盘上左 Shift 右侧多出的第 102 键；ANSI 键盘上不存在。首期就要有
    # 定义，否则欧洲用户按下它会被静默丢弃（12 文档 §5 已决定首期做 iso105 布局族）。
    ("iso_backslash", "\\"),
    *((f"key_{letter.lower()}", letter) for letter in "ZXCVBNM"),
    ("comma", ","),
    ("period", "."),
    ("slash", "/"),
    ("shift_right", "Shift"),
    # ── 修饰键行 ──────────────────────────────────────────────────────────
    ("control_left", "Ctrl"),
    ("win_left", "Win"),
    ("alt_left", "Alt"),
    ("space", "Space"),
    ("alt_right", "Alt"),
    ("win_right", "Win"),
    ("menu", "Menu"),
    ("control_right", "Ctrl"),
    # ── 编辑与导航簇 ──────────────────────────────────────────────────────
    ("insert", "Ins"),
    ("home", "Home"),
    ("page_up", "PgUp"),
    ("delete", "Del"),
    ("end", "End"),
    ("page_down", "PgDn"),
    ("arrow_up", "↑"),
    ("arrow_left", "←"),
    ("arrow_down", "↓"),
    ("arrow_right", "→"),
    # ── 小键盘 ────────────────────────────────────────────────────────────
    ("num_lock", "Num"),
    ("numpad_divide", "/"),
    ("numpad_multiply", "*"),
    ("numpad_subtract", "-"),
    *((f"numpad_{index}", str(index)) for index in range(7, 10)),
    ("numpad_add", "+"),
    *((f"numpad_{index}", str(index)) for index in range(4, 7)),
    *((f"numpad_{index}", str(index)) for index in range(1, 4)),
    ("numpad_enter", "Enter"),
    ("numpad_0", "0"),
    ("numpad_decimal", "."),
    ("numpad_equal", "="),
    # ── 扩展功能键 ────────────────────────────────────────────────────────
    # 部分全尺寸键盘与 macOS 键盘有 F13~F24。定义它们的成本是一行，不定义的代价是
    # 用户按下后什么都不记录且无从发现。
    *((f"f{index}", f"F{index}") for index in range(13, 25)),
)

KEYS: tuple[KeyDefinition, ...] = _define(_DEFINITIONS)

KEY_BY_ID: dict[str, KeyDefinition] = {key.id: key for key in KEYS}

KEY_IDS: frozenset[str] = frozenset(KEY_BY_ID)


def label_for(key_id: str) -> str:
    """展示标签；未知 ``key_id`` 原样返回，绝不抛异常。

    未知不代表出错——旧库里可能存着某个已改名的 ``key_id``，界面应该照样能画出来
    （标记为 ``orphan_keys``，见 05 文档 §4），而不是让整个面板 500。
    """
    definition = KEY_BY_ID.get(key_id)
    return definition.label if definition else key_id


def is_known(key_id: str) -> bool:
    return key_id in KEY_BY_ID


__all__ = [
    "FINGERS",
    "FINGER_HANDS",
    "FINGER_NAMES",
    "KEYS",
    "KEY_BY_ID",
    "KEY_IDS",
    "MODIFIER_KEYS",
    "ROWS",
    "ROW_NAMES",
    "KeyDefinition",
    "is_known",
    "label_for",
]
