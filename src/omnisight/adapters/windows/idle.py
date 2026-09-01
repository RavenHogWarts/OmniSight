"""系统空闲时长（← TimeLens ``monitor.py:_get_idle_seconds``）。

``GetLastInputInfo`` 看得见**全部**输入（键盘、鼠标、触控），这是它比"最近一次按键
时间"这种近似强的地方：用户看视频时不停动鼠标但不打字，近似法会误判为空闲，
它不会。通用兜底适配器只能用近似法，因此那里的 ``idle`` 精度更低（见
``adapters/generic/idle.py`` 的说明）。

``dwTime`` 来自 ``GetTickCount``，49.7 天回绕一次。``& 0xFFFFFFFF`` 让回绕时刻的差值
仍然正确——不做掩码会在开机 49.7 天后算出一个巨大的空闲时长，把当前会话凭空截断。
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import ClassVar


class LASTINPUTINFO(ctypes.Structure):
    _fields_: ClassVar = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


class WindowsIdleSource:
    """实现 :class:`~omnisight.adapters.ports.IdleSource`。"""

    __slots__ = ()

    def idle_seconds(self) -> float:
        info = LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(LASTINPUTINFO)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
            # 取不到就当作"刚刚有输入"。反过来（当作空闲）会错误地截断会话。
            return 0.0
        tick = ctypes.windll.kernel32.GetTickCount()
        return ((tick - info.dwTime) & 0xFFFFFFFF) / 1000.0


__all__ = ["WindowsIdleSource"]
