"""键名映射（11 文档 §3.1，"最高价值"的一组）。

一百多个键位 × 多条输入路径，全是纯查表逻辑，错了完全无声——用户只会看到某个键
永远是 0，而且没有任何报错。因此这一组测试盯的不是"某个键映射对不对"，而是三条
**结构性**约束：

1. 每个 ``key_id`` 都至少能被某个平台的原生码到达（否则它永远是 0）。
2. 每张原生表只映射到已定义的 ``key_id``（否则会造出没有布局渲染的幽灵键）。
3. ``key_id`` 唯一（标签可以重复，格子不能）。

第 1 条对**所有平台的表求并集**：``key_id`` 是标准，各平台原生码是输入
（04 文档 §3.2）。首期只有 Windows 一张表，M8/M9 加表时这条会自动开始检查
"新平台漏了哪些键"，不需要改测试。
"""

from __future__ import annotations

import pytest

from omnisight.adapters import hid
from omnisight.adapters.generic import pynput_keys
from omnisight.adapters.windows import keymap_native as windows_native
from omnisight.capture.keymap import KEY_BY_ID, KEY_IDS, KEYS, is_known, label_for


def _windows_key_ids() -> set[str]:
    """Windows 表是 ``(scan, E0) → HID``，因此要多走一跳才拿到 ``key_id``。"""
    usages = {
        *windows_native.SCAN_TO_HID.values(),
        *windows_native.EXTENDED_SCAN_TO_HID.values(),
        *windows_native.VK_FALLBACK_TO_HID.values(),
    }
    return {key_id for key_id in map(hid.key_id_for_hid, usages) if key_id}


def _generic_key_ids() -> set[str]:
    """兜底后端直接给 ``key_id``，没有 HID 这一跳（拿不到物理位置码）。"""
    return {
        *pynput_keys.NAME_TO_KEY_ID.values(),
        *pynput_keys.CHAR_TO_KEY_ID.values(),
        *pynput_keys.NUMPAD_VK.values(),
    }


#: 各平台的"能到达哪些 key_id"。M8/M9 在这里加一行即可被全部结构性测试覆盖。
NATIVE_TABLES: dict[str, set[str]] = {
    "windows": _windows_key_ids(),
    "generic": _generic_key_ids(),
}

#: 兜底后端**结构性**拿不到的键，理由各不相同，但都不是 bug：
#:
#: * ``numpad_enter``：pynput 报的是 ``Key.enter``，与主键盘回车无法区分。
#: * ``iso_backslash``：ISO 105 键盘第 102 键，pynput 只给字符，与 ``backslash`` 撞。
#: * ``numpad_equal``：仅见于部分苹果/日系小键盘，pynput 无对应名称。
#:
#: 固定住这个集合，是为了让"兜底后端又少认了一个键"变成一次失败而不是一次静默退化。
KNOWN_GENERIC_GAPS = frozenset({"numpad_enter", "iso_backslash", "numpad_equal"})


def test_every_key_definition_is_reachable_from_some_native_code():
    """任何 key_id 都不许无法到达：无法到达的键会永远停在 0，且不会报错。"""
    reachable: set[str] = set()
    for table in NATIVE_TABLES.values():
        reachable |= table
    missing = KEY_IDS - reachable
    assert not missing, f"这些键永远不会被记录：{sorted(missing)}"


@pytest.mark.parametrize("platform_id", sorted(NATIVE_TABLES))
def test_native_table_maps_only_to_known_key_ids(platform_id: str):
    """原生表里的一个拼写错误会造出没有任何布局渲染的幽灵 key_id。"""
    unknown = NATIVE_TABLES[platform_id] - KEY_IDS
    assert not unknown, f"{platform_id} 映射到了未定义的 key_id：{sorted(unknown)}"


def test_key_ids_are_unique():
    """标签**故意**重复（左右 Shift 同名、小键盘数字与主键区同名），id 不许重复。"""
    ids = [key.id for key in KEYS]
    duplicates = sorted({key_id for key_id in ids if ids.count(key_id) > 1})
    assert not duplicates, f"重复的键 id：{duplicates}"
    assert len(KEY_BY_ID) == len(KEYS), "KEY_BY_ID 的条数必须与 KEYS 一致"


def test_left_and_right_modifiers_are_separate_slots():
    """热力图要能分辨左右修饰键——这是 Raw Input 相对兜底后端的核心优势。"""
    for left, right in (
        ("shift_left", "shift_right"),
        ("control_left", "control_right"),
        ("alt_left", "alt_right"),
        ("win_left", "win_right"),
    ):
        assert left in KEY_IDS and right in KEY_IDS
        assert KEY_BY_ID[left].label == KEY_BY_ID[right].label, "左右同名是刻意的"
        assert KEY_BY_ID[left].hid_usage != KEY_BY_ID[right].hid_usage


def test_numpad_digits_are_separate_from_main_row_digits():
    for index in range(10):
        main = KEY_BY_ID[f"digit{index}"]
        pad = KEY_BY_ID[f"numpad_{index}"]
        assert main.id != pad.id
        assert main.hid_usage != pad.hid_usage


def test_every_key_has_a_hid_usage():
    """没有 HID usage 的键说明没有任何平台能报出它——应视为定义错误而非可选项。"""
    orphans = [key.id for key in KEYS if key.hid_usage is None]
    assert not orphans, f"这些键缺少 HID usage：{orphans}"


def test_hid_mapping_round_trips():
    for key in KEYS:
        assert hid.key_id_for_hid(key.hid_usage) == key.id


def test_hid_usages_are_unique_per_key():
    usages = [key.hid_usage for key in KEYS]
    assert len(usages) == len(set(usages)), "两个键共用一个 HID usage 会互相覆盖"


def test_generic_backend_gaps_are_exactly_the_documented_ones():
    """兜底后端的缺口是已知且有理由的；多一个就是退化，少一个说明可以更新文档。"""
    assert KEY_IDS - NATIVE_TABLES["generic"] == KNOWN_GENERIC_GAPS


def test_windows_backend_has_no_gaps():
    """一级平台不允许有缺口——Raw Input 拿得到全部物理位置。"""
    assert KEY_IDS - NATIVE_TABLES["windows"] == set()


def test_unknown_key_id_is_returned_as_is_not_crashing():
    """孤儿键（旧数据里的 key_id 在当前布局下不存在）必须能显示，不能抛异常。"""
    assert label_for("some_key_from_the_future") == "some_key_from_the_future"
    assert is_known("some_key_from_the_future") is False
    assert is_known("key_a") is True


def test_label_is_never_empty():
    for key in KEYS:
        assert label_for(key.id).strip(), f"{key.id} 的标签是空的"
