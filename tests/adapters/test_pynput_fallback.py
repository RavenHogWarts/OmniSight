"""通用兜底后端的解码（11 文档 §8.1 的同一层，不需要装 pynput）。

``key_id_for`` 是纯函数且鸭子类型，因此这里用假按键对象喂它——测试不导入 pynput，
在三个平台上都能跑。这一点不是巧合：兜底后端在 Windows 上也可能被启用（Raw Input
被反作弊拦截时），它的映射错了同样是无声的。

本文件同时把这个后端的**已知损失**固定成断言。它拿不到物理位置码，左右修饰键与
小键盘会合并——这不是 bug，而是 ``key_position_stable = False`` 所描述的那件事。
把它写成测试，是为了让"哪些损失是已知的"有一份机械化的清单，而不是靠记忆。
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from omnisight.adapters.generic.pynput_keys import (
    BACKEND_NAME,
    CHAR_TO_KEY_ID,
    NAME_TO_KEY_ID,
    key_id_for,
)
from omnisight.capture.keymap import KEY_IDS


@dataclass(frozen=True)
class FakeKey:
    """pynput 的 ``Key``/``KeyCode`` 在解码路径上只暴露这三个属性。"""

    name: str | None = None
    char: str | None = None
    vk: int | None = None


def test_backend_name_is_stable():
    """后端名会写进 ``capture_capability``，改名等于让历史数据无法解释。"""
    assert BACKEND_NAME == "pynput"


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        (FakeKey(char="a"), "key_a"),
        (FakeKey(char="A"), "key_a"),
        (FakeKey(char="1"), "digit1"),
        (FakeKey(char="!"), "digit1"),  # Shift+1 落在同一个物理格子
        (FakeKey(char="?"), "slash"),
        (FakeKey(char="\t"), "tab"),
        (FakeKey(char="\r"), "enter"),
        (FakeKey(name="space", char=" "), "space"),
        (FakeKey(name="f5"), "f5"),
        (FakeKey(name="shift_r"), "shift_right"),
        (FakeKey(name="ctrl_l"), "control_left"),
        (FakeKey(name="alt_gr"), "alt_right"),
        (FakeKey(name="cmd"), "win_left"),  # macOS 的 Command 归到 Win 位
        (FakeKey(vk=0x64), "numpad_4"),
        (FakeKey(vk=0x6F), "numpad_divide"),
    ],
)
def test_key_id_for_maps_fake_keys(key: FakeKey, expected: str):
    assert key_id_for(key) == expected


def test_unrecognised_key_returns_none():
    assert key_id_for(FakeKey()) is None
    assert key_id_for(FakeKey(char="😀")) is None
    assert key_id_for(object()) is None


def test_name_wins_over_char():
    """``Key.space`` 同时有 ``name`` 与 ``char``；按名字更可靠（char 可能是本地化的）。"""
    assert key_id_for(FakeKey(name="enter", char="\r")) == "enter"


def test_numpad_vk_is_only_consulted_without_name_and_char():
    """有 ``char`` 时不许查 vk 表——各平台的 vk 编号不同，会在 macOS/Linux 上撞车。"""
    # 0x64 在 Windows 上是小键盘 4，但这次带了字符 "d"，必须按字符走。
    assert key_id_for(FakeKey(char="d", vk=0x64)) == "key_d"


def test_shifted_and_unshifted_symbols_share_one_slot():
    """否则热力图会多出一整排只在按 Shift 时才出现的符号键。"""
    for shifted, unshifted in (("~", "`"), ("_", "-"), ("|", "\\"), (":", ";")):
        assert CHAR_TO_KEY_ID[shifted] == CHAR_TO_KEY_ID[unshifted]


def test_left_right_agnostic_names_collapse_to_left():
    """已知损失：pynput 给不出左右时一律记左键，且必须与 key_position_stable=False 配套。"""
    assert NAME_TO_KEY_ID["shift"] == "shift_left"
    assert NAME_TO_KEY_ID["ctrl"] == "control_left"
    assert NAME_TO_KEY_ID["alt"] == "alt_left"


def test_all_mapped_values_are_defined_keys():
    for table in (NAME_TO_KEY_ID, CHAR_TO_KEY_ID):
        unknown = set(table.values()) - KEY_IDS
        assert not unknown, f"映射到了未定义的 key_id：{sorted(unknown)}"
