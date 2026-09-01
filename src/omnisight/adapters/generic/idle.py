"""以"最近一次按键时间"近似空闲时长。"""

from __future__ import annotations

import time


class LastInputIdleSource:
    """没有系统级空闲 API 时的近似实现。

    与真正的 ``GetLastInputInfo`` 的差别要记在案：它只看得见**键盘**。用户看视频
    时不断移动鼠标但不打字，这里会判定为空闲。因此使用它的环境上，
    ``Capabilities.idle`` 仍为 True 但精度更低，UI 在设置页说明这一点。
    """

    __slots__ = ("_last_input_mono",)

    def __init__(self) -> None:
        self._last_input_mono = time.monotonic()

    def note_input(self) -> None:
        """由键盘采集在每次按下时调用。"""
        self._last_input_mono = time.monotonic()

    def idle_seconds(self) -> float:
        return max(0.0, time.monotonic() - self._last_input_mono)
