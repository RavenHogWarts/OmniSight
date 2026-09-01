"""可见窗口枚举（← TimeLens ``monitor.py:list_visible_apps``）。

供应用选择器用（"我想看 VS Code 的键盘热力图"里的下拉框）。它与 ``foreground.py``
共用同一份系统外壳过滤名单，否则选择器里会冒出"资源管理器"这类用户根本不会去选的
条目，而统计里又没有它们的数据。

单独成文件是因为它与前台探测的调用节奏完全不同：前台是 1 秒一次的热路径，枚举是
用户点开下拉框时才走一次的冷路径（``EnumWindows`` 遍历全部顶层窗口 + 每个窗口一次
``psutil.Process``，几十毫秒量级）。
"""

from __future__ import annotations

import logging

import psutil
import win32gui
import win32process

from ..ports import AppIdentity
from .shell_filter import SHELL_KEYS, display_name_for

logger = logging.getLogger(__name__)


def list_visible_apps() -> list[AppIdentity]:
    """返回拥有可见且有标题的顶层窗口的应用，按展示名排序、按 ``app_key`` 去重。"""
    found: dict[str, AppIdentity] = {}

    def visit(hwnd: int, _extra: object) -> bool:
        try:
            if not win32gui.IsWindowVisible(hwnd):
                return True
            if not win32gui.GetWindowText(hwnd).strip():
                return True
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if not pid:
                return True
            process = psutil.Process(pid)
            process_name = process.name()
            if not process_name or process_name.casefold() in SHELL_KEYS:
                return True
            try:
                exe_path = process.exe()
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                exe_path = ""
            app_key = process_name.casefold()
            found.setdefault(
                app_key,
                AppIdentity(
                    app_key=app_key,
                    identity_kind="process",
                    display_name=display_name_for(process_name),
                    process_name=process_name,
                    exe_path=exe_path,
                ),
            )
        except (psutil.AccessDenied, psutil.NoSuchProcess, OSError):
            # 进程在遍历途中退出是常态，不是异常情况。
            pass
        return True

    try:
        win32gui.EnumWindows(visit, None)
    except OSError:
        # EnumWindows 在回调抛异常时会整体失败；返回已收集到的部分好于返回空。
        logger.exception("枚举可见窗口失败，返回已收集到的部分")
    return sorted(found.values(), key=lambda item: item.display_name.casefold())


__all__ = ["list_visible_apps"]
