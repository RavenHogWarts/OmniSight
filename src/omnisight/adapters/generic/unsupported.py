"""明确抛错的占位实现：能力缺失时**报错好于假装成功**。"""

from __future__ import annotations

from ..ports import AppIdentity, UnsupportedOperation


class UnsupportedAutostart:
    """无法自动配置开机自启的环境。

    ``is_enabled()`` 返回 False 而不抛异常——调用方（托盘菜单、设置接口）需要
    显示当前状态，让读操作抛异常会迫使每个调用点写 try/except。写操作则必须
    抛异常：静默失败会让用户以为已经设置好了。
    """

    def is_enabled(self) -> bool:
        return False

    def set_enabled(self, enabled: bool) -> None:
        raise UnsupportedOperation(
            "当前环境不支持自动配置开机自启，请按所用系统的方式手动添加启动项"
        )


class UnsupportedIconSource:
    """无法提取应用图标；前端退化为首字母色块。"""

    def icon_png(self, identity: AppIdentity, size: int) -> bytes | None:
        return None
