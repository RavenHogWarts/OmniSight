"""Windows 能力探测与适配器装配。

探测与装配分两阶段（02 文档 §5.1）：

* :func:`detect` 回答"**这个操作系统允许我们做什么**"。纯函数、无副作用、永不抛
  异常，结果在建库、日志、状态接口三处使用。
* :func:`build` 回答"**这个版本此刻真能交付什么**"。它**只构造不启动**：注册 Raw Input
  发生在 ``KeyboardSource.start()``，由生命周期在数据库就绪且单实例锁到手之后调用。

"启动之后真正生效的是什么"由 :func:`omnisight.adapters.reconcile` 收敛，那一层是平台
无关的——本文件不负责描述降级文案。
"""

from __future__ import annotations

import ctypes
import importlib.util
import logging
import sys
from pathlib import Path

from ..chain import ChainedKeyboardSource
from ..ports import AdapterOptions, AdapterSet, Capabilities, DegradedNotice, KeyboardSource
from .autostart import RegistryAutostart
from .foreground import WindowsForegroundSource
from .idle import WindowsIdleSource
from .keyboard import BACKEND_NAME as RAW_INPUT_BACKEND
from .keyboard import RawInputKeyboardSource
from .notifier import MessageBoxNotifier
from .single_instance import NamedMutexInstanceLock

logger = logging.getLogger(__name__)

PLATFORM_ID = "windows"
TIER = 1


def _os_version() -> str:
    try:
        info = sys.getwindowsversion()
    except Exception:  # pragma: no cover
        return ""
    return f"{info.major}.{info.minor}.{info.build}"


def _has_export(library: str, symbol: str) -> bool:
    """检查 API 是否存在。刻意只查符号、不调用——探测必须无副作用。

    真正的注册失败（被反作弊拦截、会话 0 无桌面）只有在 ``start()`` 时才会暴露，
    届时走降级路径并如实上报（02 文档 §5.1 第 10 步）。
    """
    try:
        return hasattr(ctypes.WinDLL(library), symbol)
    except OSError:  # pragma: no cover - 系统 DLL 缺失
        return False


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
    """环境能力：Windows 上这些 API 对普通进程一律开放，无需授权。"""
    return Capabilities(
        platform_id=PLATFORM_ID,
        tier=TIER,
        os_version=_os_version(),
        keyboard=_has_export("user32", "RegisterRawInputDevices"),
        keyboard_backend=RAW_INPUT_BACKEND,
        keyboard_durations=True,
        key_position_stable=True,
        foreground=_has_export("user32", "GetForegroundWindow"),
        window_titles=_has_export("user32", "GetWindowTextW"),
        idle=_has_export("user32", "GetLastInputInfo"),
        icons=_has_export("shell32", "SHGetFileInfoW"),
        autostart=True,
        tray=_tray_available(),
        permissions_required=(),
        permissions_granted=(),
    )


#: 图标提取排在 M2（04 文档 §6 的持久化缓存与后台解析一并做）。
_ICONS_PENDING = DegradedNotice(
    code="icons_not_implemented",
    severity="warning",
    title="应用图标尚未启用",
    detail="应用列表会显示首字母色块而不是真实图标；统计数据不受影响。",
    hint=None,
)


def _build_keyboard(options: AdapterOptions, environment: Capabilities) -> KeyboardSource | None:
    """按用户偏好组装后端链。

    **显式指定时不静默降级**（04 文档 §3.1）：写了 ``raw_input`` 就只试 Raw Input，
    失败就是失败——用户明确选了这个后端，悄悄换成另一个等于欺骗。只有 ``auto`` 才
    允许链式回退。
    """
    preference = options.keyboard_backend
    if preference == "none":
        return None

    def raw_input_source() -> RawInputKeyboardSource:
        return RawInputKeyboardSource(on_session_end=options.on_session_end)

    if preference == RAW_INPUT_BACKEND:
        return ChainedKeyboardSource([raw_input_source()])
    if preference == "pynput":
        return _fallback_only()

    candidates: list[KeyboardSource] = []
    if environment.keyboard:
        candidates.append(raw_input_source())
    if _pynput_available():
        from ..generic.pynput_keys import PynputKeyboardSource

        candidates.append(PynputKeyboardSource())
    if not candidates:
        return None
    return ChainedKeyboardSource(candidates)


def _fallback_only() -> KeyboardSource | None:
    if not _pynput_available():
        return None
    from ..generic.pynput_keys import PynputKeyboardSource

    return ChainedKeyboardSource([PynputKeyboardSource()])


def build(
    environment: Capabilities,
    *,
    app_root: Path,
    options: AdapterOptions | None = None,
) -> AdapterSet:
    """装配 Windows 适配器集合。只构造，不申请系统资源。"""
    options = options or AdapterOptions()
    notices: list[DegradedNotice] = []

    autostart = RegistryAutostart()
    if autostart.repair_if_stale():
        logger.info("已把过期的开机自启项改写为当前程序路径")

    if not environment.tray:
        notices.append(
            DegradedNotice(
                code="tray_unavailable",
                severity="warning",
                title="托盘图标不可用",
                detail="未能加载 pystray，程序会继续在后台运行。",
                hint="通过浏览器访问仪表盘地址即可使用，退出请用设置页的「退出」按钮",
            )
        )
    if environment.icons:
        notices.append(_ICONS_PENDING)

    from dataclasses import replace

    effective = replace(
        environment,
        # 唯一还没接线的能力。绝不上报尚未实现的东西：UI 依据这份数据决定显示哪些面板。
        icons=False,
        degraded=(*environment.degraded, *notices),
    )
    return AdapterSet(
        capabilities=effective,
        instance_lock=NamedMutexInstanceLock(),
        notifier=MessageBoxNotifier(app_root),
        autostart=autostart,
        foreground=(
            WindowsForegroundSource(titles_enabled=options.record_window_titles)
            if environment.foreground
            else None
        ),
        keyboard=_build_keyboard(options, environment),
        idle=WindowsIdleSource() if environment.idle else None,
        icons=None,  # M2
    )
