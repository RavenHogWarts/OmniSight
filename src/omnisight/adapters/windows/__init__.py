"""Windows 适配器（一级平台，首期唯一完整实现）。

本包是唯一允许 ``import win32*`` / ``ctypes.windll`` 的地方之一。对外只暴露
:func:`detect` 与 :func:`build`，核心层拿到的永远是 ``ports.py`` 里的协议。
"""

from .factory import build, detect

__all__ = ["build", "detect"]
