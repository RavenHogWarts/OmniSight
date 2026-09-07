"""主线程归属的分派（02 文档 §3、19 文档 A2、20 文档 A2）。

``needs_main_loop`` 在端口上声明了三个里程碑、被 chain 转发，却没有任何调用者——
而 macOS 的 event tap **必须**挂在主线程 runloop 上，不接上它就是"tap 创建成功、
回调永不触发、状态页一切正常"的最坏失败。这里钉住分派的两条分支：

* ``needs_main_loop=False``（Windows 恒如此）：托盘留在主线程，逐字原路径；
* ``=True``（未来的 macOS）：托盘退到子线程，主线程交给 ``run_main_loop()``。

决定权在端口属性，不在平台判断——这是跨平台策略的全部要点（13 文档 §4）。
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


def test_loop_backend_takes_the_main_thread(monkeypatch):
    """needs_main_loop=True：托盘退到子线程，主线程交给 run_main_loop。"""
    tray = RecordingTray()
    lifecycle = _lifecycle_with(tray, monkeypatch)
    backend = LoopBackend()
    lifecycle._run_foreground(
        SimpleNamespace(adapter_set=SimpleNamespace(keyboard=backend))
    )
    assert backend.main_loop_threads == [threading.current_thread().name]
    assert tray.threads, "托盘也要跑起来——只是不在主线程"
    assert threading.current_thread().name not in tray.threads


def test_missing_keyboard_source_keeps_the_original_path(monkeypatch):
    """keyboard 为 None（能力缺失/用户选了 none）：与 False 同一条原路径。"""
    tray = RecordingTray()
    lifecycle = _lifecycle_with(tray, monkeypatch)
    lifecycle._run_foreground(SimpleNamespace(adapter_set=SimpleNamespace(keyboard=None)))
    assert tray.threads == [threading.current_thread().name]
