"""托盘菜单的构成（10 文档 §5、§5.2）。

托盘是全项目最难自动化的一层，而它恰好承载三个"点错了就会出事"的入口：暂停记录、
以管理员身份重启、退出。这里用一个假的 pystray 顶掉真库，于是菜单的**结构**——有哪些
项、什么顺序、什么时候能点、点下去调谁——可以在三个平台上被断言，不需要桌面会话。

**刻意断言文字本身。** 菜单项的措辞是用户判断"这一项会做什么"的唯一依据（尤其是提权
那一项，点下去会重启整个程序），改动它应当是一次自觉的决定，而不是某次重构的副作用。
"""

from __future__ import annotations

import sys
import types

import pytest

pytest.importorskip("PIL", reason="托盘用 Pillow 渲染图标")

from omnisight.tray.tray import ELEVATION_LABELS, TrayIcon


class FakeMenuItem:
    """记下 pystray 会收到的参数。``text`` / ``enabled`` 等都允许是可调用对象。"""

    def __init__(self, text, action=None, **options) -> None:
        self.text = text
        self.action = action
        self.options = options

    @property
    def label(self) -> str:
        return self.text(self) if callable(self.text) else str(self.text)

    def flag(self, name: str) -> bool:
        value = self.options.get(name, True)
        return bool(value(self)) if callable(value) else bool(value)

    def click(self, icon) -> None:
        self.action(icon, self)


class FakeMenu:
    SEPARATOR = object()

    def __init__(self, *items) -> None:
        self.items = list(items)


class FakeIcon:
    def __init__(self, name, icon=None, title="", menu=None) -> None:
        self.name = name
        self.icon = icon
        self.title = title
        self.menu = menu
        self.updates = 0

    def update_menu(self) -> None:
        self.updates += 1


@pytest.fixture(autouse=True)
def fake_pystray(monkeypatch) -> types.SimpleNamespace:
    """``_build_icon`` 里是 ``import pystray``，因此顶掉 ``sys.modules`` 就够了。"""
    module = types.SimpleNamespace(Menu=FakeMenu, MenuItem=FakeMenuItem, Icon=FakeIcon)
    monkeypatch.setitem(sys.modules, "pystray", module)
    return module


def build(**overrides) -> TrayIcon:
    actions = {
        "dashboard_url": lambda: "http://127.0.0.1:6100/?token=t",
        "open_dashboard": lambda: None,
        "on_quit": lambda: None,
    }
    actions.update(overrides)
    return TrayIcon(**actions)


def menu_of(tray: TrayIcon) -> tuple[FakeIcon, list[FakeMenuItem]]:
    icon = tray._build_icon()
    return icon, [item for item in icon.menu.items if item is not FakeMenu.SEPARATOR]


def admin_item(entries: list[FakeMenuItem]) -> FakeMenuItem:
    found = [item for item in entries if item.label in set(ELEVATION_LABELS.values())]
    assert len(found) == 1, f"管理员模式那一项应当恰好有一个：{[i.label for i in entries]}"
    return found[0]


#: 10 文档 §5 与 18 文档 批 4 的菜单清单。**顺序也是内容**：「打开设置」紧跟「打开
#: OmniSight」（两条都是"去页面"），暂停/重启/提权是一组（都在回答"此刻记录得全不全"），
#: 两个目录入口与退出是最后一组。
EXPECTED_ORDER = [
    "打开 OmniSight",
    "打开设置",
    "暂停记录",
    "重新启动",
    ELEVATION_LABELS["available"],
    "打开数据目录",
    "打开日志目录",
    "退出",
]


def test_the_menu_lists_the_documented_items_in_that_order():
    tray = build(elevation_state=lambda: "available", on_elevate=lambda: None)
    _icon, entries = menu_of(tray)
    assert [item.label for item in entries] == EXPECTED_ORDER


def test_the_menu_no_longer_carries_settings_that_belong_on_a_page():
    """18 文档 批 4：开机自启与关于说明搬进页面了。

    前者的真源是操作系统，而 Windows 上有两条互斥机制——一个勾选框只能显示并集，说不出
    是哪一条开着（10 文档 §5.3 早已把提权那一条放在设置页）。后者现在是 `/about` 那一页。
    托盘留下的是**进程级动作**与两个目录入口：页面打不开时它们是唯一的一键路径。
    """
    tray = build(elevation_state=lambda: "available", on_elevate=lambda: None)
    _icon, entries = menu_of(tray)
    labels = [item.label for item in entries]
    assert "开机自启" not in labels
    assert "关于与隐私说明" not in labels


def test_the_settings_item_goes_through_the_composition_root():
    """怎么打开由装配层决定（管理员模式下要降权，且地址要带令牌）。"""
    calls: list[str] = []
    tray = build(open_settings=lambda: calls.append("settings"))
    icon, entries = menu_of(tray)
    next(item for item in entries if item.label == "打开设置").click(icon)
    assert calls == ["settings"]


def test_the_restart_item_is_not_a_checkbox_and_calls_the_composition_root():
    """重启不是一个状态：一个勾选框会让人以为"取消勾选"能回到重启前（提权那一项同理）。"""
    calls: list[str] = []
    tray = build(on_restart=lambda: calls.append("restart"))
    icon, entries = menu_of(tray)
    item = next(entry for entry in entries if entry.label == "重新启动")
    assert "checked" not in item.options
    item.click(icon)
    assert calls == ["restart"]


def test_a_failing_restart_does_not_escape_into_pystray():
    """回调抛异常时 pystray 的菜单线程会整条死掉，托盘从此不响应右键。"""

    def boom() -> None:
        raise RuntimeError("起不来")

    tray = build(on_restart=boom)
    icon, entries = menu_of(tray)
    next(item for item in entries if item.label == "重新启动").click(icon)


@pytest.mark.parametrize(
    ("state", "clickable"),
    [("available", True), ("elevated", False), ("unavailable", False)],
)
def test_the_admin_item_can_only_be_clicked_when_elevation_is_possible(state, clickable):
    """已经是管理员就无事可做；标准用户账户点下去会提权成**另一个账户**，数据目录随之
    改变——那不是用户要的东西，所以入口是灰的，且文字里写明原因。
    """
    tray = build(elevation_state=lambda: state, on_elevate=lambda: None)
    _icon, entries = menu_of(tray)
    item = admin_item(entries)
    assert item.label == ELEVATION_LABELS[state]
    assert item.flag("enabled") is clickable
    assert item.flag("visible") is True


def test_the_admin_item_is_not_a_checkbox():
    """提权只能靠重启成一个新进程，勾掉它不会回到普通权限——勾不掉的勾选框是在说谎。"""
    tray = build(elevation_state=lambda: "elevated", on_elevate=lambda: None)
    _icon, entries = menu_of(tray)
    assert "checked" not in admin_item(entries).options


def test_the_admin_item_is_hidden_where_the_platform_has_no_elevation_port():
    """macOS / Linux 还没有实现这个端口。永远灰着的菜单项只会带来"为什么点不了"。"""
    tray = build()
    _icon, entries = menu_of(tray)
    assert admin_item(entries).flag("visible") is False


def test_clicking_it_asks_the_composition_root_to_relaunch():
    calls: list[str] = []
    tray = build(elevation_state=lambda: "available", on_elevate=lambda: calls.append("relaunch"))
    icon, entries = menu_of(tray)
    admin_item(entries).click(icon)
    assert calls == ["relaunch"]


def test_a_failing_relaunch_does_not_escape_into_pystray():
    """回调抛异常会顺着消息循环炸掉托盘线程，那时用户只看到图标凭空消失。"""

    def boom() -> None:
        raise RuntimeError("ShellExecuteExW 失败")

    tray = build(elevation_state=lambda: "available", on_elevate=boom)
    icon, entries = menu_of(tray)
    admin_item(entries).click(icon)


@pytest.mark.parametrize("state", ["root", ""])
def test_an_unknown_state_string_is_treated_as_the_least_privileged_one(state):
    tray = build(elevation_state=lambda: state, on_elevate=lambda: None)
    _icon, entries = menu_of(tray)
    assert admin_item(entries).label == ELEVATION_LABELS["unavailable"]


def test_an_unreadable_state_falls_back_instead_of_breaking_the_menu():
    def boom() -> str:
        raise OSError("令牌查不到")

    tray = build(elevation_state=boom, on_elevate=lambda: None)
    _icon, entries = menu_of(tray)
    item = admin_item(entries)
    assert item.label == ELEVATION_LABELS["unavailable"]
    assert item.flag("enabled") is False


def test_the_tooltip_stays_plain_in_the_normal_case():
    icon, _entries = menu_of(build())
    assert icon.title == "OmniSight"


def test_the_tooltip_still_says_only_paused_when_that_is_all_there_is():
    icon, _entries = menu_of(build(paused_state=lambda: True))
    assert icon.title == "OmniSight（记录已暂停）"


def test_the_tooltip_shows_admin_mode_because_it_is_the_only_always_visible_place():
    """一个正以管理员权限运行的键盘记录程序，应当随时能被看见。"""
    tray = build(
        paused_state=lambda: True,
        elevation_state=lambda: "elevated",
        on_elevate=lambda: None,
    )
    icon, _entries = menu_of(tray)
    assert icon.title == "OmniSight（记录已暂停 · 管理员模式）"


def test_opening_the_dashboard_goes_through_the_composition_root():
    opened: list[str] = []
    tray = build(open_dashboard=lambda: opened.append("dashboard"))
    icon, entries = menu_of(tray)
    entries[0].click(icon)
    assert opened == ["dashboard"]
    assert entries[0].flag("default") is True, "双击图标应当就是这一项"


def test_the_tray_does_not_open_anything_by_itself():
    """"怎么打开"是装配层的决定——管理员模式下必须降权，否则浏览器会继承管理员令牌
    （``lifecycle._open_external``）。托盘里再出现 ``webbrowser`` 就说明这条边界又被
    跨回去了。
    """
    from omnisight.tray import tray as module

    assert not hasattr(module, "webbrowser")
