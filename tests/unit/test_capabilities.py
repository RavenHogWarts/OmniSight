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
