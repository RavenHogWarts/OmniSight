"""应用自动分类（05 文档 §3、07 文档 §10）。

**规则只有一份，在后端。** TimeLens 的分类规则在 Python 与 JS 里各有一份实现，两者已经
分叉（同一个进程在列表页与饼图上属于不同类别）。合并时的决定是彻底删掉前端副本，因此这里
除了规则本身，还要断言"前端目录里没有第二份规则"——否则副本会在某次"顺手加个映射"里回来。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from omnisight.services import categories

STATIC = Path(categories.__file__).resolve().parents[1] / "presentation" / "static"


@pytest.mark.parametrize(
    ("process", "display", "expected"),
    [
        ("Code.exe", "Visual Studio Code", "development"),
        ("code.exe", "", "development"),  # 只有进程名也要认得
        ("pycharm64.exe", "PyCharm", "development"),
        ("WindowsTerminal.exe", "", "development"),
        ("chrome.exe", "Google Chrome", "productivity"),
        ("EXCEL.EXE", "Microsoft Excel", "productivity"),  # 大小写无关
        ("WeChat.exe", "微信", "communication"),
        ("outlook.exe", "Outlook", "communication"),  # Office 家族但属于沟通
        ("steam.exe", "Steam", "entertainment"),
        ("explorer.exe", "文件资源管理器", "system"),
        ("", "", "uncategorized"),
    ],
)
def test_exact_process_rules(process: str, display: str, expected: str):
    assert categories.categorize(display, process) == expected


def test_exact_match_wins_over_keywords():
    """``notepad`` 精确命中"效率"；靠关键词它会撞上 ``system`` 的 ``windows``。"""
    assert categories.categorize("Windows 记事本", "notepad.exe") == "productivity"


def test_keyword_order_keeps_system_components_out_of_entertainment():
    """``game`` 关键词排在最后：否则 ``GameBar`` 这类系统组件会被算成娱乐。"""
    assert categories.categorize("Xbox Game Bar", "GameBar.exe") == "entertainment"
    assert categories.categorize("Windows 音频服务", "AudioService.exe") == "system"


def test_substring_matching_does_not_leak_across_names():
    """``unicode.exe`` 曾被"含 code"的子串规则算成开发。精确匹配 + 有序关键词修掉了它。"""
    assert categories.categorize("Unicode 工具", "unicode.exe") == "uncategorized"


def test_unknown_apps_get_a_named_category_not_an_empty_string():
    """空字符串会让分类饼图多出一块没有图例的扇形（06 文档 §3.1）。"""
    assert categories.categorize("某个自研工具", "acme-tool.exe") == categories.UNCATEGORIZED
    assert categories.UNCATEGORIZED in categories.CATEGORY_NAMES


def test_catalog_covers_every_category_id():
    catalog = categories.catalog()
    assert [item["id"] for item in catalog] == list(categories.CATEGORY_IDS)
    assert all(item["name"] for item in catalog)


def test_name_of_an_unknown_category_is_returned_verbatim():
    """用户可能在旧版里设过一个已删掉的类别；界面照样要画出来，而不是 500。"""
    assert categories.name_of("legacy-thing") == "legacy-thing"


def test_no_second_copy_of_the_rules_ships_in_the_frontend():
    """规则只有一份。前端出现任何一条进程名映射，就意味着两份实现开始分叉。"""
    if not STATIC.exists():  # M3 之前静态目录可能还很空
        pytest.skip("前端静态目录尚未建立")
    samples = ("pycharm64", "steamwebhelper", "startmenuexperiencehost")
    offenders = [
        path.relative_to(STATIC).as_posix()
        for path in STATIC.rglob("*.js")
        if any(sample in path.read_text(encoding="utf-8", errors="ignore") for sample in samples)
    ]
    assert not offenders, f"前端又出现了一份分类规则副本：{offenders}"
