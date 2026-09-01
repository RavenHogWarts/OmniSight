"""通用降级适配器：让程序在未预料的环境里**能跑且不骗人**（13 文档 §6.5）。

它不是"临时凑数"，而是产品的一条正式路径：没有专用适配器的系统上，用户仍能
得到键盘统计，只是应用归因不可用——并且界面会如实说明这一点。
"""

from .foreground import NullForegroundSource
from .idle import LastInputIdleSource
from .instance_lock import FileInstanceLock
from .notifier import FileNotifier
from .unsupported import UnsupportedAutostart, UnsupportedIconSource

__all__ = [
    "FileInstanceLock",
    "FileNotifier",
    "LastInputIdleSource",
    "NullForegroundSource",
    "UnsupportedAutostart",
    "UnsupportedIconSource",
]
