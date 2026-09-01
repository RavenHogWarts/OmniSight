"""查询缓存的世代语义（05 文档 §1.6）。

要固定的不是"缓存能命中"，而是**它不可能给出过期结果**：条目带着算出它时的
``data_version``，版本一变就是未命中。显式失效方案的失败模式（漏通知 → 用户改了别名
却看到旧名字）在这种结构下不存在，而这正是选它的理由。
"""

from __future__ import annotations

import threading

import pytest

from omnisight.services.cache import QueryCache


def test_same_version_hits_and_does_not_recompute():
    cache = QueryCache()
    calls = []

    def compute():
        calls.append(1)
        return "值"

    assert cache.get_or_compute("k", 7, compute) == "值"
    assert cache.get_or_compute("k", 7, compute) == "值"
    assert len(calls) == 1
    assert cache.stats()["hits"] == 1


def test_a_new_data_version_invalidates_without_anyone_notifying_the_cache():
    """写入侧不认识缓存。这是"漏一次失效"变成不可能的原因。"""
    cache = QueryCache()
    assert cache.get_or_compute("k", 1, lambda: "旧") == "旧"
    assert cache.get_or_compute("k", 2, lambda: "新") == "新"
    assert cache.get_or_compute("k", 2, lambda: "不该被调用") == "新"


def test_stale_version_never_wins_even_if_it_arrives_later():
    """并发下老版本的计算可能后完成。它会覆盖条目，但下一次请求带着新版本仍然重算。"""
    cache = QueryCache()
    cache.get_or_compute("k", 2, lambda: "新")
    cache.get_or_compute("k", 1, lambda: "旧")
    assert cache.get_or_compute("k", 2, lambda: "重算") == "重算"


def test_lru_eviction_keeps_the_most_recently_used():
    cache = QueryCache(maxsize=2)
    cache.get_or_compute("a", 1, lambda: "A")
    cache.get_or_compute("b", 1, lambda: "B")
    cache.get_or_compute("a", 1, lambda: "不该被调用")  # a 变成最近使用
    cache.get_or_compute("c", 1, lambda: "C")  # 淘汰 b
    assert cache.stats()["size"] == 2
    assert cache.get_or_compute("a", 1, lambda: "不该被调用") == "A"  # 仍在
    assert cache.get_or_compute("b", 1, lambda: "B2") == "B2"  # 已被淘汰，重算


def test_compute_runs_outside_the_lock():
    """持锁跑查询会把并发请求串行化——那正是缓存本该避免的事。

    做法：在 ``compute`` 内部再进一次缓存。如果锁还被持着，这里会死锁而不是通过。
    """
    cache = QueryCache()

    def outer():
        return cache.get_or_compute("inner", 1, lambda: "内层")

    assert cache.get_or_compute("outer", 1, outer) == "内层"


def test_concurrent_readers_all_get_a_value():
    cache = QueryCache()
    results: list[str] = []
    barrier = threading.Barrier(4)

    def worker():
        barrier.wait()
        results.append(cache.get_or_compute("k", 1, lambda: "值"))

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert results == ["值"] * 4


def test_maxsize_must_be_positive():
    with pytest.raises(ValueError):
        QueryCache(maxsize=0)
