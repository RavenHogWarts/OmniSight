"""查询缓存：以 ``data_version`` 为世代号（05 文档 §1.4、§1.6）。

**不做显式失效。** 每个条目记下它是在哪个 ``data_version`` 上算出来的，版本变了就是
未命中。这比"写操作通知缓存清哪些键"简单，且**不可能漏**——漏一次失效的症状是用户改
了别名却看到旧名字，而这种 bug 只在特定顺序下出现，几乎测不出来。

代价是一次写入让全部缓存失效。这在本项目里是对的：写入是"每秒一批"级别的稀疏事件，
而真正需要缓存的是历史周期（它们的 ``data_version`` 早就不再变化）。当前周期本来每次
都要重算，缓存与否无关。

**不缓存响应外壳。** ``generated_at`` / ``is_current`` 依赖墙钟——跨零点时
``is_current`` 会翻转而 ``data_version`` 没变。缓存只存业务数据，外壳每次现拼。
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from collections.abc import Callable
from typing import Any

DEFAULT_MAXSIZE = 256


class QueryCache:
    """带 LRU 淘汰的世代缓存。线程安全：Flask 以多线程模式跑（``threaded=True``）。"""

    __slots__ = ("_entries", "_hits", "_lock", "_maxsize", "_misses")

    def __init__(self, maxsize: int = DEFAULT_MAXSIZE) -> None:
        if maxsize < 1:
            raise ValueError("maxsize 必须为正")
        self._maxsize = maxsize
        self._entries: OrderedDict[Any, tuple[int, Any]] = OrderedDict()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def get_or_compute(self, key: Any, data_version: int, compute: Callable[[], Any]) -> Any:
        """取或算。``compute`` **在锁外执行**——查询可能要几十毫秒，持锁跑它会把
        并发请求串行化，而这正是缓存本该避免的事。代价是同一个键可能被并发算两次
        （结果相同，只浪费一次查询），比互相阻塞划算。"""
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None and entry[0] == data_version:
                self._entries.move_to_end(key)
                self._hits += 1
                return entry[1]
            self._misses += 1
        value = compute()
        with self._lock:
            self._entries[key] = (data_version, value)
            self._entries.move_to_end(key)
            while len(self._entries) > self._maxsize:
                self._entries.popitem(last=False)
        return value

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "size": len(self._entries),
                "hits": self._hits,
                "misses": self._misses,
            }


__all__ = ["DEFAULT_MAXSIZE", "QueryCache"]
