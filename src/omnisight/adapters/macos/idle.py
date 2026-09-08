"""macOS 空闲判定（``IdleSource`` 的 macOS 实现，19 文档 §2.1）。

``CGEventSourceSecondsSinceLastEventType(HIDSystemState, kCGAnyInputEventType)``：
看得见鼠标、触控板与键盘——与 Windows 的 ``GetLastInputInfo`` 同档，比 generic
那个"只看最近一次按键"的近似诚实得多（那个会把"只动鼠标不敲键"判成空闲）。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class MacIdleSource:
    """实现 :class:`~omnisight.adapters.ports.IdleSource`。绝不抛异常。"""

    __slots__ = ()

    def idle_seconds(self) -> float:
        try:
            from Quartz import (
                CGEventSourceSecondsSinceLastEventType,
                kCGAnyInputEventType,
            )

            # kCGEventSourceStateHIDSystemState = 1（0 是合成会话状态）。
            return float(max(0.0, CGEventSourceSecondsSinceLastEventType(1, kCGAnyInputEventType)))
        except Exception:
            # 取不到就当作"刚刚有输入"：反过来（当作空闲）会错误截断会话。
            logger.debug("空闲判定不可用", exc_info=True)
            return 0.0


__all__ = ["MacIdleSource"]
