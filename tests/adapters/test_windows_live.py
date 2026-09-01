"""真正调用 Win32 的那几处（11 文档 §1 的 ``windows_only`` 少数派）。

**这个文件的用例数应当保持极少**——标记数量增长就说明平台依赖正在向上层泄漏。
它们存在的理由很具体：`ctypes` 的函数签名、结构体字段、返回值判断写错时，纯 Python
测试一律通不过发现，只有真的调一次才会暴露。这几行代码此外没有任何覆盖。

同文件里不需要真实 API 的部分（外壳名单、显示名推导）不打标记，三个平台都跑。
"""

from __future__ import annotations

import sys

import pytest

from omnisight.adapters.ports import AppIdentity, ForegroundInfo
from omnisight.adapters.windows.shell_filter import (
    SHELL_KEYS,
    display_name_for,
    is_shell,
)


# ── 纯逻辑：任意平台 ──────────────────────────────────────────────────────
def test_shell_keys_are_all_lowercase():
    """名单要与 ``app_key = casefold(process_name)`` 同口径，否则永远匹配不上。"""
    assert all(key == key.casefold() for key in SHELL_KEYS)


def test_is_shell_is_case_insensitive():
    assert is_shell("Explorer.exe") is True
    assert is_shell("EXPLORER.EXE") is True
    assert is_shell("code.exe") is False


@pytest.mark.parametrize(
    ("process_name", "expected"),
    [
        ("Code.exe", "Code"),
        ("chrome.EXE", "chrome"),
        ("weird", "weird"),
        (".exe", ".exe"),  # 去掉后缀会变空串，此时保留原值
        ("  Notepad.exe  ", "Notepad"),
    ],
)
def test_display_name_strips_the_exe_suffix(process_name: str, expected: str):
    assert display_name_for(process_name) == expected


# ── 真实 Win32：只验"调得通且形状对" ───────────────────────────────────────
@pytest.mark.windows_only
def test_foreground_source_returns_a_well_formed_identity_or_none():
    """``current()` 永不抛异常——探测失败必须表现为 ``None``，否则轮询线程会死掉。"""
    from omnisight.adapters.windows.foreground import WindowsForegroundSource

    info = WindowsForegroundSource(titles_enabled=False).current()
    if info is None:
        return  # 测试进程可能没有前台窗口（CI 无桌面会话），这是合法结果
    assert isinstance(info, ForegroundInfo)
    assert isinstance(info.identity, AppIdentity)
    assert info.identity.app_key == info.identity.app_key.casefold()
    assert info.identity.identity_kind == "process"
    assert info.identity.process_name
    assert info.window_title == "", "titles_enabled=False 时标题必须是空串"


@pytest.mark.windows_only
def test_foreground_source_can_return_a_title_when_explicitly_enabled():
    from omnisight.adapters.windows.foreground import WindowsForegroundSource

    info = WindowsForegroundSource(titles_enabled=True).current()
    if info is None:
        return
    assert isinstance(info.window_title, str)


@pytest.mark.windows_only
def test_idle_source_reports_a_sane_number():
    """``GetLastInputInfo`` + ``GetTickCount`` 的回绕处理写错会给出巨大的负数或秒数。"""
    from omnisight.adapters.windows.idle import WindowsIdleSource

    seconds = WindowsIdleSource().idle_seconds()
    assert 0.0 <= seconds < 86_400.0, f"空闲秒数不合理：{seconds}"


@pytest.mark.windows_only
def test_window_enumeration_returns_distinct_lowercased_keys():
    """``EnumWindows`` 的回调签名写错会静默返回空列表，而"应用选择器是空的"很难归因。"""
    from omnisight.adapters.windows.window_enum import list_visible_apps

    apps = list_visible_apps()
    keys = [app.app_key for app in apps]
    assert len(keys) == len(set(keys)), "同一个应用不该出现两次"
    assert all(key == key.casefold() for key in keys)
    assert all(not is_shell(key) for key in keys), "系统外壳不该出现在应用列表里"


@pytest.mark.windows_only
def test_raw_input_backend_can_actually_register():
    """M1 三个核心假设的第一条，能自动验证的那一半：注册本身成功、能停干净。

    "收得全不全"只能真人在全屏独占游戏里验（见 PROGRESS 的待人工验收）；这里验的是
    ``RegisterRawInputDevices`` + 顶层消息窗口这条路在本机上走得通。
    """
    from omnisight.adapters.ports import CaptureUnavailable
    from omnisight.adapters.windows.keyboard import RawInputKeyboardSource

    source = RawInputKeyboardSource()
    try:
        source.start(lambda event: None)
    except CaptureUnavailable as exc:
        pytest.skip(f"本机无法注册 Raw Input（会话 0 / 反作弊）：{exc}")
    try:
        assert source.running is True
        assert source.backend_name == "raw_input"
        assert source.needs_main_loop is False
    finally:
        source.stop()
    assert source.running is False


def test_windows_only_marker_count_stays_small():
    """标记数量本身就是一个指标：它增长意味着平台依赖在向上层泄漏（11 文档 §1）。"""
    source = __import__("pathlib").Path(__file__).read_text(encoding="utf-8")
    count = source.count("@pytest.mark.windows_only")
    assert count <= 8, f"windows_only 用例已有 {count} 个，检查是否有依赖泄漏"
    if sys.platform != "win32":
        pytest.skip("其余用例在非 Windows 上已被 conftest 跳过")
