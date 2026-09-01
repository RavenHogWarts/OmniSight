"""命名互斥锁单实例（迁移自 KeyTrace ``single_instance.py``）。

用 ``Local\\`` 前缀（会话级）而非 ``Global\\``：多用户机器上每个登录会话应各自
记录自己的使用情况（10 文档 §3）。
"""

from __future__ import annotations

import ctypes
import logging
from ctypes import wintypes

logger = logging.getLogger(__name__)

ERROR_ALREADY_EXISTS = 183
DEFAULT_MUTEX_NAME = r"Local\OmniSight.Instance"


class NamedMutexInstanceLock:
    __slots__ = ("_handle", "_name")

    def __init__(self, name: str = DEFAULT_MUTEX_NAME) -> None:
        self._name = name
        self._handle: int | None = None

    @property
    def name(self) -> str:
        return self._name

    def acquire(self) -> bool:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        handle = kernel32.CreateMutexW(None, True, self._name)
        last_error = ctypes.get_last_error()
        if not handle:
            # 拿不到互斥锁本身不是"已有实例在跑"，不能因此拒绝启动。
            logger.warning("CreateMutexW 失败（错误码 %s），跳过单实例检查", last_error)
            return True
        if last_error == ERROR_ALREADY_EXISTS:
            kernel32.CloseHandle(handle)
            return False
        self._handle = handle
        return True

    def notify_existing(self) -> bool:
        """本程序常驻托盘、没有主窗口，没有"窗口"可以带到前台。

        返回 False 让调用方退回"打开仪表盘 URL"——这正是 10 文档 §3 为 Windows
        规定的行为，也是用户点图标后期望看到的结果。
        """
        return False

    def release(self) -> None:
        if self._handle is None:
            return
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.ReleaseMutex(self._handle)
        kernel32.CloseHandle(self._handle)
        self._handle = None
