"""前台应用探测（← TimeLens ``monitor.py:_get_foreground_info``）。

Windows 上应用身份就是进程名：``app_key = casefold(process_name)``、
``identity_kind = "process"``。这个取值与旧 TimeLens 的 ``process_key`` **完全一致**，
所以迁移不需要转换。字段名之所以是中性的 ``app_key``，是因为进程名只在 Windows 上
是可靠的应用身份（03 文档 §2.2）。

窗口标题的处理是本文件唯一的策略性决定：``titles_enabled`` 为假时**只读取标题用于
判空**（无标题的顶层窗口不算前台应用，沿用 TimeLens 的判据），但绝不把它返回给上层。
这比"上层拿到后再丢掉"更彻底——标题根本没有离开这个函数。
``privacy.record_window_titles`` 默认关闭（08 文档 §2.1）。
"""

from __future__ import annotations

import logging

import psutil
import win32gui
import win32process

from ..ports import AppIdentity, ForegroundInfo
from .shell_filter import SHELL_KEYS, display_name_for
from .window_enum import list_visible_apps

logger = logging.getLogger(__name__)


class WindowsForegroundSource:
    """实现 :class:`~omnisight.adapters.ports.ForegroundSource`。"""

    __slots__ = ("titles_enabled",)

    def __init__(self, *, titles_enabled: bool = False) -> None:
        self.titles_enabled = titles_enabled

    def current(self) -> ForegroundInfo | None:
        """当前前台应用；无前台窗口、最小化、系统外壳、取不到进程时返回 ``None``。

        **绝不抛异常**：调用方是 1 秒一次的轮询循环，让它处理异常等于要求每秒
        写一次 try/except，且任何一次失败都不该中断采集。
        """
        try:
            return self._probe()
        except Exception:
            # 窗口在探测途中消失、进程权限不足、COM 抖动——都属于常态。
            logger.debug("前台窗口探测失败，按无前台处理", exc_info=True)
            return None

    def _probe(self) -> ForegroundInfo | None:
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            # 锁屏、桌面切换动画、UAC 提示期间会短暂出现。
            return None
        if win32gui.IsIconic(hwnd):
            return None

        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if not pid:
            return None
        try:
            process = psutil.Process(pid)
            process_name = process.name()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return None
        if not process_name:
            return None

        app_key = process_name.casefold()
        if app_key in SHELL_KEYS:
            return None

        # 无标题的顶层窗口不算"用户正在用的应用"（沿用 TimeLens 判据）。标题在这里
        # 只用于判空，titles_enabled 为假时不会离开本函数。
        title = win32gui.GetWindowText(hwnd) or ""
        if not title:
            return None

        try:
            exe_path = process.exe()
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            exe_path = ""

        return ForegroundInfo(
            identity=AppIdentity(
                app_key=app_key,
                identity_kind="process",
                display_name=display_name_for(process_name),
                process_name=process_name,
                exe_path=exe_path,
            ),
            window_title=title if self.titles_enabled else "",
        )

    def list_running(self) -> list[AppIdentity]:
        return list_visible_apps()


__all__ = ["WindowsForegroundSource"]
