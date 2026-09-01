"""Windows 原生码 → ``key_id``（11 文档 §3.1 的参数化组）。

11 文档写的调用形态是 ``normalize_raw_key`` + ``key_metadata_from_codes`` 两步。实现
合成了一个 :func:`~omnisight.adapters.windows.keymap_native.resolve`：以
``(扫描码, E0)`` 为枢轴之后，``normalize_raw_key`` 里那四处特殊处理全部变成普通表项，
留一个只做归一化的函数已无意义（偏离已记入 PROGRESS）。这里的断言逐条对应原文。
"""

from __future__ import annotations

import pytest

from omnisight.adapters.hid import key_id_for_hid
from omnisight.adapters.windows import keymap_native as native
from omnisight.capture.keymap import KEY_IDS

E0 = native.RI_KEY_E0
E1 = native.RI_KEY_E1
BREAK = native.RI_KEY_BREAK


@pytest.mark.parametrize(
    ("vk", "scan", "flags", "expected"),
    [
        (0x10, 0x2A, 0x00, "shift_left"),  # VK_SHIFT + 左扫描码
        (0x10, 0x36, 0x00, "shift_right"),  # VK_SHIFT + 右扫描码
        (0x11, 0x1D, 0x00, "control_left"),
        (0x11, 0x1D, E0, "control_right"),  # E0 扩展位
        (0x12, 0x38, 0x00, "alt_left"),
        (0x12, 0x38, E0, "alt_right"),
        (0x0D, 0x1C, 0x00, "enter"),
        (0x0D, 0x1C, E0, "numpad_enter"),  # 小键盘回车
        (0x60, 0x52, 0x00, "numpad_0"),
        (0x2D, 0x52, E0, "insert"),  # NumLock 关闭时的 Ins 与 Num0 同扫描码
        (0x64, 0x4B, 0x00, "numpad_4"),
        (0x25, 0x4B, E0, "arrow_left"),
        (0x41, 0x1E, 0x00, "key_a"),
        (0x56, 0x2F, 0x00, "key_v"),
        (0xE2, 0x56, 0x00, "iso_backslash"),  # ISO 105 键盘的第 102 键
        (0x5D, 0x5D, E0, "menu"),
    ],
)
def test_resolve_maps_native_codes_to_key_ids(vk: int, scan: int, flags: int, expected: str):
    key_id, usage, is_down = native.resolve(vk, scan, flags)
    assert key_id == expected
    assert is_down is True
    assert key_id_for_hid(usage) == expected


def test_break_flag_marks_a_release():
    """按下与抬起走同一张表，方向只由 ``RI_KEY_BREAK`` 决定。"""
    down = native.resolve(0x41, 0x1E, 0x00)
    up = native.resolve(0x41, 0x1E, BREAK)
    assert down[0] == up[0] == "key_a"
    assert down[2] is True
    assert up[2] is False


def test_extended_break_is_still_a_release():
    """扩展键的抬起是 ``E0 | BREAK``；漏掉这一位会把抬起当成又一次按下。"""
    key_id, _usage, is_down = native.resolve(0x11, 0x1D, E0 | BREAK)
    assert key_id == "control_right"
    assert is_down is False


def test_pause_prefix_segment_is_not_a_key():
    """Pause 的报文是 ``E1 1D`` + ``45`` 两段。

    第一段的 MakeCode 恰好是左 Ctrl 的 ``0x1D``——不丢弃的话，每按一次 Pause 都会
    多记一次左 Ctrl，而这个错误在统计上完全看不出来。
    """
    key_id, usage, _ = native.resolve(0x11, 0x1D, E1)
    assert key_id is None
    assert usage is None


def test_pause_and_numlock_share_a_scancode_and_are_split_by_vk():
    """``0x45`` 同时是 Pause 第二段与 NumLock，是全表唯一必须靠 VK 消歧的地方。"""
    assert native.resolve(native.VK_PAUSE, 0x45, 0x00)[0] == "pause"
    assert native.resolve(native.VK_NUMLOCK, 0x45, 0x00)[0] == "num_lock"


def test_unknown_native_code_returns_none_rather_than_guessing():
    """猜一个 key_id 会把按键计到别的格子上，比留空更糟——调用方负责计入未映射数。"""
    key_id, usage, is_down = native.resolve(0xAF, 0x71, E0)
    assert key_id is None
    assert usage is None
    assert is_down is True


def test_vk_fallback_only_covers_position_unambiguous_keys():
    """VK 兜底表不许收录左右成对的键：VK 分不出左右，一旦落进兜底就会归错格子。"""
    ambiguous = {0x10, 0x11, 0x12}  # VK_SHIFT / VK_CONTROL / VK_MENU
    assert not ambiguous & set(native.VK_FALLBACK_TO_HID)


@pytest.mark.parametrize(
    "table_name", ["SCAN_TO_HID", "EXTENDED_SCAN_TO_HID", "VK_FALLBACK_TO_HID"]
)
def test_tables_contain_only_usages_that_map_to_defined_keys(table_name: str):
    table: dict[int, int] = getattr(native, table_name)
    for code, usage in table.items():
        key_id = key_id_for_hid(usage)
        assert key_id in KEY_IDS, f"{table_name}[{code:#04x}] → usage {usage:#04x} 无对应键"


def test_scan_tables_do_not_disagree_with_each_other_by_accident():
    """同一个扫描码在扩展/非扩展下必须是**不同**的键，否则 E0 位就白读了。

    唯一允许相同的是 PrintScreen：``E0 0x37`` 与 Alt+PrtSc 的 ``0x54`` 是同一个键的
    两种报文形态。
    """
    for scan, plain_usage in native.SCAN_TO_HID.items():
        extended_usage = native.EXTENDED_SCAN_TO_HID.get(scan)
        if extended_usage is None:
            continue
        assert plain_usage != extended_usage, f"扫描码 {scan:#04x} 的 E0 位没有意义"
