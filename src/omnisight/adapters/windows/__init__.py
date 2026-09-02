"""Windows 适配器（一级平台，首期唯一完整实现）。

本包是唯一允许 ``import win32*`` / ``ctypes.windll`` 的地方之一。对外只暴露
:func:`detect` 与 :func:`build`，核心层拿到的永远是 ``ports.py`` 里的协议。

**这里刻意不写 ``from .factory import build, detect``。** 那一句会在导入本包的**任何**子模块
时把整个 Windows 栈（``winreg``、``win32gui``……）一并拉进来，于是
``from omnisight.adapters.windows import keymap_native`` 这种纯查表的导入在 Linux / macOS 上
直接 ``ImportError``——**而那正是"除 ``windows_only`` 外全部测试都要在三个平台通过"这条约束
（11 文档 §1）要检验的东西**：`windows_only` 标记只在运行期跳过用例，收集期照样要 import。

PEP 562 的模块级 ``__getattr__`` 让 ``windows.detect`` / ``windows.build`` 照旧可用
（``adapters._platform_module()`` 拿到的就是本包），同时把导入推迟到真要用的那一刻。
"""

from __future__ import annotations

from typing import Any

__all__ = ["build", "detect"]


def __getattr__(name: str) -> Any:
    if name in __all__:
        from . import factory

        return getattr(factory, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
