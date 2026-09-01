"""Linux / Wayland（三级平台，仅键盘统计，实验性） —— 占位包。

首期不实现任何采集，只保证 ``adapters.detect()`` 能识别出这个平台并**如实
上报"适配器未实现"**，装配退回通用降级。目录与工厂函数现在就位，是为了让后续
里程碑只需填充本包，不必改动核心层（13 文档 §7.9）。
"""

from __future__ import annotations

from pathlib import Path

from ..generic import factory as _generic
from ..ports import AdapterOptions, AdapterSet, Capabilities

PLATFORM_ID = "linux_wayland"
TIER = 3


def detect() -> Capabilities:
    """Wayland 上连兜底后端都不可用，必须如实说出来。

    通用 detect() 会因为「装了 pynput」而报 ``keyboard=True``，但 pynput 在 Wayland
    上**结构性**地拿不到全局按键（安全模型不允许），这不是权限问题。三级平台的键盘
    方案是 evdev 直读，排在 M8。此处把这一位压回 False，好过让用户等一个永远不会来的
    数字（R15）。
    """
    from dataclasses import replace

    return replace(
        _generic.detect(platform_id=PLATFORM_ID, tier=TIER),
        keyboard=False,
        keyboard_backend="none",
        keyboard_durations=False,
        idle=False,
    )


def build(
    environment: Capabilities, *, app_root: Path, options: AdapterOptions | None = None
) -> AdapterSet:
    return _generic.build(environment, app_root=app_root, options=options)


__all__ = ["PLATFORM_ID", "TIER", "build", "detect"]
