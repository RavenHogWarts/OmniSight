"""USB HID Usage ID 枢轴表（Keyboard/Keypad page 0x07），04 文档 §3.2。

方向是刻意的：**``key_id`` 是标准，各平台的原生位置码是需要映射到它的输入。**
若反过来（``key_id`` 由 Windows 的 ``VK_MAP`` 派生，KeyTrace 现状如此），每加一个
平台就要回头改动键定义。

为避免写 N×N 的映射表，中间插一层 HID usage：

    Windows 扫描码 ─┐
    macOS kVK_*  ──┼─► HID Usage ID ─► key_id ─► 数据库 / API / 前端
    Linux KEY_*  ──┘

选 HID 做枢轴是因为三者本质相同——都是物理位置码，且键盘固件上报的本来就是 HID
usage，各操作系统只是各自做了一层转换。每个平台因此只需维护一张 ``native → HID``
表，各自单元测试。

**为什么这张表在 ``adapters/`` 而不在 ``capture/``**：每个适配器都要用它，而
适配器不允许依赖上层（02 文档 §1 的分层规则）。``capture/keymap.py`` 持有
``key_id → 标签``，并向下依赖本文件取 ``hid_usage``——两处零重复。

HID usage **不落盘作为身份**，只作为 ``raw_key_events.hid_usage`` 的诊断列
（03 文档 §2.5）：归一化逻辑出 bug 时可以从原生码重放修正。
"""

from __future__ import annotations

# ── 字母与数字 ────────────────────────────────────────────────────────────
_LETTERS = {0x04 + index: f"key_{chr(ord('a') + index)}" for index in range(26)}
_DIGITS = {0x1E + index: f"digit{index + 1}" for index in range(9)}

# ── 功能键 ────────────────────────────────────────────────────────────────
_FUNCTION_KEYS = {0x3A + index: f"f{index + 1}" for index in range(12)}
#: F13–F24 存在于部分键盘与 macOS。不映射它们等于让这些键永远统计为 0。
_EXTRA_FUNCTION_KEYS = {0x68 + index: f"f{index + 13}" for index in range(12)}

# ── 小键盘 ────────────────────────────────────────────────────────────────
_KEYPAD_DIGITS = {0x59 + index: f"numpad_{index + 1}" for index in range(9)}

KEY_ID_BY_HID: dict[int, str] = {
    **_LETTERS,
    **_DIGITS,
    0x27: "digit0",
    0x28: "enter",
    0x29: "esc",
    0x2A: "backspace",
    0x2B: "tab",
    0x2C: "space",
    0x2D: "minus",
    0x2E: "equal",
    0x2F: "bracket_left",
    0x30: "bracket_right",
    0x31: "backslash",
    # 0x32 是 HID 的「Non-US # and ~」。Windows 对 ISO 键盘上的这个键报的扫描码
    # 仍是 0x2B（→ 0x31），因此本条在 Windows 上不可达；映射到同一个 key_id 是为了
    # 让日后由固件直接给出 HID 的路径与扫描码路径落到同一个格子，而不是凭空多出
    # 一个只有部分环境才会出现的键。
    0x32: "backslash",
    0x33: "semicolon",
    0x34: "quote",
    0x35: "grave",
    0x36: "comma",
    0x37: "period",
    0x38: "slash",
    0x39: "caps_lock",
    **_FUNCTION_KEYS,
    0x46: "print_screen",
    0x47: "scroll_lock",
    0x48: "pause",
    0x49: "insert",
    0x4A: "home",
    0x4B: "page_up",
    0x4C: "delete",
    0x4D: "end",
    0x4E: "page_down",
    0x4F: "arrow_right",
    0x50: "arrow_left",
    0x51: "arrow_down",
    0x52: "arrow_up",
    0x53: "num_lock",
    0x54: "numpad_divide",
    0x55: "numpad_multiply",
    0x56: "numpad_subtract",
    0x57: "numpad_add",
    0x58: "numpad_enter",
    **_KEYPAD_DIGITS,
    0x62: "numpad_0",
    0x63: "numpad_decimal",
    #: ISO 105 键键盘的第 102 键（左 Shift 右侧）。ANSI 键盘上不存在。
    0x64: "iso_backslash",
    0x65: "menu",
    0x67: "numpad_equal",
    **_EXTRA_FUNCTION_KEYS,
    0xE0: "control_left",
    0xE1: "shift_left",
    0xE2: "alt_left",
    0xE3: "win_left",
    0xE4: "control_right",
    0xE5: "shift_right",
    0xE6: "alt_right",
    0xE7: "win_right",
}

#: 反向索引。两个 usage 指向同一个 ``key_id``（见 0x32 的注释）时保留先出现的那个，
#: 因为它才是各平台实际会报的那一个。
HID_BY_KEY_ID: dict[str, int] = {}
for _usage, _key_id in KEY_ID_BY_HID.items():
    HID_BY_KEY_ID.setdefault(_key_id, _usage)
del _usage, _key_id


def key_id_for_hid(usage: int | None) -> str | None:
    """HID usage → ``key_id``；未收录时返回 ``None``（调用方须计入未映射计数）。"""
    if usage is None:
        return None
    return KEY_ID_BY_HID.get(usage)


def hid_for_key_id(key_id: str) -> int | None:
    return HID_BY_KEY_ID.get(key_id)


__all__ = ["HID_BY_KEY_ID", "KEY_ID_BY_HID", "hid_for_key_id", "key_id_for_hid"]
