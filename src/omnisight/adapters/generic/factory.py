"""通用降级适配器的装配。

它是"没有专用适配器"时的正式路径，不是异常分支：程序照常启动，能做的照常做，
做不到的在 :class:`~omnisight.adapters.ports.Capabilities` 与 ``degraded`` 里
如实写明。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from ..chain import ChainedKeyboardSource
from ..ports import AdapterOptions, AdapterSet, Capabilities, DegradedNotice
from .foreground import NullForegroundSource
from .idle import LastInputIdleSource
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


def _pynput_installed() -> bool:
    """只查模块是否存在，**不导入**——探测必须无副作用（导入 pynput 会拉起平台后端）。"""
    try:
        return importlib.util.find_spec("pynput") is not None
    except (ImportError, ValueError):  # pragma: no cover - 异常的 import 环境
        return False


def detect(platform_id: str = PLATFORM_ID, tier: int = TIER) -> Capabilities:
    """通用环境：只假设"能跑 Python" + 兜底键盘后端装没装，不假设任何系统 API。"""
    notices = [UNSUPPORTED_PLATFORM] if platform_id == PLATFORM_ID else [ADAPTER_PENDING]
    has_pynput = _pynput_installed()
    return Capabilities(
        platform_id=platform_id,  # type: ignore[arg-type]
        tier=tier,
        keyboard=has_pynput,
        keyboard_backend="pynput" if has_pynput else "none",
        keyboard_durations=has_pynput,
        # 兜底后端拿不到物理位置码，这一位永远是 False（04 文档 §3.1）。
        key_position_stable=False,
        foreground=False,
        window_titles=False,
        # 没有系统级空闲 API，只能用「最近一次按键」近似——因此它依赖兜底键盘后端。
        idle=has_pynput,
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


def build(
    environment: Capabilities,
    *,
    app_root: Path,
    options: AdapterOptions | None = None,
) -> AdapterSet:
    """只构造，不启动。按需导入 pynput——只要专用后端可用就永远不加载它（08 文档 §8）。"""
    options = options or AdapterOptions()
    idle = LastInputIdleSource()
    keyboard = None
    if options.keyboard_backend != "none" and environment.keyboard:
        from .pynput_keys import PynputKeyboardSource

        keyboard = ChainedKeyboardSource(
            [PynputKeyboardSource(idle_notifier=idle.note_input)]
        )
    return AdapterSet(
        capabilities=environment,
        instance_lock=FileInstanceLock(app_root / LOCK_FILENAME),
        notifier=FileNotifier(app_root),
        autostart=UnsupportedAutostart(),
        # 恒返回 None：没有应用归因，但键盘统计照常，且界面会说明原因。
        foreground=NullForegroundSource(),
        keyboard=keyboard,
        idle=idle,
        icons=UnsupportedIconSource(),
    )
