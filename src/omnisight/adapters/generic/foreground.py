"""恒返回 None 的前台源：没有应用归因，但键盘统计照常。"""

from __future__ import annotations

from ..ports import AppIdentity, ForegroundInfo


class NullForegroundSource:
    """应用归因不可用时的实现。

    刻意**不抛异常**：调用方是 1 秒一次的轮询循环，抛异常会把"这个环境没有这项
    能力"变成每秒一条错误日志。返回 None 与"当前没有前台窗口"是同一语义，
    调用方本来就必须处理。
    """

    def current(self) -> ForegroundInfo | None:
        return None

    def list_running(self) -> list[AppIdentity]:
        return []
