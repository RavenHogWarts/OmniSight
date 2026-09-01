"""Windows 能力探测与适配器装配。

探测与装配分两阶段（02 文档 §5.1）：

* :func:`detect` 回答"**这个操作系统允许我们做什么**"。纯函数、无副作用、永不抛
  异常，结果在建库、日志、状态接口三处使用。
* :func:`build` 回答"**这个版本此刻真能交付什么**"，并申请系统资源。它返回的
  ``AdapterSet.capabilities`` 是环境能力与已实现能力的交集——这才是 UI 该信的
  那一份。M0 阶段采集层尚未实现，因此这里会明确降级并给出说明。
"""

from __future__ import annotations

import ctypes
import logging
import sys
from pathlib import Path

from ..ports import AdapterSet, Capabilities, DegradedNotice
from .autostart import RegistryAutostart
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

    真正的注册失败（被反作弊拦截、会话 0 无桌面）只有在 :func:`build` 时才会
    暴露，届时走降级路径并如实上报（02 文档 §5.1 第 10 步）。
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


def detect() -> Capabilities:
    """环境能力：Windows 上这些 API 对普通进程一律开放，无需授权。"""
    return Capabilities(
        platform_id=PLATFORM_ID,
        tier=TIER,
        os_version=_os_version(),
        keyboard=_has_export("user32", "RegisterRawInputDevices"),
        keyboard_backend="raw_input",
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


#: M0 的诚实交代：骨架已就位，采集层排在 M1。
_CAPTURE_PENDING = DegradedNotice(
    code="capture_not_implemented",
    severity="warning",
    title="采集功能尚未启用",
    detail=(
        "当前版本只包含地基（配置、数据库、托盘、状态接口），"
        "前台应用与键盘采集将在下一个里程碑加入。"
    ),
    hint="现在运行不会产生任何统计数据，也不会记录任何按键",
)


def build(environment: Capabilities, *, app_root: Path) -> AdapterSet:
    """装配 Windows 适配器集合。"""
    notices: list[DegradedNotice] = [_CAPTURE_PENDING]

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

    effective = _effective_capabilities(environment, notices)
    return AdapterSet(
        capabilities=effective,
        instance_lock=NamedMutexInstanceLock(),
        notifier=MessageBoxNotifier(app_root),
        autostart=autostart,
        foreground=None,   # M1
        keyboard=None,     # M1
        idle=None,         # M1
        icons=None,        # M2
    )


def _effective_capabilities(
    environment: Capabilities, notices: list[DegradedNotice]
) -> Capabilities:
    """把"环境允许"收敛为"此刻真能交付"。

    绝不上报尚未接线的能力：UI 依据这份数据决定显示哪些面板，虚报会让用户看到
    一个永远是 0 的图表却无从解释——这正是 03 文档 §2.8 要消除的那类现象。
    """
    from dataclasses import replace

    return replace(
        environment,
        keyboard=False,
        keyboard_backend="none",
        keyboard_durations=False,
        key_position_stable=False,
        foreground=False,
        window_titles=False,
        idle=False,
        icons=False,
        degraded=tuple(notices),
    )
