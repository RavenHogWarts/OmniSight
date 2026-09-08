"""macOS 启动期错误告知（``Notifier`` 的 macOS 实现，19 文档 §2.1）。

``NSAlert`` 的 ``runModal`` 必须在主线程；启动早期的错误路径恰好就在主线程上
（``_fail_startup`` 在 ``start()`` 的调用栈里），成立。其余一切交给
:class:`~omnisight.adapters.generic.notifier.FileNotifier`（含 ``clear()``，
A1 之后它是每个新 Notifier 的最低标准）：无 GUI 会话时兜底的是文件。
"""

from __future__ import annotations

import logging
import threading

from ..generic.notifier import FileNotifier

logger = logging.getLogger(__name__)


class MacNotifier(FileNotifier):
    """NSAlert + 文件兜底。API 与语义完全继承 FileNotifier。"""

    __slots__ = ()

    def error(self, title: str, message: str) -> None:
        super().error(title, message)
        if threading.current_thread() is not threading.main_thread():
            # NSAlert 离开主线程行为未定义；文件那份已经写了，别在这里翻车。
            logger.warning("非主线程调用错误通知，跳过弹窗：%s", title)
            return
        try:
            self._alert(title, message)
        except Exception:  # pragma: no cover - 弹窗失败不该掩盖原始错误
            logger.debug("NSAlert 弹窗失败", exc_info=True)

    def _alert(self, title: str, message: str) -> None:
        from AppKit import NSAlert, NSApp

        NSApp()
        alert = NSAlert.alloc().init()
        alert.setMessageText_(title)
        alert.setInformativeText_(message)
        alert.addButtonWithTitle_("好")
        alert.runModal()


__all__ = ["MacNotifier"]
