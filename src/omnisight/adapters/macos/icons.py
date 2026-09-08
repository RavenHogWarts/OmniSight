"""macOS 应用图标提取（``IconSource`` 的 macOS 实现，19 文档 §2.1）。

``NSWorkspace.iconForFile_`` 接受 **.app 包路径**（不是包内可执行文件）——
所以 :class:`.foreground.MacForegroundSource` 把 ``exe_path`` 记成包路径。
PNG 编码用 ``NSBitmapImageRep`` 原生完成，不依赖 Pillow；缓存与失败重试都在
上层（``app_icon`` 表），适配器只做"给身份，还一张 PNG"这一件事。
"""

from __future__ import annotations

import logging

from ..ports import AppIdentity

logger = logging.getLogger(__name__)


class MacIconSource:
    """实现 :class:`~omnisight.adapters.ports.IconSource`。绝不抛异常。"""

    __slots__ = ()

    def icon_png(self, identity: AppIdentity, size: int) -> bytes | None:
        try:
            return self._render(identity, size)
        except Exception:
            logger.debug("图标提取失败：%s", identity.app_key, exc_info=True)
            return None

    def _render(self, identity: AppIdentity, size: int) -> bytes | None:
        path = identity.exe_path
        if not path:
            return None
        from AppKit import (
            NSBitmapImageRep,
            NSPNGFileType,
            NSWorkspace,
        )

        icon = NSWorkspace.sharedWorkspace().iconForFile_(path)
        if icon is None:
            return None
        icon.setSize_((size, size))
        tiff = icon.TIFFRepresentation()
        if tiff is None:
            return None
        reps = NSBitmapImageRep.imageRepsWithData_(tiff)
        if reps is None or not reps:
            return None
        data = reps[0].representationUsingType_property_(NSPNGFileType, None)
        return bytes(data) if data is not None else None


__all__ = ["MacIconSource"]
