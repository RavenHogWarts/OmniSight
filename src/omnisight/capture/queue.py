"""采集线程与写入线程之间的有界队列（02 文档 §3.2、04 文档 §5）。

设计文档在两处给了不同的形状（04 §5.1 是 ``queue.Queue(8192)`` + 丢最新，
02 §3.2 是 ``deque(maxlen=50000)`` + 丢最旧）。实现取后者，理由：

* ``deque.append`` 在满时静默淘汰，**永不抛异常也永不阻塞**。``queue.Queue`` 的
  ``put_nowait`` 在满时抛 ``queue.Full``——在磁盘卡死的场景下，热路径上每个按键都要
  构造一次异常对象，恰好是最不该增加开销的时刻。
* 50 000 条按 20 键/秒算是 40 分钟缓冲，内存约 2 MB。8192 条只有约 7 分钟。多出来的
  缓冲几乎免费，而它换来的是"外部备份工具锁住数据库半小时"这类情况下零丢失。
* 丢最旧而非最新：队列见底意味着写线程已经落后很久，此时用户最可能正在看仪表盘并
  期待"我刚敲的键计数涨了"。丢掉刚发生的事比丢掉半小时前的更让人困惑。

无论丢哪一头，**丢弃必须可见**：计数经 ``/api/v1/status`` 的 ``dropped_events``
暴露，并写入 ``health_stat``。静默丢弃会让用户在不知情的情况下得到错误统计。
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from collections.abc import Iterable

from .models import KeyEvent, UsageSession

logger = logging.getLogger(__name__)

QUEUE_MAXSIZE = 50_000

Event = KeyEvent | UsageSession


class EventQueue:
    """线程安全的有界队列。生产者永不阻塞，消费者可带超时等待。"""

    __slots__ = ("_dropped_pending", "_dropped_total", "_items", "_maxsize", "_not_empty")

    def __init__(self, maxsize: int = QUEUE_MAXSIZE) -> None:
        if maxsize < 1:
            raise ValueError("maxsize 必须为正")
        self._items: deque[Event] = deque()
        self._maxsize = maxsize
        self._not_empty = threading.Condition(threading.Lock())
        # 累计值给状态接口看（永不清零），待记值给写入线程记进 health_stat 后清零。
        self._dropped_total = 0
        self._dropped_pending = 0

    # ── 生产者侧（采集线程）───────────────────────────────────────────────
    def put(self, event: Event) -> bool:
        """入队。返回 ``False`` 表示为了腾位置淘汰了一条旧事件。

        锁的持有时间是一次 ``append`` + 一次 ``notify``，微秒级；这与"每次按键去竞争
        一把被 1 秒轮询线程持有的锁"不是一回事（后者才是 Coordinator 拒绝用锁的原因）。
        """
        dropped = False
        with self._not_empty:
            if len(self._items) >= self._maxsize:
                self._items.popleft()
                self._dropped_total += 1
                self._dropped_pending += 1
                dropped = True
            self._items.append(event)
            self._not_empty.notify()
        if dropped and self._dropped_total % 1000 == 1:
            # 每千条报一次：磁盘卡死时不该让日志本身变成新的 IO 压力源。
            logger.error("事件队列已满，已累计丢弃 %s 条事件", self._dropped_total)
        return not dropped

    # ── 消费者侧（写入线程）───────────────────────────────────────────────
    def drain(self, max_items: int, timeout: float) -> list[Event]:
        """取出至多 ``max_items`` 条。队列空时最多等 ``timeout`` 秒，超时返回空列表。"""
        with self._not_empty:
            if not self._items:
                self._not_empty.wait(timeout)
            if not self._items:
                return []
            count = min(max_items, len(self._items))
            return [self._items.popleft() for _ in range(count)]

    def drain_all(self) -> list[Event]:
        """停机时一次取空，不等待。"""
        with self._not_empty:
            items = list(self._items)
            self._items.clear()
            return items

    def put_back(self, events: Iterable[Event]) -> None:
        """写失败时把整批放回队首，保持时间顺序，下一轮重试。

        放回而不是丢弃，是因为写失败的常见原因（备份工具短暂锁库）是可恢复的。
        若队列已满，放回同样会触发淘汰计数——不会无声膨胀。
        """
        with self._not_empty:
            for event in reversed(list(events)):
                if len(self._items) >= self._maxsize:
                    self._dropped_total += 1
                    self._dropped_pending += 1
                    continue
                self._items.appendleft(event)
            self._not_empty.notify()

    def wake(self) -> None:
        """唤醒等待中的消费者（停机时用，避免多等一个 timeout）。"""
        with self._not_empty:
            self._not_empty.notify_all()

    # ── 观测 ────────────────────────────────────────────────────────────
    @property
    def depth(self) -> int:
        with self._not_empty:
            return len(self._items)

    @property
    def dropped(self) -> int:
        """自启动以来累计丢弃数，供 ``/api/v1/status`` 展示。"""
        return self._dropped_total

    def take_dropped(self) -> int:
        """取出并清零丢弃计数，交给写入线程记进 ``health_stat``。"""
        with self._not_empty:
            dropped, self._dropped_pending = self._dropped_pending, 0
            return dropped


__all__ = ["QUEUE_MAXSIZE", "Event", "EventQueue"]
