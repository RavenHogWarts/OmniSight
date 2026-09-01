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


def _define(pairs: tuple[tuple[str, str], ...]) -> tuple[KeyDefinition, ...]:
    return tuple(
        KeyDefinition(key_id, label, hid.hid_for_key_id(key_id)) for key_id, label in pairs
    )


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


__all__ = ["KEYS", "KEY_BY_ID", "KEY_IDS", "KeyDefinition", "is_known", "label_for"]
