"""能力探测（11 文档 §8.2）。

探测逻辑是纯函数：输入环境变量与几个"能不能连上"的布尔值，输出 Capabilities。
因此可以完全用伪造输入测试，不需要真的跑在那个平台上——这也是首期就能为 M8/M9
写测试的原因。
"""

from __future__ import annotations

import pytest

from omnisight import adapters
from omnisight.adapters.ports import Capabilities


@pytest.fixture(autouse=True)
def _clean_session_env(monkeypatch):
    monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.delenv("DISPLAY", raising=False)


def test_windows_is_tier_one_with_full_capabilities(monkeypatch):
    caps = adapters.detect(adapters.Probe(platform="win32"))
    assert caps.platform_id == "windows"
    assert caps.tier == 1
    assert caps.keyboard_backend == "raw_input"
    assert caps.key_position_stable is True


def test_wayland_session_is_not_mistaken_for_x11(monkeypatch):
    """XWayland 会让 X11 连接成功，但原生 Wayland 窗口完全不可见。

    信任 X11 探测结果会产出最坏的一种情况——程序看起来在正常工作，
    数据却大面积缺失（13 文档 §5）。
    """
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setenv("DISPLAY", ":0")
    caps = adapters.detect(adapters.Probe(platform="linux", x11_connectable=True))
    assert caps.platform_id == "linux_wayland"
    assert caps.tier == 3
    assert caps.foreground is False


def test_wayland_display_alone_is_enough_to_detect_wayland(monkeypatch):
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    caps = adapters.detect(adapters.Probe(platform="linux", x11_connectable=True))
    assert caps.platform_id == "linux_wayland"


def test_x11_detected_when_session_type_is_x11(monkeypatch):
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    caps = adapters.detect(adapters.Probe(platform="linux", x11_connectable=True))
    assert caps.platform_id == "linux_x11"
    assert caps.tier == 2


def test_unknown_platform_falls_back_to_generic_without_crashing():
    caps = adapters.detect(adapters.Probe(platform="sunos5"))
    assert caps.platform_id == "generic"
    assert caps.tier == 0
    assert caps.supported is False


def test_keyboard_failure_does_not_disable_foreground():
    """键盘后端失败不该把屏幕时间统计一起带下去（10 文档 §6）。"""
    caps = adapters.detect(adapters.Probe(platform="win32", raw_input_registrable=False))
    assert caps.keyboard_backend == "pynput"
    # 左右修饰键不可分，必须如实上报，否则热力图形态突变无从解释。
    assert caps.key_position_stable is False
    assert caps.foreground is True
    assert any(n.code == "keyboard_backend_degraded" for n in caps.degraded)


def test_degradation_notices_explain_what_still_works():
    """文案必须同时讲清缺什么、什么仍正常、怎么解决（06 文档 §4.2）。"""
    caps = adapters.detect(adapters.Probe(platform="win32", raw_input_registrable=False))
    notice = next(n for n in caps.degraded if n.code == "keyboard_backend_degraded")
    assert notice.title and notice.detail
    assert notice.hint, "缺能力却没有给出任何指引，对用户是死路"


def test_unimplemented_platform_says_so_instead_of_pretending(monkeypatch):
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    caps = adapters.detect(adapters.Probe(platform="linux", x11_connectable=True))
    assert any(n.code == "adapter_not_implemented" for n in caps.degraded)
    assert caps.foreground is False


def test_detect_never_raises_even_if_platform_module_explodes(monkeypatch):
    def boom(_platform_id):
        raise RuntimeError("探测炸了")

    monkeypatch.setattr(adapters, "_platform_module", boom)
    caps = adapters.detect(adapters.Probe(platform="win32"))
    assert caps.platform_id == "generic"


def test_capabilities_to_dict_omits_platform_fields():
    """``platform`` 与 ``degraded`` 在状态接口里是独立段落（05 文档 §7）。"""
    payload = Capabilities(platform_id="windows", tier=1).to_dict()
    assert "platform_id" not in payload
    assert "tier" not in payload
    assert "degraded" not in payload
    assert "keyboard" in payload


# ── 第三阶段：reconcile()（M1 新增，02 文档 §5.1 的能力语义表）────────────────
#
# detect() 说"这个操作系统允许什么"，build() 说"本版本实现了什么"，reconcile() 说
# "启动之后真正生效的是什么"。**只有第三份能给 UI 与 /api/v1/status 看**——前两份说
# 「键盘可用」而后端其实注册失败时，用户会看到一个永远是 0 的图表却无从解释。


class _FakeBackend:
    def __init__(self, running: bool, backend_name: str = "raw_input") -> None:
        self.running = running
        self.backend_name = backend_name


def test_reconcile_reports_the_backend_that_actually_started():
    caps = adapters.detect(adapters.Probe(platform="win32"))
    effective = adapters.reconcile(
        caps,
        keyboard=_FakeBackend(True, "raw_input"),
        foreground_running=True,
        idle_available=True,
        titles_recorded=False,
    )
    assert effective.keyboard is True
    assert effective.keyboard_backend == "raw_input"
    assert effective.key_position_stable is True
    assert effective.window_titles is False, "能力允许但用户没开启 → 这一位是假"
    assert effective.degraded == caps.degraded


def test_reconcile_marks_keyboard_unavailable_when_the_backend_did_not_start():
    """Raw Input 被反作弊拦截、会话 0 无桌面——起不来时必须如实上报并给出说明。"""
    caps = adapters.detect(adapters.Probe(platform="win32"))
    effective = adapters.reconcile(caps, keyboard=None, foreground_running=True)
    assert effective.keyboard is False
    assert effective.keyboard_backend == "none"
    assert effective.keyboard_durations is False
    assert effective.key_position_stable is False
    codes = {notice.code for notice in effective.degraded}
    assert adapters.KEYBOARD_UNAVAILABLE.code in codes


def test_reconcile_flags_a_fallback_backend_as_position_unstable():
    """链式回退到 pynput 之后左右修饰键会合并，UI 必须知道这件事（04 文档 §3.1）。"""
    caps = adapters.detect(adapters.Probe(platform="win32"))
    effective = adapters.reconcile(
        caps, keyboard=_FakeBackend(True, "pynput"), foreground_running=True
    )
    assert effective.keyboard_backend == "pynput"
    assert effective.key_position_stable is False
    assert len(effective.degraded) > len(caps.degraded), "降级必须留下说明"


def test_reconcile_keeps_foreground_and_keyboard_independent():
    """键盘失败不许把屏幕时间一起拖下水，反之亦然（10 文档 §6）。"""
    caps = adapters.detect(adapters.Probe(platform="win32"))
    keyboard_only = adapters.reconcile(
        caps, keyboard=_FakeBackend(True), foreground_running=False
    )
    assert keyboard_only.keyboard is True
    assert keyboard_only.foreground is False
    assert keyboard_only.window_titles is False

    foreground_only = adapters.reconcile(caps, keyboard=None, foreground_running=True)
    assert foreground_only.foreground is True
    assert foreground_only.keyboard is False


def test_reconcile_never_upgrades_a_capability_the_environment_lacks():
    """收敛只会往下走。往上走等于凭空宣称一个平台做不到的事。"""
    caps = Capabilities(platform_id="linux_wayland", tier=3, keyboard=False, foreground=False)
    effective = adapters.reconcile(
        caps,
        keyboard=_FakeBackend(True, "evdev"),
        foreground_running=True,
        idle_available=True,
        titles_recorded=True,
    )
    assert effective.window_titles is False, "环境拿不到标题时不许因为用户开了就变真"
    assert effective.idle is False


def test_reconcile_is_idempotent():
    """状态接口每次请求都读同一份能力；重复收敛不该不断堆积降级说明。"""
    caps = adapters.detect(adapters.Probe(platform="win32"))
    once = adapters.reconcile(caps, keyboard=None, foreground_running=False)
    twice = adapters.reconcile(once, keyboard=None, foreground_running=False)
    assert {notice.code for notice in once.degraded} == {
        notice.code for notice in twice.degraded
    }
