"""归因中枢——**合并的技术核心**（02 文档 §4.3、04 文档 §4）。

它做的事一句话说完：前台监控线程每秒写一个 ``(app_id, since_monotonic)`` 元组，
键盘采集线程在每次抬起时读它。这一个内存引用取代了旧方案的"HTTP 调另一个进程取全部
历史区间 → 区间合并 → 按月分组 → 扫描原始事件表求交"。

**为什么不能用锁。** 读发生在 Raw Input 的消息泵线程上，每次按键一次。如果每次按键
都要竞争一把被 1 秒轮询线程周期性持有的锁，最坏情况下按键处理会被阻塞，用户能直接
感觉到输入延迟。而无锁读取的代价仅仅是可能读到"上一个轮询周期"的值——这个误差已经
由 ``confidence="boundary"`` 如实表达了，不是需要用锁消除的问题。

**无锁为什么安全。** CPython 里单个对象引用的赋值与读取是原子的（受 GIL 保护），
读者不会看到半个元组。这是本设计成立的前提；若将来迁到无 GIL 的 Python，需改用锁或
不可变快照 + atomic 语义重新评估。这条前提写在这里，是因为它是**唯一**会让本文件
静默出错的假设。
"""

from __future__ import annotations

import time
from collections.abc import Callable

from ..adapters.ports import UNKNOWN_APP_ID
from .models import Attribution

#: 未知前台时的归因，模块级常量避免热路径上反复构造。
UNKNOWN = Attribution(app_id=UNKNOWN_APP_ID, confidence="unknown")


class CaptureCoordinator:
    """前台状态的唯一持有者。读写都不加锁，见模块注释。"""

    __slots__ = ("_boundary_window_s", "_current", "_idle", "_monotonic")

    def __init__(
        self,
        *,
        boundary_window_seconds: float = 1.0,
        monotonic: Callable[[], float] | None = None,
    ) -> None:
        #: ``(app_id, since_monotonic)``；元组整体替换，因此读者永不见撕裂值。
        self._current: tuple[int, float] | None = None
        self._idle = False
        self._boundary_window_s = boundary_window_seconds
        self._monotonic = monotonic or time.monotonic

    # ── 写：前台监控线程，约 1 次/秒 ──────────────────────────────────────
    def set_foreground(self, app_id: int | None) -> None:
        """更新当前前台应用。``None`` 或 ``0`` 表示无前台/被排除/系统外壳。"""
        if not app_id:
            self._current = None
            return
        current = self._current
        if current is not None and current[0] == app_id:
            # 同一个应用继续在前台：**不刷新时间戳**，否则每次轮询都会把它重新算作
            # "刚切过来"，所有按键都会被标成 boundary。
            return
        self._current = (app_id, self._monotonic())

    def set_idle(self, idle: bool) -> None:
        self._idle = idle

    def clear(self) -> None:
        """停止采集时调用。之后的按键归到未知，而不是归给一个已结束的会话。"""
        self._current = None
        self._idle = False

    # ── 读：键盘采集线程，每次抬起一次 ────────────────────────────────────
    def attribution(self) -> Attribution:
        current = self._current  # 单次读取，无锁
        if current is None:
            return UNKNOWN
        app_id, since = current
        # 切换后一个轮询周期内的按键可能属于任一方，标出来让严格分析可以排除。
        fresh = (self._monotonic() - since) < self._boundary_window_s
        return Attribution(app_id=app_id, confidence="boundary" if fresh else "high")

    @property
    def current_app_id(self) -> int:
        current = self._current
        return current[0] if current is not None else UNKNOWN_APP_ID

    @property
    def idle(self) -> bool:
        """空闲标志。

        注意**按键本身就是输入**——一旦有按键就不可能真的空闲。因此这个标志不用于
        丢弃按键，只用于让前台监控知道该截断会话（04 文档 §4.4）。
        """
        return self._idle


__all__ = ["UNKNOWN", "CaptureCoordinator"]
