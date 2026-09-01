"""Linux / X11（二级平台，M8 实现） —— 占位包。

首期不实现任何采集，只保证 ``adapters.detect()`` 能识别出这个平台并**如实
上报"适配器未实现"**，装配退回通用降级。目录与工厂函数现在就位，是为了让后续
里程碑只需填充本包，不必改动核心层（13 文档 §7.9）。
"""

from __future__ import annotations

from pathlib import Path

from ..generic import factory as _generic
from ..ports import AdapterOptions, AdapterSet, Capabilities

PLATFORM_ID = "linux_x11"
TIER = 2


def detect() -> Capabilities:
    return _generic.detect(platform_id=PLATFORM_ID, tier=TIER)


def build(
    environment: Capabilities, *, app_root: Path, options: AdapterOptions | None = None
) -> AdapterSet:
    return _generic.build(environment, app_root=app_root, options=options)


__all__ = ["PLATFORM_ID", "TIER", "build", "detect"]
