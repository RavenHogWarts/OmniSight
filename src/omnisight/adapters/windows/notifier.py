"""Windows 启动期错误弹框（``MessageBoxW``），失败时退回文件通知。"""

from __future__ import annotations

import ctypes
import logging
from pathlib import Path

from ..generic.notifier import FileNotifier

logger = logging.getLogger(__name__)

MB_OK = 0x0
MB_ICONERROR = 0x10
MB_SETFOREGROUND = 0x10000
MB_TOPMOST = 0x40000


class MessageBoxNotifier:
    """弹框 + 始终同时落到日志与 STARTUP_ERROR.txt。

    两者都做是有意的：弹框会被用户点掉，而排查问题时需要一份留痕。
    """

    __slots__ = ("_fallback",)

    def __init__(self, directory: Path) -> None:
        self._fallback = FileNotifier(directory)

    def error(self, title: str, message: str) -> None:
        self._fallback.error(title, message)
        try:
            ctypes.windll.user32.MessageBoxW(
                None, message, f"OmniSight — {title}", MB_OK | MB_ICONERROR | MB_TOPMOST
            )
        except Exception:  # pragma: no cover - 会话 0 等无桌面环境
            logger.exception("MessageBoxW 不可用，已退回文件通知")

    def clear(self) -> None:
        self._fallback.clear()
