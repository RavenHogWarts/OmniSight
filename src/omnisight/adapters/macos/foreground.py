"""macOS 前台应用探测（``ForegroundSource`` 的 macOS 实现，19 文档 §2.1 / 20 文档 B4）。

macOS 的应用身份是 **bundle id**：``app_key = casefold(bundleIdentifier)``、
``identity_kind = "bundle"``、``process_name`` 填 ``localizedName`` 供分类兜底
（A3 的 bundle 精确表按 ``identity_kind`` 命中）。``exe_path`` 记 ``.app`` 包路径
（**不是**包内可执行文件）——图标要按包路径取（``NSWorkspace.iconForFile``）。

窗口标题：默认关闭（08 文档 §2.1 的默认不因平台改变）。开启时走 AXAPI
（``AXUIElementCopyAttributeValue``），那需要「辅助功能」授权——拿不到就返回
空标题，不抛异常：授权与否是用户的选择，不是错误。

"这是一个真的前台应用"的判据：``activationPolicy == Regular``（后台代理与无窗口
进程不是用户眼里的"正在使用"）。Windows 版靠窗口标题判空，macOS 没有那条路
（拿标题就要授权），改用 policy——文档 B4 预告的正是这个替换。
"""

from __future__ import annotations

import logging

from ..ports import AppIdentity, ForegroundInfo
from .shell_filter import SHELL_KEYS

logger = logging.getLogger(__name__)

#: NSApplicationActivationPolicyRegular 的值（AppKit 常量，写死避免模块级导入）。
_REGULAR_POLICY = 0


class MacForegroundSource:
    """实现 :class:`~omnisight.adapters.ports.ForegroundSource`。

    无状态（轮询由 :class:`~omnisight.capture.foreground.ForegroundMonitor` 的
    线程驱动），与 Windows 版同一个契约：**绝不抛异常**——调用方是每秒一次的
    轮询循环。
    """

    __slots__ = ("titles_enabled",)

    def __init__(self, *, titles_enabled: bool = False) -> None:
        self.titles_enabled = titles_enabled

    def current(self) -> ForegroundInfo | None:
        try:
            return self._probe()
        except Exception:
            logger.debug("前台探测失败", exc_info=True)
            return None

    def _probe(self) -> ForegroundInfo | None:
        from AppKit import NSWorkspace

        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        if app is None:
            return None
        bundle_id = str(app.bundleIdentifier() or "")
        if not bundle_id:
            return None
        if bundle_id.casefold() in SHELL_KEYS:
            # Dock / 聚焦 / 登录窗：不产生会话，按键归 app_id = 0。
            return None
        if app.activationPolicy() != _REGULAR_POLICY:
            return None
        name = str(app.localizedName() or bundle_id)
        # .app 包路径（图标按它取）；取不到时为空串，图标层自会降级。
        bundle_path = ""
        url = app.bundleURL()
        if url is not None:
            bundle_path = str(url.path() or "")
        return ForegroundInfo(
            identity=AppIdentity(
                app_key=bundle_id.casefold(),
                identity_kind="bundle",
                display_name=name,
                process_name=name,
                exe_path=bundle_path,
            ),
            window_title=self._focused_title() if self.titles_enabled else "",
        )

    def _focused_title(self) -> str:
        """聚焦窗口标题（AXAPI，需「辅助功能」授权）。拿不到就是空串，绝不抛。"""
        try:
            from ApplicationServices import (
                AXFocusedApplication,
                AXUIElementCopyAttributeValue,
                kAXFocusedWindowAttribute,
                kAXTitleAttribute,
            )

            app = AXUIElementCopyAttributeValue(AXFocusedApplication(), kAXFocusedWindowAttribute)
            if app is None:
                return ""
            title = AXUIElementCopyAttributeValue(app, kAXTitleAttribute)
            return str(title) if title else ""
        except Exception:
            # 授权被拒时 AX 调用返回错误码而不是抛异常，这里兜住真正的异常形态
            # （框架缺失等）。标题是可选维度，任何失败都按"无标题"处理。
            logger.debug("窗口标题不可用（辅助功能授权或 AXAPI）", exc_info=True)
            return ""

    def list_running(self) -> list[AppIdentity]:
        """拥有可见窗口的应用（``activationPolicy == Regular``），按名称排序去重。"""
        try:
            from AppKit import NSWorkspace

            seen: dict[str, AppIdentity] = {}
            for app in NSWorkspace.sharedWorkspace().runningApplications():
                if app.activationPolicy() != _REGULAR_POLICY:
                    continue
                bundle_id = str(app.bundleIdentifier() or "")
                if not bundle_id or bundle_id.casefold() in SHELL_KEYS:
                    continue
                name = str(app.localizedName() or bundle_id)
                seen.setdefault(
                    bundle_id.casefold(),
                    AppIdentity(
                        app_key=bundle_id.casefold(),
                        identity_kind="bundle",
                        display_name=name,
                        process_name=name,
                    ),
                )
            return [seen[key] for key in sorted(seen)]
        except Exception:
            logger.debug("枚举运行中应用失败", exc_info=True)
            return []


__all__ = ["MacForegroundSource"]
