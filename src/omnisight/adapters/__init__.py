"""适配器装配入口：**全仓库唯一允许判断平台身份的运行时模块**。

（另一处豁免是 ``core/paths.py`` 的 ``_platform_app_dir()``，理由见该文件；
构建脚本 ``tools/build.py`` 不属于运行时，不受此约束——见 10 文档 §2.1。）

两阶段设计（02 文档 §5.1）：

* :func:`detect` —— 探测。纯函数、无副作用、**永不抛异常**，结果用于建库、
  日志首行与状态接口。
* :func:`build` —— 装配。可能申请系统资源，必须在数据库就绪之后调用；返回的
  ``AdapterSet.capabilities`` 是"环境允许 ∧ 本版本已实现"的交集，也是 UI 唯一
  应当相信的那一份。
"""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass, replace
from pathlib import Path

from .ports import (
    AdapterOptions,
    AdapterSet,
    Capabilities,
    DegradedNotice,
    ForegroundInfo,
    RawKeyEvent,
    UnsupportedOperation,
)

logger = logging.getLogger(__name__)

__all__ = [
    "AdapterOptions",
    "AdapterSet",
    "Capabilities",
    "DegradedNotice",
    "ForegroundInfo",
    "Probe",
    "RawKeyEvent",
    "UnsupportedOperation",
    "build",
    "detect",
    "reconcile",
    "system_probe",
]


@dataclass(frozen=True, slots=True)
class Probe:
    """环境事实的快照。测试通过构造它来伪造环境（11 文档 §8.2）。

    刻意只装"需要试一下才知道"的事实；能从环境变量直接读到的（会话类型等）
    由 :func:`detect` 自己读，这样测试用 ``monkeypatch.setenv`` 就能覆盖。
    """

    platform: str | None = None
    x11_connectable: bool = False
    raw_input_registrable: bool = True


def system_probe() -> Probe:
    """测量真实环境。任何探测失败都退化为"不可用"，绝不抛异常。"""
    return Probe(
        platform=sys.platform,
        x11_connectable=_x11_connectable(),
        raw_input_registrable=True,
    )


def _x11_connectable() -> bool:
    if sys.platform == "win32" or sys.platform == "darwin":
        return False
    if not os.environ.get("DISPLAY"):
        return False
    try:
        from Xlib import display as xdisplay  # type: ignore[import-not-found]
    except Exception:
        return False
    try:
        connection = xdisplay.Display()
    except Exception:
        return False
    connection.close()
    return True


def _resolve_platform_id(probe: Probe) -> str:
    """把环境映射到 platform_id。这是本函数存在的全部意义。"""
    platform = probe.platform or sys.platform
    if platform == "win32":
        return "windows"
    if platform == "darwin":
        return "macos"
    if platform.startswith("linux"):
        return _resolve_linux_session(probe)
    return "generic"


def _resolve_linux_session(probe: Probe) -> str:
    """Wayland 的判定以会话类型为准，**不以"能否连上 X11"为准**。

    XWayland 会让 X11 连接成功，但 ``_NET_ACTIVE_WINDOW`` 只覆盖 XWayland 客户端，
    原生 Wayland 应用完全不可见。若据此判定为 X11，会产生最坏的一种结果——
    程序看起来在正常工作，数据却大面积缺失（13 文档 §5）。
    """
    session_type = os.environ.get("XDG_SESSION_TYPE", "").strip().casefold()
    if session_type == "wayland" or os.environ.get("WAYLAND_DISPLAY"):
        return "linux_wayland"
    if probe.x11_connectable:
        return "linux_x11"
    return "generic"


def _platform_module(platform_id: str):
    if platform_id == "windows":
        from . import windows

        return windows
    if platform_id == "macos":
        from . import macos

        return macos
    if platform_id == "linux_x11":
        from . import linux_x11

        return linux_x11
    if platform_id == "linux_wayland":
        from . import linux_wayland

        return linux_wayland
    from .generic import factory as generic

    return generic


def detect(probe: Probe | None = None) -> Capabilities:
    """探测当前环境能力。永不抛异常——探测失败本身也是一种探测结果。"""
    probe = probe or system_probe()
    platform_id = _resolve_platform_id(probe)
    try:
        capabilities = _platform_module(platform_id).detect()
    except Exception:
        logger.exception("能力探测失败，退回通用降级")
        from .generic import factory as generic

        return generic.detect()

    if platform_id == "windows" and not probe.raw_input_registrable:
        capabilities = _degrade_to_fallback_keyboard(capabilities)
    return capabilities


def _degrade_to_fallback_keyboard(capabilities: Capabilities) -> Capabilities:
    """专用键盘后端不可用时降级到通用兜底，并如实标注能力缺口。

    关键是 ``key_position_stable = False``：pynput 拿不到稳定的物理位置码，
    左右 Ctrl / Shift 会合并统计。不标出来，用户只会看到"某天 Shift 用量翻倍"
    这类无从解释的异常（03 文档 §2.8）。
    """
    notice = DegradedNotice(
        code="keyboard_backend_degraded",
        severity="warning",
        title="键盘采集降级为兼容模式",
        detail=(
            "专用后端不可用，已改用通用兜底后端。按键总数仍然准确，"
            "但左右 Ctrl / Shift / Alt 会合并统计，且全屏独占程序内的按键可能收不到。"
        ),
        hint="重启程序可再次尝试专用后端",
    )
    return replace(
        capabilities,
        keyboard_backend="pynput",
        key_position_stable=False,
        degraded=(*capabilities.degraded, notice),
    )


def build(
    environment: Capabilities,
    *,
    app_root: Path,
    options: AdapterOptions | None = None,
) -> AdapterSet:
    """按能力装配适配器集合。失败时退回通用降级，绝不让启动流程崩在这里。

    **只构造，不启动。** 采集后端在这里被创建但不注册任何系统资源——注册发生在
    ``KeyboardSource.start()``，由生命周期在数据库就绪之后调用（02 文档 §5.1 第 10 步）。
    这条区分很重要：``build()`` 必须先于单实例锁（锁本身就来自返回的 AdapterSet），
    而"抢占系统资源"绝不能先于单实例判定。
    """
    options = options or AdapterOptions()
    try:
        return _platform_module(environment.platform_id).build(
            environment, app_root=app_root, options=options
        )
    except Exception:
        logger.exception("适配器装配失败，退回通用降级")
        from .generic import factory as generic

        return generic.build(generic.detect(), app_root=app_root, options=options)


#: 采集能力从"环境允许"收敛为"此刻真能交付"时可能产出的说明。
KEYBOARD_UNAVAILABLE = DegradedNotice(
    code="keyboard_unavailable",
    severity="error",
    title="键盘采集未启动",
    detail=(
        "所有键盘后端都无法注册，本次运行不会记录任何按键。"
        "屏幕时间统计不受影响，仍在正常记录。"
    ),
    hint="常见原因是反作弊驱动、远程会话或安全软件拦截；重启程序可再试一次",
)

FOREGROUND_UNAVAILABLE = DegradedNotice(
    code="foreground_unavailable",
    severity="warning",
    title="无法识别当前应用",
    detail="前台窗口监控未启动，按应用维度的统计不可用；键盘统计不受影响。",
    hint=None,
)


def reconcile(
    capabilities: Capabilities,
    *,
    keyboard: object | None = None,
    foreground_running: bool = False,
    idle_available: bool = False,
    titles_recorded: bool = False,
) -> Capabilities:
    """把有效能力对齐到**采集真正启动之后**的事实（02 文档 §5.1 的能力语义表）。

    ``build()`` 返回的是"环境允许 ∧ 已实现"，而这里加上第三个条件"∧ 已成功启动"。
    ``/api/v1/status`` 与 UI 一律使用这一份——理由是不骗人：键盘后端注册失败后若照旧
    上报 ``keyboard: true``，用户会看到一个永远是 0 的图表却无从解释。

    本函数**不判断平台**，只读端口对象的状态，因此三个平台共用同一段收敛逻辑。
    """
    notices = list(capabilities.degraded)
    running = bool(keyboard is not None and getattr(keyboard, "running", False))
    changes: dict[str, object] = {}

    if not running:
        changes.update(
            keyboard=False,
            keyboard_backend="none",
            keyboard_durations=False,
            key_position_stable=False,
        )
        if capabilities.keyboard:
            _append(notices, KEYBOARD_UNAVAILABLE)
    else:
        active = str(getattr(keyboard, "backend_name", capabilities.keyboard_backend))
        changes["keyboard"] = True
        changes["keyboard_backend"] = active
        if active != capabilities.keyboard_backend:
            # 用了兜底后端：位置码拿不到，左右修饰键与小键盘会合并。
            changes["key_position_stable"] = False
            _append(notices, _fallback_notice(capabilities.keyboard_backend, active))

    if not foreground_running:
        changes.update(foreground=False, window_titles=False)
        if capabilities.foreground:
            _append(notices, FOREGROUND_UNAVAILABLE)
    else:
        changes["window_titles"] = capabilities.window_titles and titles_recorded

    changes["idle"] = capabilities.idle and idle_available
    return replace(capabilities, degraded=tuple(notices), **changes)


def _append(notices: list[DegradedNotice], notice: DegradedNotice) -> None:
    if all(existing.code != notice.code for existing in notices):
        notices.append(notice)


def _fallback_notice(preferred: str, active: str) -> DegradedNotice:
    return DegradedNotice(
        code="keyboard_backend_degraded",
        severity="warning",
        title="键盘采集降级为兼容模式",
        detail=(
            f"首选后端 {preferred} 不可用，已改用 {active}。按键总数仍然准确，"
            "但左右 Ctrl / Shift / Alt 会合并统计，且全屏独占程序内的按键可能收不到。"
        ),
        hint="重启程序可再次尝试首选后端",
    )
