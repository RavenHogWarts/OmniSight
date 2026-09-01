"""时长与数字格式化——**服务端唯一真源**（← TimeLens ``web_app.py:_format_duration``）。

格式化放在后端而不是前端，是 07 文档 §10 的决定：TimeLens 现状在 Python 与 JS 各写
一份，两份的边界处理不同（"59 秒"在一处显示 "0分钟"）。后端算好 ``*_formatted``
字段下发，前端只负责显示。

**取舍**：这让接口多了几个冗余字段（``seconds`` 与 ``seconds_formatted`` 并存）。
接受这个冗余，因为它换掉的是"同一个数字在两个地方长得不一样"这类无法自动发现的缺陷。
i18n 到来时（M7）这里是唯一要改的地方。
"""

from __future__ import annotations


def format_duration(seconds: float) -> str:
    """人类可读时长。**边界沿用现状**：0 → ``0秒``，59.9 → ``59秒``，60 → ``1分钟``。

    刻意不做"1小时0分钟"这种补零：整点时长省略后半段更好读，而这正是旧实现的行为，
    改掉会让老用户觉得数字变了。
    """
    if seconds <= 0:
        return "0秒"
    if seconds < 60:
        return f"{int(seconds)}秒"
    minutes = int(seconds // 60)
    if minutes < 60:
        return f"{minutes}分钟"
    hours, mins = divmod(minutes, 60)
    return f"{hours}小时" if mins == 0 else f"{hours}小时{mins}分钟"


def format_count(value: float) -> str:
    """千分位。按键数动辄六位，不分组读不出量级。"""
    return f"{int(value):,}"


def percent(part: float, whole: float, digits: int = 1) -> float:
    """百分比。**分母为 0 时返回 0**——这条路径只该存在一处。

    旧代码在四处各写了一遍 ``x / total * 100 if total else 0``，其中两处漏了保护，
    空库首屏因此会 500（11 文档 §4.3 专门固定了"空库不 500"）。
    """
    if not whole:
        return 0.0
    return round(part / whole * 100, digits)


def delta(current: float, previous: float) -> dict[str, float]:
    """与上一周期的差值。

    ``percent`` 在上期为 0 时返回 0 而不是无穷——"从 0 涨到 100"没有百分比可言，
    前端应该显示绝对值。方向由符号表达，**不做价值判断**：屏幕时间上升不一定是坏事
    （06 文档 §5.1 因此规定箭头不用红绿）。
    """
    difference = current - previous
    return {
        "value": round(difference, 1),
        "percent": round(difference / previous * 100, 1) if previous else 0.0,
    }


def ratio_per_minute(count: float, duration_ms: float) -> float:
    """KPM：每前台分钟的按键数。分母是**前台时长**，不含空闲与无前台时段。

    分母口径必须在 UI 上说明（12 文档 M4 的完成判据），因为"每分钟 56 键"取决于
    分母是"在线时长"还是"该应用前台时长"，两者能差好几倍。
    """
    minutes = duration_ms / 60_000
    if minutes <= 0:
        return 0.0
    return round(count / minutes, 1)


def average(total: float, count: float, digits: int = 1) -> float:
    return round(total / count, digits) if count else 0.0


def percentile(values: list[float], fraction: float) -> float:
    """最近秩百分位。用于热力图的 ``scale.p95``。

    **为什么需要它**：旧实现用最大值归一，而空格键往往是第二名的 3 倍，于是其余键被
    压成一片浅色，热力图读不出差异（06 文档 §7）。p95 归一 + 超出者饱和解决这一点。
    列表通常只有一百来个元素，直接排序即可，不引入 numpy。
    """
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    index = min(len(ordered) - 1, max(0, round(fraction * (len(ordered) - 1))))
    return float(ordered[index])


__all__ = [
    "average",
    "delta",
    "format_count",
    "format_duration",
    "percent",
    "percentile",
    "ratio_per_minute",
]
