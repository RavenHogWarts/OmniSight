"""把 Raw Input 适配为 :class:`~omnisight.adapters.ports.KeyboardSource`。

刻意做成**薄封装**：``raw_input.py`` 是已验证的 ctypes 层，``keymap_native.py`` 是
纯函数映射表，本文件只负责把两者接起来并盖上时间戳。三者分开的收益是——真正需要
真实键盘才能测的代码只剩 ``raw_input.py``，另外两个在任何平台上都可测。

**时间戳由本层盖**，而不是上层的采集编排。理由是延迟：这里离硬件事件最近，
``sink`` 之后还要经过归一化、配对、归因、入队若干步。双时钟的分工见 04 文档 §3.3
——单调钟算时长（NTP 校时不影响），墙钟定日期桶。

``needs_main_loop = False``：Windows 上消息泵跑在自己的线程里。macOS 的 event tap
必须挂主线程 runloop，届时那个适配器会返回 ``True``，装配层据此让托盘让出主线程
（02 文档 §3）——这个属性首期恒为 False，但接口现在就留好。
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from ..ports import CaptureUnavailable, RawKeyEvent
from .keymap_native import resolve
from .raw_input import RawInputKeyboardListener

logger = logging.getLogger(__name__)

BACKEND_NAME = "raw_input"


class RawInputKeyboardSource:
    """Windows 一级键盘后端：能捕获全屏独占程序内的按键。"""

    __slots__ = ("_listener", "_on_session_end", "_sink", "_unmapped")

    def __init__(self, *, on_session_end: Callable[[], None] | None = None) -> None:
        self._listener: RawInputKeyboardListener | None = None
        self._sink: Callable[[RawKeyEvent], None] | None = None
        self._on_session_end = on_session_end
        self._unmapped = 0

    @property
    def backend_name(self) -> str:
        return BACKEND_NAME

    @property
    def needs_main_loop(self) -> bool:
        return False

    @property
    def running(self) -> bool:
        return bool(self._listener and self._listener.running)

    @property
    def unmapped_events(self) -> int:
        """收到但无法映射到 ``key_id`` 的原生事件数（媒体键、厂商键、Pause 前缀段）。

        暴露它是为了不让"某个键从来没被记录"变成无声故障：数字异常增长时
        ``/api/v1/status`` 上看得见，可以据此补映射表。
        """
        return self._unmapped

    def start(self, sink: Callable[[RawKeyEvent], None]) -> None:
        if self.running:
            return
        self._sink = sink
        listener = RawInputKeyboardListener(
            self._on_raw, on_session_end=self._on_session_end
        )
        try:
            listener.start()
        except (OSError, RuntimeError) as exc:
            # 不是致命错误：屏幕时间统计与整个程序都应该继续可用（02 文档 §5.1 第 10 步）。
            raise CaptureUnavailable(f"Raw Input 注册失败：{exc}") from exc
        self._listener = listener
        logger.info("键盘采集已启动，后端 %s", BACKEND_NAME)

    def stop(self) -> None:
        listener, self._listener = self._listener, None
        if listener is not None:
            listener.stop()
        self._sink = None

    # ── 回调（运行在消息泵线程上，必须极快）──────────────────────────────
    def _on_raw(self, vk: int, scan: int, flags: int, is_down: bool) -> None:
        key_id, hid_usage, pressed = resolve(vk, scan, flags)
        if key_id is None:
            self._unmapped += 1
            return
        sink = self._sink
        if sink is None:  # pragma: no cover - stop() 与在途消息竞态
            return
        sink(
            RawKeyEvent(
                key_id=key_id,
                pressed=pressed,
                wall_ts_ns=time.time_ns(),
                mono_ts_ns=time.perf_counter_ns(),
                hid_usage=hid_usage,
                native_code=scan,
                native_code2=vk,
            )
        )


__all__ = ["BACKEND_NAME", "RawInputKeyboardSource"]
