"""pynput 通用兜底键盘后端（04 文档 §3.1 的最后一行）。

**这是兜底，不是主后端。** 它只在两种情况下被启用：当前平台没有专用适配器，或专用
后端注册失败（Raw Input 被反作弊拦截、会话 0 无桌面等，见 R1）。

它有一条**结构性**的能力缺陷，比"全屏独占程序可能收不到"更硬：pynput 拿不到物理
位置码，只给字符或平台虚拟键。因此

* 左右 Shift / Ctrl / Alt 会合并统计；
* 小键盘数字与主键盘数字会合并；
* ``Shift+1`` 报的字符是 ``!``，只能按 ANSI 布局反推回 ``digit1``。

启用它时 ``Capabilities.key_position_stable`` 必须为 ``False``，``capture_capability``
会把这一位记进当天的行——否则日后看到"某天 Shift 用量突然翻倍"将无从解释
（03 文档 §2.8）。

**按需导入**：``import pynput`` 会在部分平台注册全局钩子相关的依赖，Windows 发布版
虽然内置它（12 文档 §5 的决定："完全没有数据"比"多一个可疑模块"更糟），但只要
Raw Input 正常就永远不会加载（08 文档 §8）。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from ..ports import CaptureUnavailable, RawKeyEvent

logger = logging.getLogger(__name__)

BACKEND_NAME = "pynput"

#: pynput ``Key.<name>`` → ``key_id``。左右不分的名字（``shift``、``ctrl``、``alt``）
#: 一律归到左键——必须选一个，而"左"是绝大多数键盘上更常用的那个。这个合并正是
#: ``key_position_stable = False`` 所描述的损失。
NAME_TO_KEY_ID: dict[str, str] = {
    "alt": "alt_left", "alt_l": "alt_left", "alt_r": "alt_right", "alt_gr": "alt_right",
    "backspace": "backspace", "caps_lock": "caps_lock",
    "cmd": "win_left", "cmd_l": "win_left", "cmd_r": "win_right",
    "ctrl": "control_left", "ctrl_l": "control_left", "ctrl_r": "control_right",
    "delete": "delete", "down": "arrow_down", "end": "end", "enter": "enter",
    "esc": "esc", "home": "home", "insert": "insert", "left": "arrow_left",
    "menu": "menu", "num_lock": "num_lock", "page_down": "page_down",
    "page_up": "page_up", "pause": "pause", "print_screen": "print_screen",
    "right": "arrow_right", "scroll_lock": "scroll_lock",
    "shift": "shift_left", "shift_l": "shift_left", "shift_r": "shift_right",
    "space": "space", "tab": "tab", "up": "arrow_up",
    **{f"f{index}": f"f{index}" for index in range(1, 25)},
}

#: 字符 → ``key_id``，按 ANSI 布局反推物理键。同一物理键的上下档都指向它，这样
#: ``Shift+1`` 与 ``1`` 落在同一个格子里（否则热力图会多出一堆符号键）。
_UNSHIFTED = r"`1234567890-=[]\;',./"
_SHIFTED = '~!@#$%^&*()_+{}|:"<>?'
_CHAR_SLOTS = (
    "grave", "digit1", "digit2", "digit3", "digit4", "digit5", "digit6", "digit7",
    "digit8", "digit9", "digit0", "minus", "equal", "bracket_left", "bracket_right",
    "backslash", "semicolon", "quote", "comma", "period", "slash",
)

CHAR_TO_KEY_ID: dict[str, str] = {
    **{chr(ord("a") + index): f"key_{chr(ord('a') + index)}" for index in range(26)},
    **{chr(ord("A") + index): f"key_{chr(ord('a') + index)}" for index in range(26)},
    **dict(zip(_UNSHIFTED, _CHAR_SLOTS, strict=True)),
    **dict(zip(_SHIFTED, _CHAR_SLOTS, strict=True)),
    "\t": "tab", "\r": "enter", "\n": "enter", " ": "space", "\x1b": "esc",
    "\x08": "backspace",
}

#: 仅在既无 ``name`` 又无 ``char`` 时才查：Windows 小键盘的虚拟键。
#: 有 ``char`` 时不查，避免在其他平台上与该平台自己的 vk 编号撞车。
#:
#: 与上面两张表同为「原生 → key_id」的映射表，因此同样公开：键位可达性测试要对
#: **所有**平台的所有表求并集（11 文档 §3.1），漏掉一张就等于放过一批永远为 0 的键。
NUMPAD_VK: dict[int, str] = {
    **{0x60 + index: f"numpad_{index}" for index in range(10)},
    0x6A: "numpad_multiply", 0x6B: "numpad_add", 0x6D: "numpad_subtract",
    0x6E: "numpad_decimal", 0x6F: "numpad_divide",
}


def key_id_for(key: Any) -> str | None:
    """pynput 的按键对象 → ``key_id``；无法识别时返回 ``None``。

    纯函数、不导入 pynput，因此可以用鸭子类型的假对象在任何平台上测试。
    """
    name = getattr(key, "name", None)
    if isinstance(name, str):
        mapped = NAME_TO_KEY_ID.get(name)
        if mapped:
            return mapped
    char = getattr(key, "char", None)
    if isinstance(char, str) and char:
        mapped = CHAR_TO_KEY_ID.get(char)
        if mapped:
            return mapped
        return CHAR_TO_KEY_ID.get(char.lower())
    vk = getattr(key, "vk", None)
    if isinstance(vk, int):
        return NUMPAD_VK.get(vk)
    return None


class PynputKeyboardSource:
    """实现 :class:`~omnisight.adapters.ports.KeyboardSource` 的兜底后端。

    ``idle_notifier`` 让通用空闲源能被按键喂到（generic 环境没有系统级空闲 API）。
    它在采集热路径上被调用，因此必须是一次赋值级别的操作。
    """

    __slots__ = ("_idle_notifier", "_listener", "_sink", "_unmapped")

    def __init__(self, *, idle_notifier: Callable[[], None] | None = None) -> None:
        self._listener: Any | None = None
        self._sink: Callable[[RawKeyEvent], None] | None = None
        self._idle_notifier = idle_notifier
        self._unmapped = 0

    @property
    def backend_name(self) -> str:
        return BACKEND_NAME

    @property
    def needs_main_loop(self) -> bool:
        # pynput 自己起线程；macOS 上它内部也会处理 runloop，无需我们让出主线程。
        return False

    @property
    def running(self) -> bool:
        listener = self._listener
        return bool(listener is not None and listener.is_alive())

    @property
    def unmapped_events(self) -> int:
        return self._unmapped

    def start(self, sink: Callable[[RawKeyEvent], None]) -> None:
        if self.running:
            return
        try:
            from pynput import keyboard
        except Exception as exc:  # ImportError 或平台后端初始化失败
            raise CaptureUnavailable(
                f"通用兜底后端不可用（未安装 pynput 或当前环境不支持）：{exc}"
            ) from exc
        self._sink = sink
        listener = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
        try:
            listener.start()
            listener.wait()
        except Exception as exc:
            self._sink = None
            raise CaptureUnavailable(f"通用兜底后端启动失败：{exc}") from exc
        self._listener = listener
        logger.warning("键盘采集已降级到兜底后端 %s：左右修饰键与小键盘无法区分", BACKEND_NAME)

    def stop(self) -> None:
        listener, self._listener = self._listener, None
        if listener is not None:
            listener.stop()
            join = getattr(listener, "join", None)
            if join is not None:
                join(timeout=2)
        self._sink = None

    # ── 回调 ────────────────────────────────────────────────────────────
    def _on_press(self, key: Any) -> None:
        self._emit(key, pressed=True)

    def _on_release(self, key: Any) -> None:
        self._emit(key, pressed=False)

    def _emit(self, key: Any, *, pressed: bool) -> None:
        import time

        key_id = key_id_for(key)
        if key_id is None:
            self._unmapped += 1
            return
        if pressed and self._idle_notifier is not None:
            self._idle_notifier()
        sink = self._sink
        if sink is None:  # pragma: no cover - stop() 与在途回调竞态
            return
        sink(
            RawKeyEvent(
                key_id=key_id,
                pressed=pressed,
                wall_ts_ns=time.time_ns(),
                mono_ts_ns=time.perf_counter_ns(),
                # 位置码无从取得，这正是 key_position_stable = False 的含义。
                hid_usage=None,
                native_code=None,
                native_code2=getattr(key, "vk", None) if isinstance(
                    getattr(key, "vk", None), int
                ) else None,
            )
        )


__all__ = [
    "BACKEND_NAME",
    "CHAR_TO_KEY_ID",
    "NAME_TO_KEY_ID",
    "NUMPAD_VK",
    "PynputKeyboardSource",
    "key_id_for",
]
