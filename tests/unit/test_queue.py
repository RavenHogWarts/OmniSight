"""有界事件队列（02 文档 §3.2、04 文档 §5）。

这里盯的是两条**产品级**约束，而不是队列本身的数据结构：

1. **生产者永不阻塞、永不抛异常。** 它跑在按键热路径上（Windows 上就是 Raw Input
   的消息泵线程），一次阻塞就是一次可感知的输入延迟。
2. **丢弃永远可见。** 静默丢弃会让用户在不知情的情况下拿到错误统计，比明确报"丢了
   1200 条"糟得多。累计计数供状态接口、待记计数进 ``health_stat``，两者不能混用——
   混用过一次：``take_dropped()`` 把状态接口的计数也清零了，于是"丢过事件"这个事实
   在下一次刷新页面时就消失了。
"""

from __future__ import annotations

import threading

import pytest

from omnisight.capture.models import KeyEvent
from omnisight.capture.queue import QUEUE_MAXSIZE, EventQueue


def _event(index: int) -> KeyEvent:
    return KeyEvent(
        key_id="key_a", down_ts_ns=index, up_ts_ns=index + 1, duration_ms=1.0
    )


def test_default_size_is_the_documented_one():
    """50 000 条 ≈ 20 键/秒下 40 分钟缓冲，改小它等于缩短"备份工具锁库"的容忍窗口。"""
    assert QUEUE_MAXSIZE == 50_000
    assert EventQueue().depth == 0


def test_maxsize_must_be_positive():
    with pytest.raises(ValueError):
        EventQueue(maxsize=0)


def test_put_and_drain_preserve_order():
    queue = EventQueue()
    for index in range(5):
        assert queue.put(_event(index)) is True
    drained = queue.drain(10, timeout=0.0)
    assert [event.down_ts_ns for event in drained] == [0, 1, 2, 3, 4]
    assert queue.depth == 0


def test_drain_respects_max_items():
    queue = EventQueue()
    for index in range(10):
        queue.put(_event(index))
    assert len(queue.drain(4, timeout=0.0)) == 4
    assert queue.depth == 6


def test_full_queue_drops_the_oldest_and_never_raises():
    """丢最旧：队列见底意味着写线程已落后很久，此时用户最关心的是刚敲的键。"""
    queue = EventQueue(maxsize=3)
    for index in range(3):
        assert queue.put(_event(index)) is True
    assert queue.put(_event(3)) is False  # 返回 False = 淘汰了一条
    assert [event.down_ts_ns for event in queue.drain(10, timeout=0.0)] == [1, 2, 3]


def test_dropped_total_is_never_reset_but_pending_is():
    """两个计数各有归属，共用一个会让"丢过事件"这个事实在页面刷新后消失。"""
    queue = EventQueue(maxsize=1)
    for index in range(4):
        queue.put(_event(index))
    assert queue.dropped == 3
    assert queue.take_dropped() == 3
    assert queue.take_dropped() == 0, "待记计数取走后应清零"
    assert queue.dropped == 3, "累计计数不许被清零——状态接口靠它"


def test_drain_all_empties_without_waiting():
    queue = EventQueue()
    for index in range(3):
        queue.put(_event(index))
    assert len(queue.drain_all()) == 3
    assert queue.drain_all() == []


def test_put_back_restores_order_at_the_head():
    """写失败时整批放回队首，下一轮重试。顺序错了会让跨小时切片算到错的桶。"""
    queue = EventQueue()
    batch = [_event(index) for index in range(3)]
    queue.put(_event(99))
    queue.put_back(batch)
    assert [event.down_ts_ns for event in queue.drain(10, timeout=0.0)] == [0, 1, 2, 99]


def test_put_back_into_a_full_queue_counts_drops_instead_of_growing():
    """否则一次写失败就能让队列无声突破上限，把内存吃到 OOM。"""
    queue = EventQueue(maxsize=2)
    queue.put(_event(0))
    queue.put(_event(1))
    queue.put_back([_event(7), _event(8), _event(9)])
    assert queue.depth == 2
    assert queue.dropped == 3


def test_drain_returns_empty_after_timeout_rather_than_blocking_forever():
    queue = EventQueue()
    assert queue.drain(10, timeout=0.01) == []


def test_drain_wakes_up_when_an_event_arrives():
    """写线程平时阻塞在这里；醒不过来意味着数据要多等一个 batch 窗口才落盘。"""
    queue = EventQueue()
    drained: list = []

    def consume() -> None:
        drained.extend(queue.drain(10, timeout=2.0))

    consumer = threading.Thread(target=consume)
    consumer.start()
    queue.put(_event(1))
    consumer.join(timeout=2.0)
    assert not consumer.is_alive()
    assert len(drained) == 1


def test_wake_releases_a_waiting_consumer():
    """停机时用：不唤醒的话要多等一整个 timeout 才能退出。"""
    queue = EventQueue()
    finished = threading.Event()

    def consume() -> None:
        queue.drain(10, timeout=5.0)
        finished.set()

    threading.Thread(target=consume, daemon=True).start()
    queue.wake()
    assert finished.wait(timeout=2.0), "wake() 没能唤醒等待中的消费者"


def test_producer_never_blocks_even_when_massively_over_capacity():
    queue = EventQueue(maxsize=10)
    for index in range(1000):
        queue.put(_event(index))
    assert queue.depth == 10
    assert queue.dropped == 990
