"""键盘布局族（05 文档 §4、02 文档 §2）。

**布局是数据，不是 DOM。** 前端不内置任何键位坐标，全部来自 ``/keyboard/layout``。因此
这里要固定的是三件事：id 集合不许超出 ``keymap``（12 文档 M2 的 CI 断言）、每行宽度一致
（否则前端渲染出锯齿）、以及两个族的键数确实是 104 与 105。
"""

from __future__ import annotations

import pytest

from omnisight.capture import keymap, layouts


@pytest.mark.parametrize("family", layouts.IMPLEMENTED_FAMILIES)
def test_layout_key_ids_are_a_subset_of_the_keymap(family: str):
    """布局里出现一个 ``keymap`` 没有的 id，那个格子就永远收不到按键——静默错。

    这是 12 文档 M2 点名要在 CI 里断言的那一条。
    """
    unknown = layouts.FAMILIES[family].key_ids - keymap.KEY_IDS
    assert not unknown, f"{family} 引用了未定义的 key_id：{sorted(unknown)}"


@pytest.mark.parametrize("family", layouts.IMPLEMENTED_FAMILIES)
def test_every_row_has_the_same_total_width(family: str):
    """行宽不齐前端只能自己补空位——而"补多少"是后端已经知道的事。"""
    layout = layouts.FAMILIES[family]
    widths = {
        sum(slot.w for slot in row)
        for row in layout.rows
    }
    assert widths == {layout.max_units}, f"{family} 各行宽度不一致：{sorted(widths)}"


@pytest.mark.parametrize(("family", "count"), [("ansi104", 104), ("iso105", 105)])
def test_families_have_the_key_count_their_name_claims(family: str, count: int):
    """名字里写着 104 就必须是 104 个键——差一个说明漏了或多了一格。"""
    layout = layouts.FAMILIES[family]
    real = [slot for row in layout.rows for slot in row if slot.id != "gap"]
    assert len(real) == count


@pytest.mark.parametrize("family", layouts.IMPLEMENTED_FAMILIES)
def test_no_duplicate_key_ids_within_a_family(family: str):
    layout = layouts.FAMILIES[family]
    ids = [slot.id for row in layout.rows for slot in row if slot.id != "gap"]
    assert len(ids) == len(set(ids))


def test_iso_enter_is_the_only_special_shape():
    """ISO 回车是 L 形，这一个例外靠 ``shape`` 字段表达而不是让前端按族猜。"""
    shapes = {
        slot.shape
        for family in layouts.IMPLEMENTED_FAMILIES
        for row in layouts.FAMILIES[family].rows
        for slot in row
        if slot.shape
    }
    assert shapes == {"iso_enter"}


def test_iso_has_the_extra_key_ansi_lacks():
    """105 − 104 = 1：ISO 多出的那个键（回车左下方）必须真的存在于 keymap。"""
    extra = layouts.FAMILIES["iso105"].key_ids - layouts.FAMILIES["ansi104"].key_ids
    assert len(extra) == 1
    assert extra <= keymap.KEY_IDS


@pytest.mark.parametrize(
    ("platform_id", "family"),
    [("windows", "ansi104"), ("macos", "ansi104"), ("linux", "ansi104"), ("unknown", "ansi104")],
)
def test_default_family_is_defined_for_every_platform(platform_id: str, family: str):
    """未知平台也要有默认值：没有布局等于键盘页整页空白。"""
    assert layouts.default_family(platform_id) == family


def test_all_layout_key_ids_is_the_union_of_the_families():
    union = set()
    for family in layouts.IMPLEMENTED_FAMILIES:
        union |= layouts.FAMILIES[family].key_ids
    assert layouts.all_layout_key_ids() == union


def test_keys_outside_every_layout_still_have_labels():
    """媒体键、厂商键不在任何布局里，但会被记到 ``orphan_keys``——它们也要能显示名字。"""
    orphans = keymap.KEY_IDS - layouts.all_layout_key_ids()
    assert orphans, "keymap 应当比布局更宽（否则热力图的 orphan_keys 分支是死代码）"
    assert all(keymap.label_for(key_id) for key_id in orphans)
