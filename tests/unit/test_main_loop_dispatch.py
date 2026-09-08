"""主线程归属的分派（02 文档 §3、19 文档 A2、20 文档 A2）。

``needs_main_loop`` 在端口上声明了三个里程碑、被 chain 转发，却没有任何调用者——
而 macOS 的 event tap **必须**挂在主线程 runloop 上，不接上它就是"tap 创建成功、
回调永不触发、状态页一切正常"的最坏失败。

**主线程归谁，真机已经定了（R23，原为 20 文档 A2 的未决问题）。** 原设计是
"谁需要主线程谁拿"：后端 ``needs_main_loop=True`` 时托盘退到子线程。真机（macOS
26.6.2 / Apple Silicon）证明这条分派不可用——pystray 的 darwin 后端要在
``Icon.__init__`` 里建 ``NSApplication`` 与 ``NSStatusBar``，AppKit 强制主线程，
子线程初始化必抛 ``NSInternalInconsistencyException``；托盘线程一死，用户既没有
菜单栏图标（打不开仪表盘、也退不出程序），又因为 ``NSApplication`` 从未建立而让
Dock 图标永远停在"启动中"的弹跳状态。

现在的分派是**托盘恒在主线程**，后端不再独占：需要主 runloop 的后端在 ``start()``
时已把 tap 挂到主 runloop 的 ``kCFRunLoopCommonModes``，而 pystray 的 ``NSApp.run()``
驱动的就是同一个主 CFRunLoop，两者共用一条循环。因此 ``run_main_loop()`` 不再被调用。

决定权仍在端口属性，不在平台判断——这是跨平台策略的全部要点（13 文档 §4）；
改变的只是"端口说需要主循环"时该怎么满足它。
"""

from __future__ import annotations

import threading
from types import SimpleNamespace

from omnisight.core.lifecycle import Lifecycle


class RecordingTray:
    def __init__(self) -> None:
        self.threads: list[str] = []

    def run(self) -> None:
        self.threads.append(threading.current_thread().name)


class LoopBackend:
    """needs_main_loop=True 的假键盘后端（B6 之前没有真实实现）。"""

    def __init__(self) -> None:
        self.main_loop_threads: list[str] = []

    @property
    def needs_main_loop(self) -> bool:
        return True

    def run_main_loop(self) -> None:
        self.main_loop_threads.append(threading.current_thread().name)


class PumpBackend:
    """needs_main_loop=False 的假键盘后端（Windows Raw Input 的形状）。"""

    needs_main_loop = False

    def run_main_loop(self) -> None:  # pragma: no cover - 不该被调用
        raise AssertionError("不需要主循环的后端不该被要求驱动主 runloop")


def _lifecycle_with(tray: RecordingTray, monkeypatch) -> Lifecycle:
    lifecycle = Lifecycle()
    monkeypatch.setattr(lifecycle, "_build_tray", lambda runtime: tray)
    return lifecycle


def test_windows_shaped_backend_keeps_tray_on_main_thread(monkeypatch):
    """needs_main_loop=False：托盘在主线程跑，后端不被碰——与改动前逐字相同。"""
    tray = RecordingTray()
    lifecycle = _lifecycle_with(tray, monkeypatch)
    backend = PumpBackend()
    lifecycle._run_foreground(
        SimpleNamespace(adapter_set=SimpleNamespace(keyboard=backend))
    )
    assert tray.threads == [threading.current_thread().name]


def test_tray_keeps_the_main_thread_even_with_a_loop_backend(monkeypatch):
    """needs_main_loop=True：托盘仍在主线程，后端不再单独驱动主 runloop（R23）。

    这条断言的是被真机推翻后改定的分派：让后端拿走主线程会连托盘一起丢掉
    （AppKit 主线程规则），而 tap 早已挂在主 runloop 上，靠托盘的 ``NSApp.run()``
    驱动同一条循环即可，所以 ``run_main_loop()`` 应当是**一次都不被调用**。
    """
    tray = RecordingTray()
    lifecycle = _lifecycle_with(tray, monkeypatch)
    backend = LoopBackend()
    lifecycle._run_foreground(
        SimpleNamespace(adapter_set=SimpleNamespace(keyboard=backend))
    )
    assert tray.threads == [threading.current_thread().name]
    assert not backend.main_loop_threads, "托盘的 NSApp.run() 已驱动同一条主 runloop"


def test_missing_keyboard_source_keeps_the_original_path(monkeypatch):
    """keyboard 为 None（能力缺失/用户选了 none）：与 False 同一条原路径。"""
    tray = RecordingTray()
    lifecycle = _lifecycle_with(tray, monkeypatch)
    lifecycle._run_foreground(SimpleNamespace(adapter_set=SimpleNamespace(keyboard=None)))
    assert tray.threads == [threading.current_thread().name]
