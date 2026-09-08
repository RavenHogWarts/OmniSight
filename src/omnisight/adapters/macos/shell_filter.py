"""macOS 系统外壳过滤名单（04 文档 §2.2 的第一级过滤，19 文档 §2.6）。

与 Windows 的 :mod:`..windows.shell_filter` 同一条语义：命中的时刻**不产生会话**，
期间的按键归到 ``app_id = 0``（按键总量守恒，04 文档 §2.2）——采集层只看到
``current()`` 返回 ``None``，名单里的东西它一个都不认识。

macOS 的应用身份是 bundle id，因此这份名单的键是 bundle id（小写），
与 ``app_key = casefold(bundleIdentifier)`` 的口径一致。
"""

from __future__ import annotations

#: Dock / 聚焦 / 登录窗 / 控制中心 / 通知中心 / 舞台调度 / 菜单栏右侧。
#: 全部小写；系统组件的 bundle id 大小写不统一，比较前统一 casefold。
SHELL_KEYS: frozenset[str] = frozenset(
    {
        "com.apple.dock",
        "com.apple.spotlight",
        "com.apple.loginwindow",
        "com.apple.controlcenter",
        "com.apple.notificationcenterui",
        "com.apple.windowmanager",
        "com.apple.systemuiserver",
    }
)

__all__ = ["SHELL_KEYS"]
