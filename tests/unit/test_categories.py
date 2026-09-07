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


# ── bundle id 口径（19 文档 A3）─────────────────────────────────────────
def test_bundle_ids_categorize_by_their_own_table():
    """macOS 的身份是 bundle id：查 bundle 表，不查进程名表。"""
    assert (
        categories.categorize("Google Chrome", "com.google.Chrome", identity_kind="bundle")
        == "productivity"
    )
    assert (
        categories.categorize("微信", "com.tencent.xinWeChat", identity_kind="bundle")
        == "communication"
    )


def test_microsoft_bundle_ids_are_not_system_anymore():
    """``"microsoft."`` 关键词曾把 ``com.microsoft.VSCode`` 静默判成"系统"——
    一个开发工具被归类成系统组件，且分类错误在 UI 上完全静默（19 文档 A3）。"""
    assert (
        categories.categorize("Visual Studio Code", "com.microsoft.VSCode", identity_kind="bundle")
        == "development"
    )
    # 关键词表里确实不再有它。
    assert "microsoft." not in categories.KEYWORD_RULES[-1][1]


def test_bundle_ids_are_not_suffix_stripped():
    """``.app`` 是 bundle id 的一部分：剥掉后缀等于查一张错误的表。"""
    guess = categories.categorize("示例", "com.example.app", identity_kind="bundle")
    assert guess == "uncategorized"


def test_every_bundle_entry_maps_to_a_known_category():
    """首批 bundle 表的 49 条全部落在合法类别上——拼错类别 id 是静默的饼图缺角。"""
    assert len(categories.EXACT_BUNDLES) >= 40
    for bundle_id, category in categories.EXACT_BUNDLES.items():
        assert categories.is_known(category), bundle_id
        assert bundle_id == bundle_id.casefold(), bundle_id  # 键必须已是 casefold


def test_process_kind_is_the_default_and_unchanged():
    """默认口径是 process：既有调用点一个字不改，Windows 行为不变。"""
    assert categories.categorize("PyCharm", "pycharm64.exe") == "development"
    explicit = categories.categorize("PyCharm", "pycharm64.exe", identity_kind="process")
    assert explicit == "development"


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
