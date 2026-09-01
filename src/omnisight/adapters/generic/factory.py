"""通用降级适配器的装配。

它是"没有专用适配器"时的正式路径，不是异常分支：程序照常启动，能做的照常做，
做不到的在 :class:`~omnisight.adapters.ports.Capabilities` 与 ``degraded`` 里
如实写明。
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from ..ports import AdapterSet, Capabilities, DegradedNotice
from .foreground import NullForegroundSource
from .instance_lock import FileInstanceLock
from .notifier import FileNotifier
from .unsupported import UnsupportedAutostart, UnsupportedIconSource

PLATFORM_ID = "generic"
TIER = 0

LOCK_FILENAME = "omnisight.lock"

NO_FOREGROUND = DegradedNotice(
    code="foreground_unavailable",
    severity="warning",
    title="无法识别当前应用",
    detail="当前环境没有可用的前台窗口接口，按应用维度的统计不可用；键盘统计不受影响。",
    hint="Windows / macOS / Linux(X11) 上可获得完整功能",
)

UNSUPPORTED_PLATFORM = DegradedNotice(
    code="platform_unsupported",
    severity="warning",
    title="当前系统未在支持列表中",
    detail=(
        "程序会以最小能力运行：不会崩溃，也不会伪造数据。"
        "支持分级见项目 README。"
    ),
    hint=None,
)

ADAPTER_PENDING = DegradedNotice(
    code="adapter_not_implemented",
    severity="warning",
    title="该平台的适配器尚未实现",
    detail=(
        "端口契约与能力模型已就位，但本平台的采集实现排在后续里程碑"
        "（Linux/X11 见 M8，macOS 见 M9）。当前以通用降级方式运行。"
    ),
    hint="首期正式支持的平台是 Windows",
)


def detect(platform_id: str = PLATFORM_ID, tier: int = TIER) -> Capabilities:
    """通用环境：只假设"能跑 Python"，不假设任何系统 API。"""
    notices = [UNSUPPORTED_PLATFORM] if platform_id == PLATFORM_ID else [ADAPTER_PENDING]
    return Capabilities(
        platform_id=platform_id,  # type: ignore[arg-type]
        tier=tier,
        keyboard=False,
        keyboard_backend="none",
        keyboard_durations=False,
        key_position_stable=False,
        foreground=False,
        window_titles=False,
        idle=False,
        icons=False,
        autostart=False,
        tray=_tray_available(),
        setup_hint="当前环境仅提供最小功能，详见支持分级说明",
        degraded=tuple([*notices, NO_FOREGROUND]),
    )


def _tray_available() -> bool:
    try:
        import pystray  # noqa: F401
    except Exception:
        return False
    return True


def build(environment: Capabilities, *, app_root: Path) -> AdapterSet:
    effective = replace(environment, degraded=environment.degraded)
    return AdapterSet(
        capabilities=effective,
        instance_lock=FileInstanceLock(app_root / LOCK_FILENAME),
        notifier=FileNotifier(app_root),
        autostart=UnsupportedAutostart(),
        foreground=NullForegroundSource(),
        keyboard=None,   # M1 起由 pynput_keys 兜底
        idle=None,
        icons=UnsupportedIconSource(),
    )
