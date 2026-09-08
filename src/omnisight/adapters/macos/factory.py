"""macOS 能力探测与适配器装配（19 文档批次 B / 20 文档 B7）。

与 :mod:`..windows.factory` 同一个两阶段结构：

* :func:`detect` 回答"这台 mac 允许我们做什么"。**只 preflight 绝不 request**
  （:mod:`.permissions`）：「输入监控」未授权时如实报 ``keyboard=False`` 并附
  ``input_monitoring_denied`` 引导——谎报的后果是永远为 0 的键盘面板。
* :func:`build` 只构造不启动；"启动之后真正生效的是什么"由
  :func:`omnisight.adapters.reconcile` 收敛（平台无关层）。

**不实现** ``ElevationControl`` / ``ElevatedAutostartControl``（19 文档 §0 第 3
条）：event tap 的门槛是 TCC 的「输入监控」而不是 root，提权换不来任何采集能力，
反而让"TCC 记录绑定签名"更难推理。两个端口留 ``None``，托盘那一项与设置页那一行
整条不下发。
"""

from __future__ import annotations

import importlib.util
import logging
import platform
from pathlib import Path

from ..chain import ChainedKeyboardSource
from ..generic.instance_lock import FileInstanceLock
from ..ports import AdapterOptions, AdapterSet, Capabilities, KeyboardSource
from .autostart import LaunchAgentAutostart
from .foreground import MacForegroundSource
from .icons import MacIconSource
from .idle import MacIdleSource
from .keyboard import BACKEND_NAME as EVENT_TAP_BACKEND
from .keyboard import EventTapKeyboardSource
from .notifier import MacNotifier
from .permissions import INPUT_MONITORING, INPUT_MONITORING_DENIED, SETUP_HINT, preflight

logger = logging.getLogger(__name__)

PLATFORM_ID = "macos"
TIER = 2
LOCK_FILENAME = "omnisight.lock"


def _os_version() -> str:
    try:
        return f"macOS {platform.mac_ver()[0]}".strip() or "macOS"
    except Exception:  # pragma: no cover
        return "macOS"


def _tray_available() -> bool:
    try:
        import pystray  # noqa: F401
    except Exception:
        return False
    return True


def _pynput_available() -> bool:
    try:
        return importlib.util.find_spec("pynput") is not None
    except (ImportError, ValueError):  # pragma: no cover
        return False


def detect() -> Capabilities:
    """环境能力。授权现状是能力的一部分（TCC 的输入监控拿不到 = 键盘采集为 0）。"""
    required, granted = preflight()
    keyboard_ok = INPUT_MONITORING in granted
    notices = [] if keyboard_ok else [INPUT_MONITORING_DENIED]
    return Capabilities(
        platform_id=PLATFORM_ID,
        tier=TIER,
        os_version=_os_version(),
        keyboard=keyboard_ok,
        keyboard_backend=EVENT_TAP_BACKEND if keyboard_ok else "none",
        keyboard_backends=("auto", EVENT_TAP_BACKEND, "pynput", "none"),
        keyboard_durations=keyboard_ok,
        key_position_stable=keyboard_ok,
        # NSWorkspace 无需任何授权；标题需要「辅助功能」（默认关，08 文档 §2.1）。
        foreground=True,
        window_titles=False,
        idle=True,
        icons=True,
        autostart=True,
        tray=_tray_available(),
        permissions_required=required,
        permissions_granted=granted,
        setup_hint=None if keyboard_ok else SETUP_HINT,
        degraded=tuple(notices),
    )


def _build_keyboard(
    options: AdapterOptions, environment: Capabilities
) -> KeyboardSource | None:
    """按偏好组装后端链（与 Windows 工厂同一条"显式指定不静默降级"的纪律）。"""
    preference = options.keyboard_backend
    if preference == "none":
        return None

    def event_tap() -> EventTapKeyboardSource:
        return EventTapKeyboardSource(on_session_end=options.on_session_end)

    def fallback() -> KeyboardSource | None:
        # pynput 在 mac 上同样走 CGEventTap，同样要「输入监控」；装了才列。
        if not _pynput_available():
            return None
        from ..generic.pynput_keys import PynputKeyboardSource

        return PynputKeyboardSource(idle_notifier=None)

    if preference == EVENT_TAP_BACKEND:
        return ChainedKeyboardSource([event_tap()])
    if preference == "pynput":
        source = fallback()
        return ChainedKeyboardSource([source]) if source is not None else None

    candidates: list[KeyboardSource] = []
    if environment.keyboard:
        candidates.append(event_tap())
    fallback_source = fallback()
    if fallback_source is not None:
        candidates.append(fallback_source)
    if not candidates:
        return None
    return ChainedKeyboardSource(candidates)


def build(
    environment: Capabilities,
    *,
    app_root: Path,
    options: AdapterOptions | None = None,
) -> AdapterSet:
    """装配 macOS 适配器集合。只构造，不申请系统资源（event tap 在 start() 创建）。"""
    options = options or AdapterOptions()

    return AdapterSet(
        capabilities=environment,
        instance_lock=FileInstanceLock(app_root / LOCK_FILENAME),
        notifier=MacNotifier(app_root),
        autostart=LaunchAgentAutostart(),
        # 提权端口留 None：root 换不来采集能力（19 文档 §0 第 3 条）。
        autostart_elevated=None,
        elevation=None,
        foreground=(
            MacForegroundSource(titles_enabled=options.record_window_titles)
            if environment.foreground
            else None
        ),
        keyboard=_build_keyboard(options, environment),
        idle=MacIdleSource() if environment.idle else None,
        icons=MacIconSource() if environment.icons else None,
    )


__all__ = ["PLATFORM_ID", "TIER", "build", "detect"]
