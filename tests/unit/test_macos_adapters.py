"""macOS 适配器的可移植测试（19 文档批次 B / 20 文档 B4–B7）。

设计约束换来的直接收益：pyobjc 的导入全部藏在方法体里（适配器模块顶层只有
stdlib 与 ports），因此 **factory 的装配逻辑、plist 生成、名单与降级文案都能在
Windows 开发机上完整测试**——pyobjc 真正被调用的路径留给 macos CI 的 pytest
与真机验收（11 文档 §8.1"解码必须可离线测试"的同一条原则）。
"""

from __future__ import annotations

import plistlib
from dataclasses import replace
from pathlib import Path

from omnisight.adapters import ports
from omnisight.adapters.macos import factory, shell_filter
from omnisight.adapters.macos.autostart import LaunchAgentAutostart, render_plist
from omnisight.adapters.macos.keyboard import EventTapKeyboardSource
from omnisight.adapters.macos.notifier import MacNotifier
from omnisight.adapters.macos.permissions import INPUT_MONITORING_DENIED, preflight
from omnisight.adapters.ports import AdapterOptions

# ── B4 · 外壳名单 ────────────────────────────────────────────────────────


def test_shell_keys_cover_the_macos_chrome_and_are_casefolded():
    """Dock / 聚焦 / 登录窗等七件"系统外壳"命中后不产生会话（19 文档 §2.6）。
    键必须已是小写——比较口径是 ``casefold(bundleIdentifier)``。"""
    assert {
        key.casefold() for key in shell_filter.SHELL_KEYS
    } == shell_filter.SHELL_KEYS
    assert {
        "com.apple.dock",
        "com.apple.spotlight",
        "com.apple.loginwindow",
        "com.apple.controlcenter",
        "com.apple.notificationcenterui",
        "com.apple.windowmanager",
        "com.apple.systemuiserver",
    } <= shell_filter.SHELL_KEYS


# ── B5 · TCC 探测 ────────────────────────────────────────────────────────


def test_preflight_reports_required_and_never_raises():
    """在非 mac 环境上探测失败按"未授权"上报——谎报 granted 的代价是面板空转。"""
    required, granted = preflight()
    assert required == ("input_monitoring",)
    assert isinstance(granted, tuple)
    assert set(granted) <= {"input_monitoring", "accessibility"}


def test_denied_notice_points_at_the_full_settings_path():
    """引导文案必须写全路径——"去设置里看看"不是一个可执行的下一步。"""
    assert INPUT_MONITORING_DENIED.code == "input_monitoring_denied"
    assert INPUT_MONITORING_DENIED.severity == "error"
    assert "系统设置 › 隐私与安全性 › 输入监控" in (INPUT_MONITORING_DENIED.hint or "")
    # 隐私叙事的一致性：必须说清"屏幕时间不受影响"，而不是让人以为全坏了。
    assert "不受影响" in INPUT_MONITORING_DENIED.detail


# ── B6 · event tap 源的形状 ──────────────────────────────────────────────


def test_event_tap_source_declares_main_loop_and_zero_counters():
    source = EventTapKeyboardSource()
    assert source.backend_name == "event_tap"
    assert source.needs_main_loop is True
    assert source.running is False
    assert source.unmapped_events == 0
    assert source.tap_disabled_count == 0


def test_event_tap_source_satisfies_the_keyboard_protocol():
    assert isinstance(EventTapKeyboardSource(), ports.KeyboardSource)


# ── B7 · LaunchAgent 自启 ────────────────────────────────────────────────


def test_rendered_plist_matches_the_launchagent_contract():
    content = plistlib.loads(render_plist("/Applications/OmniSight.app/Contents/MacOS/OmniSight"))
    assert content["Label"] == "com.ravenhogwarts.omnisight"
    assert content["ProgramArguments"] == ["/Applications/OmniSight.app/Contents/MacOS/OmniSight"]
    assert content["RunAtLoad"] is True
    # 崩溃循环重启一个记录键盘的程序比"坏了就坏了"更糟（KeepAlive 关闭是刻意的）。
    assert content["KeepAlive"] is False


def test_autostart_reports_stale_entries_as_disabled(tmp_path: Path, monkeypatch):
    """用户搬走 .app 之后，旧 plist 指向死路径——照实报"未启用"（10 文档 §4）。"""
    from omnisight.adapters.macos import autostart as mod

    target = tmp_path / "com.ravenhogwarts.omnisight.plist"
    monkeypatch.setattr(mod, "plist_path", lambda: target)
    monkeypatch.setattr(mod, "_program", lambda: "/new/path/OmniSight")

    control = LaunchAgentAutostart()
    assert control.is_enabled() is False  # plist 不存在

    control.set_enabled(True)
    assert control.is_enabled() is True

    # 写死旧路径的残留：存在但不指向当前程序 → 未启用。
    target.write_bytes(render_plist("/old/moved/OmniSight"))
    assert control.is_enabled() is False

    control.set_enabled(False)
    assert not target.exists()


# ── B7 · factory 装配 ────────────────────────────────────────────────────


def test_detect_is_honest_about_missing_input_monitoring():
    """授权现状是能力的一部分：未授权 → keyboard=False + input_monitoring_denied。"""
    caps = factory.detect()
    assert caps.platform_id == "macos"
    assert caps.tier == 2
    assert caps.keyboard_backends == ("auto", "event_tap", "pynput", "none")
    codes = {notice.code for notice in caps.degraded}
    if caps.keyboard:
        assert "input_monitoring_denied" not in codes  # 真机上授权过的形态
    else:
        assert "input_monitoring_denied" in codes
        assert caps.keyboard_backend == "none"


def test_build_wires_the_full_adapter_set(tmp_path: Path):
    """端口全接上；提权两个端口留 None（19 文档 §0 第 3 条），UI 整条不下发。"""
    caps = factory.detect()
    adapter_set = factory.build(caps, app_root=tmp_path, options=AdapterOptions())
    assert isinstance(adapter_set.notifier, MacNotifier)
    assert adapter_set.autostart is not None
    assert adapter_set.elevation is None
    assert adapter_set.autostart_elevated is None
    assert adapter_set.foreground is not None  # NSWorkspace 无需授权
    assert adapter_set.idle is not None
    assert adapter_set.icons is not None
    # 端口契约：Notifier 必须满足含 clear() 的完整协议（A1 的教训）。
    assert isinstance(adapter_set.notifier, ports.Notifier)


def test_explicit_event_tap_preference_builds_only_event_tap(tmp_path: Path):
    """显式指定不静默降级（04 文档 §3.1）：写了 event_tap 就只有 event_tap。"""
    caps = replace(factory.detect(), keyboard=True)
    adapter_set = factory.build(
        caps, app_root=tmp_path, options=AdapterOptions(keyboard_backend="event_tap")
    )
    assert adapter_set.keyboard is not None
    assert adapter_set.keyboard.backend_name == "event_tap"


def test_keyboard_none_disables_the_source(tmp_path: Path):
    caps = factory.detect()
    adapter_set = factory.build(
        caps, app_root=tmp_path, options=AdapterOptions(keyboard_backend="none")
    )
    assert adapter_set.keyboard is None
