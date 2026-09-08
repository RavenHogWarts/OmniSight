"""macOS（二级平台）适配器包——M9 实现（19 文档批次 B / 20 文档 B4–B7）。

端口对应表见 19 文档 §2.1。两个刻意留 ``None`` 的端口：``ElevationControl`` 与
``ElevatedAutostartControl``（root 换不来任何采集能力，§0 第 3 条），
托盘那一项与设置页那一行整条不下发。
"""

from __future__ import annotations

from .factory import PLATFORM_ID, TIER, build, detect

__all__ = ["PLATFORM_ID", "TIER", "build", "detect"]
