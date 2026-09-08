"""macOS 键盘采集：CGEventTap（19 文档 §2.3/§2.4 / 20 文档 B6）。

四个坑的全套处置（每一个都会造成"看起来在工作但数据是错的"）：

1. **修饰键只有 FlagsChanged**：方向由"flags 位 × 该 keycode 的上一状态"合成
   （:mod:`.keymap_native` 的 ``resolve``，偏离 155 的解法），左右靠 keycode 区分。
   启动时刻的初始 flags 由 ``CGEventSourceFlagsState`` 取一次做基线——用户按着
   Shift 启动时，第一次事件不会被误读成"抬起"。
2. **``kCGEventTapDisabledByTimeout``**：回调太慢时系统停掉 tap 且**不报错**。
   必须识别它、重新启用、并把次数暴露到 ``tap_disabled_count``（经
   ``KeyboardCapture.snapshot()`` 进 ``/api/v1/status``）——"用了半小时之后按键
   统计静默停止"才可诊断（R16）。
3. **回调在输入路径上**：只查表、盖时间戳、入队，微秒级。
4. **主线程 runloop**：``needs_main_loop = True``。``start()`` 把 tap 挂到**主**
   runloop（``kCFRunLoopCommonModes``）后立即返回；主线程由装配层的
   ``_run_foreground`` 分派交给 :meth:`run_main_loop`（``CFRunLoopRun``）驱动，
   托盘退到子线程（02 文档 §3、A2）。若托盘在子线程初始化失败（R23），那也只是
   没有菜单栏图标——按键照收，方向上宁可丢托盘不丢数据。
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

from ..ports import CaptureUnavailable, RawKeyEvent
from . import keymap_native
from .permissions import INPUT_MONITORING

logger = logging.getLogger(__name__)

BACKEND_NAME = "event_tap"

#: 事件类型与掩码（Quartz 常量写死，模块保持无 pyobjc 导入即可被任何平台收集）。
_KEY_DOWN = keymap_native.EVENT_KEY_DOWN
_KEY_UP = keymap_native.EVENT_KEY_UP
_FLAGS_CHANGED = keymap_native.EVENT_FLAGS_CHANGED
_TAP_DISABLED_BY_TIMEOUT = 0xFFFFFFE5


def _modifier_keycodes() -> dict[int, int]:
    """keycode → flags 位（``MODIFIER_MASK_BY_KEYCODE`` 的浅拷贝，方向一致）。"""
    return dict(keymap_native.MODIFIER_MASK_BY_KEYCODE)


class EventTapKeyboardSource:
    """实现 :class:`~omnisight.adapters.ports.KeyboardSource`（macOS event tap）。"""

    __slots__ = (
        "_held",
        "_looping",
        "_on_session_end",
        "_sink",
        "_source",
        "_tap",
        "_tap_disabled",
        "_unmapped",
    )

    def __init__(self, *, on_session_end: Callable[[], None] | None = None) -> None:
        self._on_session_end = on_session_end
        self._sink: Callable[[RawKeyEvent], None] | None = None
        self._tap = None
        self._source = None
        self._looping = threading.Event()
        self._held: set[int] = set()
        self._unmapped = 0
        self._tap_disabled = 0

    # ── KeyboardSource 协议 ─────────────────────────────────────────────
    @property
    def backend_name(self) -> str:
        return BACKEND_NAME

    @property
    def running(self) -> bool:
        return self._tap is not None

    @property
    def needs_main_loop(self) -> bool:
        return True

    @property
    def unmapped_events(self) -> int:
        """不在映射表里的键（媒体键、JIS 专用键、Fn）——丢失它们才是无声故障。"""
        return self._unmapped

    @property
    def tap_disabled_count(self) -> int:
        """tap 被系统因回调超时禁用的次数。持续增长 = 系统繁忙，不是采集 bug。"""
        return self._tap_disabled

    def start(self, sink: Callable[[RawKeyEvent], None]) -> None:
        """创建 tap 并挂到**主** runloop（不阻塞——主循环由 ``run_main_loop`` 驱动）。

        失败抛 :class:`CaptureUnavailable`：最常见的两种是「输入监控」未授权
        （``CGEventTapCreate`` 返回 NULL）与无 GUI 会话。
        """
        if self.running:
            return
        from Quartz import (
            CGEventMaskBit,
            CGEventSourceFlagsState,
            CGEventTapCreate,
            kCGEventTapOptionListenOnly,
            kCGHeadInsertEventTap,
            kCGSessionEventTap,
        )

        self._sink = sink
        self._held = set()
        baseline_flags = 0
        try:
            # kCGEventSourceStateHIDSystemState = 1：硬件真实状态（0 是合成会话状态）。
            baseline_flags = int(CGEventSourceFlagsState(1))
        except Exception:  # pragma: no cover - 非常规会话
            baseline_flags = 0
        for keycode, mask in _modifier_keycodes().items():
            if baseline_flags & mask:
                self._held.add(keycode)

        mask = (
            CGEventMaskBit(_KEY_DOWN) | CGEventMaskBit(_KEY_UP) | CGEventMaskBit(_FLAGS_CHANGED)
        )
        self._tap = CGEventTapCreate(
            kCGSessionEventTap,
            kCGHeadInsertEventTap,
            kCGEventTapOptionListenOnly,
            mask,
            self._on_event,
            None,
        )
        if self._tap is None:
            raise CaptureUnavailable(
                "CGEventTapCreate 失败：最常见的原因是「输入监控」未授权"
                f"（{INPUT_MONITORING}），其次是锁屏/无 GUI 会话"
            )

        from CoreFoundation import (
            CFMachPortCreateRunLoopSource,
            CFRunLoopAddSource,
            CFRunLoopGetMain,
            kCFRunLoopCommonModes,
        )

        self._source = CFMachPortCreateRunLoopSource(None, self._tap, 0)
        CFRunLoopAddSource(CFRunLoopGetMain(), self._source, kCFRunLoopCommonModes)
        logger.info("event tap 已挂到主 runloop（初始修饰键按住 %d 个）", len(self._held))

    def run_main_loop(self) -> None:
        """阻塞调用线程（按契约是主线程）直到 :meth:`stop`。"""
        if not self.running:
            return
        self._looping.set()
        try:
            from CoreFoundation import CFRunLoopRun

            CFRunLoopRun()
        finally:
            self._looping.clear()

    def stop(self) -> None:
        tap, source = self._tap, self._source
        self._tap = None
        self._source = None
        if tap is None:
            return
        try:
            from CoreFoundation import (
                CFMachPortInvalidate,
                CFRunLoopGetMain,
                CFRunLoopRemoveSource,
                CFRunLoopStop,
                kCFRunLoopCommonModes,
            )
            from Quartz import CGEventTapEnable

            CGEventTapEnable(tap, False)
            if source is not None:
                CFRunLoopRemoveSource(CFRunLoopGetMain(), source, kCFRunLoopCommonModes)
            CFMachPortInvalidate(tap)
            CFRunLoopStop(CFRunLoopGetMain())
        except Exception:  # pragma: no cover - 停机路径不许抛
            logger.debug("event tap 停止时出错", exc_info=True)
        if self._on_session_end is not None:
            try:
                self._on_session_end()
            except Exception:  # pragma: no cover
                logger.exception("会话结束回调失败")

    # ── 热路径（在输入路径上，微秒级）──────────────────────────────────
    def _on_event(self, _proxy, event_type: int, event, _refcon):
        try:
            self._dispatch(event_type, event)
        except Exception:  # pragma: no cover - 回调抛异常会连累整个输入会话
            logger.exception("event tap 回调失败")
        return event

    def _dispatch(self, event_type: int, event) -> None:
        from Quartz import CGEventGetFlags, CGEventGetIntegerValueField, kCGKeyboardEventKeycode

        if event_type == _TAP_DISABLED_BY_TIMEOUT:
            from Quartz import CGEventTapEnable

            self._tap_disabled += 1
            CGEventTapEnable(self._tap, True)
            logger.warning("event tap 被系统禁用（第 %d 次），已重新启用", self._tap_disabled)
            return

        keycode = int(CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode))
        flags = int(CGEventGetFlags(event))
        key_id, hid_usage, pressed = keymap_native.resolve(
            keycode, event_type, flags, previous_held=keycode in self._held
        )
        if event_type == _FLAGS_CHANGED:
            (self._held.add if pressed else self._held.discard)(keycode)
        if key_id is None:
            self._unmapped += 1
            return
        sink = self._sink
        if sink is not None:
            sink(
                RawKeyEvent(
                    key_id=key_id,
                    pressed=pressed,
                    wall_ts_ns=time.time_ns(),
                    mono_ts_ns=time.monotonic_ns(),
                    hid_usage=hid_usage,
                    native_code=keycode,
                    native_code2=event_type,
                )
            )


__all__ = ["BACKEND_NAME", "EventTapKeyboardSource"]
