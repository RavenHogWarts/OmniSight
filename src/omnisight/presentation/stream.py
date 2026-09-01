"""SSE：取代"1 秒轮询 + 全量重绘"（05 文档 §7）。

旧 TimeLens 每秒 ``fetch`` 两次 ``/api/period`` 并重绘整个列表和两块 canvas，旧 KeyTrace
每秒重取热力图。在有一年数据的库上这让 CPU 持续占用，而 99% 的请求返回的数据与上次
完全相同。

**推的是"有新数据了"，不是数据本身**（``invalidate`` 事件）：服务端不猜前端在看哪个
周期，前端按当前视图决定要不要重取。

**隐私约束（08 文档 §2）**：``keypress`` 只发 ``key_id``，**不发时间戳、不发顺序**——
100ms 窗口内的键去重后排序发出，因此即使有人抓到这条流也无法还原输入内容。

**连接不许泄漏**：每个客户端一个有界队列，注册与注销都在生成器的 ``finally`` 里；
慢客户端只会丢自己的事件，不会拖住广播线程。
"""

from __future__ import annotations

import json
import logging
import threading
from collections import deque
from collections.abc import Iterator
from typing import Any

from flask import Flask, Response

from ..capture.foreground import TOPIC_FOREGROUND_CHANGED
from ..capture.keyboard import TOPIC_KEY_PRESSED
from ..storage.writer import TOPIC_WRITE_FLUSHED

logger = logging.getLogger(__name__)

#: 按键合并窗口。100ms 既能让键盘动画看起来是实时的，又足以把连打合成一帧。
KEYPRESS_WINDOW_SECONDS = 0.1
#: 计数器刷新间隔，仅在值变化时才发。
COUNTER_INTERVAL_SECONDS = 1.0
#: ``invalidate`` 节流。落盘每秒都在发生，但前端没必要每秒重取一屏数据。
INVALIDATE_INTERVAL_SECONDS = 5.0
#: 心跳注释。让代理与浏览器不因静默而断开，也让广播线程能发现客户端已经走了。
KEEPALIVE_SECONDS = 15.0
#: 单个客户端积压上限。超出丢最旧——慢客户端不该影响别人（与事件队列同一条原则）。
CLIENT_BACKLOG = 64


class _Client:
    __slots__ = ("_items", "_ready")

    def __init__(self) -> None:
        self._items: deque[str] = deque(maxlen=CLIENT_BACKLOG)
        self._ready = threading.Event()

    def push(self, frame: str) -> None:
        self._items.append(frame)
        self._ready.set()

    def drain(self, timeout: float) -> list[str]:
        if not self._items and not self._ready.wait(timeout):
            return []
        self._ready.clear()
        frames: list[str] = []
        while self._items:
            frames.append(self._items.popleft())
        return frames


def _frame(event: str, payload: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


class StreamHub:
    """订阅事件总线一次，扇出给所有连接。

    只有**一条**广播线程：它做合并、节流与计数器采样。让每个连接各自轮询库会把"每秒一次
    查询"变成"每标签页每秒一次查询"，而这正是要修掉的现状。
    """

    def __init__(self, bus: Any, context: Any) -> None:
        self._bus = bus
        self._context = context
        self._clients: set[_Client] = set()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._pending_keys: set[str] = set()
        self._pending_lock = threading.Lock()
        self._last_counters: dict[str, Any] | None = None
        self._last_data_version = -1
        self._unsubscribe: list[Any] = []

    # ── 生命周期 ────────────────────────────────────────────────────────
    @property
    def client_count(self) -> int:
        with self._lock:
            return len(self._clients)

    def start(self) -> None:
        if self._thread is not None or self._bus is None:
            return
        self._unsubscribe = [
            self._bus.subscribe(TOPIC_KEY_PRESSED, self._on_key),
            self._bus.subscribe(TOPIC_FOREGROUND_CHANGED, self._on_foreground),
            self._bus.subscribe(TOPIC_WRITE_FLUSHED, self._on_flushed),
        ]
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="sse-broadcast", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        for cancel in self._unsubscribe:
            cancel()
        self._unsubscribe = []
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=timeout)
        # 唤醒所有还挂着的生成器，让它们看到 stop 并退出。
        self._broadcast(_frame("bye", {"reason": "shutdown"}))

    # ── 订阅者管理 ──────────────────────────────────────────────────────
    def stream(self) -> Iterator[str]:
        """一个客户端的 SSE 帧序列。注销放在 ``finally`` 里，断开即释放。"""
        client = _Client()
        with self._lock:
            self._clients.add(client)
        try:
            yield ": connected\n\n"
            yield _frame("status", self._status_payload())
            while not self._stop.is_set():
                frames = client.drain(KEEPALIVE_SECONDS)
                if frames:
                    yield from frames
                else:
                    # 心跳：客户端已关闭时这一次写入会抛，生成器随即被回收。
                    yield ": ping\n\n"
        finally:
            with self._lock:
                self._clients.discard(client)

    def _broadcast(self, frame: str) -> None:
        with self._lock:
            clients = list(self._clients)
        for client in clients:
            client.push(frame)

    # ── 总线回调（在采集线程上执行，必须极快）─────────────────────────────
    def _on_key(self, _topic: str, key_id: Any) -> None:
        with self._pending_lock:
            self._pending_keys.add(str(key_id))

    def _on_foreground(self, _topic: str, app_id: Any) -> None:
        try:
            name = self._context.services.apps.lens().name(int(app_id))
        except Exception:  # pragma: no cover - 前台推送不值得让采集线程出错
            name = "未知"
        self._broadcast(_frame("foreground", {"app_id": int(app_id), "display_name": name}))

    def _on_flushed(self, _topic: str, data_version: Any) -> None:
        # 只记下"有新版本"，节流与广播交给广播线程——这里跑在写线程上。
        with self._pending_lock:
            self._last_data_version = max(self._last_data_version, int(data_version or 0))

    # ── 广播线程 ────────────────────────────────────────────────────────
    def _loop(self) -> None:
        last_counters = 0.0
        last_invalidate = 0.0
        announced_version = -1
        while not self._stop.wait(KEYPRESS_WINDOW_SECONDS):
            now = _monotonic()
            if self.client_count == 0:
                # 没人连着就什么都不算：计数器要查库，没有消费者时那是纯浪费。
                self._flush_keys()
                continue
            self._flush_keys()
            if now - last_counters >= COUNTER_INTERVAL_SECONDS:
                last_counters = now
                self._emit_counters()
            if now - last_invalidate >= INVALIDATE_INTERVAL_SECONDS:
                with self._pending_lock:
                    version = self._last_data_version
                if version > announced_version:
                    announced_version = version
                    last_invalidate = now
                    self._broadcast(
                        _frame(
                            "invalidate",
                            {"data_version": version, "scopes": ["usage", "keyboard"]},
                        )
                    )

    def _flush_keys(self) -> None:
        with self._pending_lock:
            if not self._pending_keys:
                return
            keys = sorted(self._pending_keys)
            self._pending_keys.clear()
        if self.client_count == 0:
            return
        # 去重 + 排序：窗口内的**顺序**不外传，这是隐私承诺的一部分（08 文档 §2）。
        self._broadcast(_frame("keypress", {"keys": keys}))

    def _emit_counters(self) -> None:
        try:
            payload = self._counters_payload()
        except Exception:  # pragma: no cover - 一次查询失败不该断开连接
            logger.debug("计算实时计数失败", exc_info=True)
            return
        if payload == self._last_counters:
            return
        self._last_counters = payload
        self._broadcast(_frame("counters", payload))

    def _counters_payload(self) -> dict[str, Any]:
        services = self._context.services
        period = services.context.resolve_period(_today_request())
        keyboard = services.keyboard.summary(period)
        screen = services.usage.screen_time(period)
        return {
            "presses": keyboard["total_presses"],
            "seconds": screen["total_seconds"],
            "kpm": keyboard["kpm_peak"],
            "data_version": services.context.data_version(),
        }

    def _status_payload(self) -> dict[str, Any]:
        from .api.system import build_status

        status = build_status(self._context)
        return {"capture": status["capture"], "degraded": status["degraded"]}


def _monotonic() -> float:
    import time

    return time.monotonic()


def _today_request():
    from ..services.period import PeriodRequest

    return PeriodRequest("day")


def register(app: Flask, context: Any) -> None:
    """挂上 ``/api/v1/stream``。

    ``privacy.realtime_stream = false`` 时返回 404 而不是 403：用户关掉了这个功能，
    "这个端点不存在"就是最准确的描述，也不给探测留信息（05 文档 §7）。
    """
    hub: StreamHub = context.stream
    if hub is not None:
        hub.start()

    @app.get("/api/v1/stream")
    def stream():
        if not context.config.privacy.realtime_stream or hub is None:
            from werkzeug.exceptions import NotFound

            raise NotFound(description="实时推送已关闭")
        response = Response(hub.stream(), mimetype="text/event-stream")
        response.headers["Cache-Control"] = "no-store"
        # 关掉代理缓冲，否则事件会被攒着一起发，实时性荡然无存。
        response.headers["X-Accel-Buffering"] = "no"
        response.headers["Connection"] = "keep-alive"
        return response


__all__ = [
    "CLIENT_BACKLOG",
    "COUNTER_INTERVAL_SECONDS",
    "INVALIDATE_INTERVAL_SECONDS",
    "KEEPALIVE_SECONDS",
    "KEYPRESS_WINDOW_SECONDS",
    "StreamHub",
    "register",
]
