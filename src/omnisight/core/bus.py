"""进程内事件总线：采集侧发布、SSE 与托盘订阅。

刻意做得很小：没有通配符、没有优先级、没有异步。它唯一的职责是让"按键落地"
与"页面收到通知"解耦，而 SSE 的实际扇出在 05 文档 §7 里另有节流逻辑。

订阅者回调中的异常**不允许**冒泡到发布者——发布者往往是采集热路径，一个坏掉的
订阅者不该让采集停摆。
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

Listener = Callable[[str, Any], None]


class EventBus:
    __slots__ = ("_listeners", "_lock")

    def __init__(self) -> None:
        self._listeners: dict[str, list[Listener]] = {}
        self._lock = threading.Lock()

    def subscribe(self, topic: str, listener: Listener) -> Callable[[], None]:
        """订阅并返回取消订阅的可调用对象。"""
        with self._lock:
            self._listeners.setdefault(topic, []).append(listener)

        def unsubscribe() -> None:
            with self._lock:
                handlers = self._listeners.get(topic)
                if handlers and listener in handlers:
                    handlers.remove(listener)

        return unsubscribe

    def publish(self, topic: str, payload: Any = None) -> None:
        with self._lock:
            handlers = list(self._listeners.get(topic, ()))
        for handler in handlers:
            try:
                handler(topic, payload)
            except Exception:
                logger.exception("事件订阅者处理 %s 时抛出异常，已忽略", topic)

    def topics(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(self._listeners)
