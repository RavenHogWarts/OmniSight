"""macOS（二级平台，M9 实现） —— 占位包。

首期不实现任何采集，只保证 ``adapters.detect()`` 能识别出这个平台并**如实
上报"适配器未实现"**，装配退回通用降级。目录与工厂函数现在就位，是为了让后续
里程碑只需填充本包，不必改动核心层（13 文档 §7.9）。
"""

from __future__ import annotations

from pathlib import Path

from ..generic import factory as _generic
from ..ports import AdapterSet, Capabilities

PLATFORM_ID = "macos"
TIER = 2


def detect() -> Capabilities:
    return _generic.detect(platform_id=PLATFORM_ID, tier=TIER)


def build(environment: Capabilities, *, app_root: Path) -> AdapterSet:
    return _generic.build(environment, app_root=app_root)


__all__ = ["PLATFORM_ID", "TIER", "build", "detect"]
