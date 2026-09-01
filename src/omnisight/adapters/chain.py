"""按顺序尝试多个键盘后端，直到有一个能起来（04 文档 §3.1、R1）。

**为什么降级不能发生在构造期。** 04 文档 §3.1 的示意代码在 ``__init__`` 里 try/except，
但真正的失败（Raw Input 被反作弊拦截、会话 0 里没有桌面、event tap 被 TCC 拒绝）只在
``start()`` 注册系统资源时才暴露；构造一个对象是不会失败的。因此链在 ``start()`` 上做，
而不是在工厂里做。

**为什么这一层是平台无关的。** 它只认识 ``KeyboardSource`` 端口与 ``CaptureUnavailable``，
不认识 Raw Input 也不认识 pynput。谁排在谁前面由各平台的工厂决定——那才是知道
"本平台最强后端是什么"的地方。

降级后 ``backend_name`` 变成实际生效的那个，装配层据此重算有效能力并产出一条
:class:`DegradedNotice`。**静默降级是不可接受的**：用户会以为游戏里的按键被记录了，
而实际上没有。
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence

from .ports import CaptureUnavailable, KeyboardSource, RawKeyEvent

logger = logging.getLogger(__name__)


class ChainedKeyboardSource:
    """把若干 :class:`KeyboardSource` 串成"能起哪个用哪个"。"""

    __slots__ = ("_active", "_candidates", "_failures")

    def __init__(self, candidates: Sequence[KeyboardSource]) -> None:
        if not candidates:
            raise ValueError("至少需要一个候选后端")
        self._candidates = tuple(candidates)
        self._active: KeyboardSource | None = None
        self._failures: list[str] = []

    @property
    def preferred_backend(self) -> str:
        """首选后端的名字，用于判断最终是否发生了降级。"""
        return self._candidates[0].backend_name

    @property
    def backend_name(self) -> str:
        active = self._active
        return active.backend_name if active is not None else self.preferred_backend

    @property
    def needs_main_loop(self) -> bool:
        active = self._active
        return bool(active.needs_main_loop) if active is not None else False

    @property
    def running(self) -> bool:
        active = self._active
        return bool(active is not None and active.running)

    @property
    def unmapped_events(self) -> int:
        active = self._active
        return int(getattr(active, "unmapped_events", 0)) if active is not None else 0

    @property
    def failures(self) -> tuple[str, ...]:
        """每个失败候选的原因，进日志与状态接口，便于回答"为什么降级了"。"""
        return tuple(self._failures)

    def start(self, sink: Callable[[RawKeyEvent], None]) -> None:
        if self.running:
            return
        self._failures = []
        for candidate in self._candidates:
            try:
                candidate.start(sink)
            except CaptureUnavailable as exc:
                self._failures.append(f"{candidate.backend_name}: {exc}")
                logger.warning("键盘后端 %s 不可用：%s", candidate.backend_name, exc)
                continue
            except Exception as exc:  # 后端里的意外错误同样不该让程序起不来
                self._failures.append(f"{candidate.backend_name}: {exc}")
                logger.exception("键盘后端 %s 启动时抛出意外异常", candidate.backend_name)
                continue
            self._active = candidate
            return
        raise CaptureUnavailable("所有键盘后端都无法启动：" + "；".join(self._failures))

    def stop(self) -> None:
        active, self._active = self._active, None
        if active is not None:
            active.stop()


__all__ = ["ChainedKeyboardSource"]
