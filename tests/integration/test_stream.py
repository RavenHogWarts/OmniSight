"""SSE 实时推送（05 文档 §7、08 文档 §2）。

替代的是旧版"每秒轮询 + 全量重绘"：TimeLens 每秒 ``fetch`` 两次并重绘两块 canvas，
KeyTrace 每秒重取热力图，而 99% 的响应与上次完全相同。

这里固定四件事：

1. **按键帧只有 ``key_id``**，没有时间戳、没有顺序——抓到这条流也还原不出输入内容；
2. **连接不跨标签页泄漏**：断开即注销（12 文档 M2 的完成判据）；
3. **只有一条广播线程**：让每个连接各自查库就等于把"每秒一次查询"变成"每标签页每秒一次"；
4. ``privacy.realtime_stream = false`` 时端点**不存在**（404），不是 403。
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from omnisight.capture.keyboard import TOPIC_KEY_PRESSED
from omnisight.core.bus import EventBus
from omnisight.presentation.stream import StreamHub, _frame
from omnisight.presentation.web import create_app


@pytest.fixture
def hub(api_context):
    bus = EventBus()
    hub = StreamHub(bus, api_context)
    api_context.stream = hub
    yield hub
    hub.stop()


def _events(frames: list[str]) -> list[tuple[str, dict]]:
    """SSE 帧文本 → ``[(event, payload)]``，注释行（``: ping``）忽略。"""
    parsed: list[tuple[str, dict]] = []
    for frame in frames:
        lines = [line for line in frame.splitlines() if line and not line.startswith(":")]
        if not lines:
            continue
        event = lines[0].removeprefix("event: ")
        payload = json.loads(lines[1].removeprefix("data: "))
        parsed.append((event, payload))
    return parsed


def test_keypress_frames_carry_only_key_ids(hub):
    """没有时间戳、没有顺序、没有内容。窗口内的键去重后**排序**发出。"""
    hub.start()
    stream = hub.stream()
    next(stream)  # ": connected"
    next(stream)  # status
    for key_id in ("key_z", "key_a", "key_a"):
        hub._on_key(TOPIC_KEY_PRESSED, key_id)
    hub._flush_keys()
    event, payload = _events([next(stream)])[0]
    assert event == "keypress"
    assert payload == {"keys": ["key_a", "key_z"]}
    assert set(payload) == {"keys"}, "多出任何字段都要先过一遍隐私审查"
    stream.close()


def test_a_closed_connection_is_unregistered(hub):
    """连接泄漏的症状是"关了标签页 CPU 还在跑"，而且只在多开几次之后才显现。"""
    hub.start()
    assert hub.client_count == 0
    first, second = hub.stream(), hub.stream()
    next(first)
    next(second)
    assert hub.client_count == 2
    first.close()
    assert hub.client_count == 1
    second.close()
    assert hub.client_count == 0


def test_many_sequential_connections_do_not_accumulate(hub):
    """刷新页面 20 次不该留下 20 个订阅者。"""
    hub.start()
    for _ in range(20):
        stream = hub.stream()
        next(stream)
        stream.close()
    assert hub.client_count == 0


def test_a_slow_client_only_drops_its_own_events(hub):
    """有界队列 + 丢最旧：慢客户端不该拖住广播线程，也不该影响别人。"""
    from omnisight.presentation.stream import CLIENT_BACKLOG

    # 不启动广播线程：这条用例要的是队列语义，让线程掺进自己的帧只会让断言变脆。
    slow = hub.stream()
    next(slow)  # ": connected"
    next(slow)  # status
    overflow = CLIENT_BACKLOG * 3
    for index in range(overflow):
        hub._broadcast(_frame("counters", {"presses": index}))
    # 队列有界：积压被裁到上限，且广播过程中不抛异常。
    events = _events([next(slow) for _ in range(CLIENT_BACKLOG)])
    assert len(events) == CLIENT_BACKLOG
    # 丢的是**最旧**的：最后一帧一定还在，第一帧是被裁剩下的那一批的开头。
    assert events[-1] == ("counters", {"presses": overflow - 1})
    assert events[0] == ("counters", {"presses": overflow - CLIENT_BACKLOG})
    slow.close()


def test_the_first_frames_tell_the_client_where_it_stands(hub):
    """连上先给一次 ``status``：否则前端在第一次 ``invalidate`` 之前不知道采集是否在跑。"""
    hub.start()
    stream = hub.stream()
    assert next(stream).startswith(":")
    event, payload = _events([next(stream)])[0]
    assert event == "status"
    assert set(payload) == {"capture", "degraded"}
    stream.close()


def test_invalidate_announces_a_version_not_the_data(hub):
    """推的是"有新数据了"。服务端不猜前端在看哪个周期。"""
    from omnisight.storage.writer import TOPIC_WRITE_FLUSHED

    hub.start()
    stream = hub.stream()
    next(stream)
    next(stream)
    hub._on_flushed(TOPIC_WRITE_FLUSHED, 42)
    hub._broadcast(
        _frame("invalidate", {"data_version": 42, "scopes": ["usage", "keyboard"]})
    )
    event, payload = _events([next(stream)])[0]
    assert event == "invalidate"
    assert payload["data_version"] == 42
    assert payload["scopes"] == ["usage", "keyboard"]
    assert "presses" not in payload, "invalidate 不该夹带数据"
    stream.close()


def test_counters_are_only_sent_when_they_change(hub, seeded):
    """每秒重发同一组数字就是换了个形式的轮询。"""
    hub.start()
    stream = hub.stream()
    next(stream)
    next(stream)
    hub._emit_counters()
    first = hub._last_counters
    assert first is not None
    hub._emit_counters()  # 数据没变
    assert hub._last_counters == first
    stream.close()


def test_broadcast_does_no_work_when_nobody_is_listening(hub, seeded):
    """没人连着就不查库——计数器要查库，没有消费者时那是纯浪费。"""
    hub.start()
    hub._on_key(TOPIC_KEY_PRESSED, "key_a")
    hub._flush_keys()
    assert hub._last_counters is None


def test_the_endpoint_does_not_exist_when_realtime_is_turned_off(api_context, hub):
    """404 而不是 403：用户关掉了这个功能，"这个端点不存在"就是最准确的描述。"""
    config = api_context.config
    api_context.config = replace(config, privacy=replace(config.privacy, realtime_stream=False))
    app = create_app(api_context)
    client = app.test_client()
    client.environ_base["HTTP_X_OMNISIGHT_TOKEN"] = "test-token-value"
    assert client.get("/api/v1/stream").status_code == 404


def test_stopping_the_hub_releases_the_bus_subscriptions(api_context):
    """关闭时不退订，采集线程会一直往一个没人读的队列里推。"""
    bus = EventBus()
    hub = StreamHub(bus, api_context)
    hub.start()
    assert hub._unsubscribe
    hub.stop()
    assert hub._unsubscribe == []
