"""可注入的时间源（11 文档 §2）。

墙钟与单调钟必须分开注入：按压时长用单调钟算、时间戳用墙钟存。测试要能独立
控制两者，才能验证"改系统时间不影响已测出的时长"这类回归。
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, tzinfo
from typing import Protocol, runtime_checkable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime:
        """带本地时区的当前时间。"""

    def time_ns(self) -> int:
        """Unix 纪元纳秒（墙钟，可被 NTP 回拨）。"""

    def monotonic_ns(self) -> int:
        """单调纳秒，仅用于测量间隔。"""


class SystemClock:
    """生产实现。``tz`` 为 None 时用系统本地时区。"""

    __slots__ = ("_tz",)

    def __init__(self, tz: tzinfo | None = None) -> None:
        self._tz = tz

    def now(self) -> datetime:
        return datetime.now(self._tz) if self._tz else datetime.now().astimezone()

    def time_ns(self) -> int:
        return time.time_ns()

    def monotonic_ns(self) -> int:
        return time.perf_counter_ns()


def resolve_timezone(configured: str | None) -> tzinfo:
    """显式配置优先，否则用系统时区（03 文档 §3.2）。

    KeyTrace 现状把 ``Asia/Shanghai`` 硬编码在源码里，对非中国用户直接算错日期桶。
    配置项 ``ui.timezone`` 接受 IANA 名称；解析不出来时**不静默回退**，让调用方
    决定是报错还是降级——静默回退会让用户以为设置生效了。
    """
    if configured:
        return ZoneInfo(configured)
    local = datetime.now().astimezone().tzinfo
    return local if local is not None else UTC


def timezone_label(tz: tzinfo) -> str:
    """写入 ``meta.timezone`` 的诊断字符串。

    Windows 的系统时区给不出 IANA 名称（拿到的是"中国标准时间"这类本地化名），
    因此附上 UTC 偏移——日后要解释"这个日期桶按哪个时区算的"时，偏移比名字有用。
    """
    if isinstance(tz, ZoneInfo):
        return str(tz)
    now = datetime.now(tz)
    offset = now.utcoffset() or UTC.utcoffset(now)
    minutes = int(offset.total_seconds() // 60) if offset else 0
    sign = "+" if minutes >= 0 else "-"
    name = tz.tzname(now) or "local"
    return f"{name} (UTC{sign}{abs(minutes) // 60:02d}:{abs(minutes) % 60:02d})"


__all__ = ["Clock", "SystemClock", "ZoneInfoNotFoundError", "resolve_timezone", "timezone_label"]
