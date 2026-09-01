"""周期计算：合并 TimeLens 的 ``_period_date_range`` 与 KeyTrace 的 ``period``（05 文档 §1.2）。

两个旧项目对"周"的定义不同——TimeLens 是"锚点往前 7 天"，KeyTrace 是自然周。合并必须
统一，这里取**自然周**，起始日由 ``ui.week_starts_on`` 决定（默认周一）。

理由不是"ISO 更标准"，而是翻页语义：往前 7 天得到的区间与原区间不相邻也不对齐，
"上一周"这个按钮因此没有稳定含义；自然周可以无歧义地前后翻。副作用是老 TimeLens
用户会发现"周"视图的数字变了，这一点要在迁移提示里说明（05 文档 §1.2）。

**未来日期一律截断到今天**，且响应里同时给出 ``end`` 与 ``truncated_end``——只给截断后
的值，前端就无法区分"这一周还没过完"和"这一周只有三天有数据"。

``total`` 的展开需要"哪些天有数据"这个**存储事实**，所以展开发生在服务层
（:func:`resolve` 收一个 ``data_range`` 参数），而不是像 05 文档 §9 的示例那样
发生在 ``presentation/validators.py`` 里。表现层只负责校验参数**语法**。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

RANGES: tuple[str, ...] = ("day", "week", "month", "year", "total", "custom")

#: 趋势图的桶粒度由后端决定，前端不需要这套映射（05 文档 §2）。
GRANULARITY: dict[str, str] = {
    "day": "hour",
    "week": "day",
    "month": "day",
    "year": "month",
    "total": "year",
    "custom": "day",
}

#: 自定义区间上限 3 年。上限存在的理由是"一次请求能算完"，不是数据库装不下。
MAX_CUSTOM_SPAN_DAYS = 1096

_WEEKDAY_NAMES = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")


@dataclass(frozen=True, slots=True)
class PeriodRequest:
    """已通过**语法**校验、但还没展开成具体日期的周期请求。

    表现层产出它，服务层展开它。分成两步是因为 ``total`` 要知道数据的起止日期，
    而"查库"不是表现层该做的事。
    """

    range: str
    anchor: date | None = None
    start: date | None = None
    end: date | None = None

    def cache_key(self) -> tuple:
        return (self.range, self.anchor, self.start, self.end)


@dataclass(frozen=True, slots=True)
class Period:
    range: str
    anchor: date
    start: date
    #: 自然结束日（本周日、本月末……），可能在未来。
    end: date
    #: 截断到今天之后的真实结束日。查询一律用它。
    truncated_end: date
    granularity: str
    is_current: bool
    label: str

    @property
    def days(self) -> int:
        """区间内的天数（含首尾）。日均值的分母。"""
        return (self.truncated_end - self.start).days + 1

    @property
    def start_day(self) -> str:
        return self.start.isoformat()

    @property
    def end_day(self) -> str:
        return self.truncated_end.isoformat()

    @property
    def day_range(self) -> tuple[str, str]:
        """``BETWEEN ? AND ?`` 用的闭区间。"""
        return (self.start_day, self.end_day)

    @property
    def is_single_day(self) -> bool:
        return self.start == self.truncated_end

    def to_dict(self) -> dict[str, object]:
        return {
            "range": self.range,
            "anchor": self.anchor.isoformat(),
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "truncated_end": self.truncated_end.isoformat(),
            "label": self.label,
            "is_current": self.is_current,
            "days": self.days,
            "granularity": self.granularity,
        }


def week_start(day: date, week_starts_on: int) -> date:
    """含 ``day`` 的自然周的第一天。``week_starts_on`` 0 = 周一，6 = 周日。"""
    offset = (day.weekday() - week_starts_on) % 7
    return day - timedelta(days=offset)


def month_start(day: date) -> date:
    return day.replace(day=1)


def month_end(day: date) -> date:
    """闰年与年末都靠"下个月 1 号往回退一天"处理，不做除法判断。"""
    if day.month == 12:
        return day.replace(month=12, day=31)
    return day.replace(month=day.month + 1, day=1) - timedelta(days=1)


def _label(range_name: str, start: date, end: date) -> str:
    if range_name == "total":
        return "全部"
    if range_name == "day":
        return f"{start.month}月{start.day}日 {_WEEKDAY_NAMES[start.weekday()]}"
    if range_name == "month":
        return f"{start.year}年{start.month}月"
    if range_name == "year":
        return f"{start.year}年"
    same_year = start.year == end.year
    left = f"{start.month}月{start.day}日"
    right = f"{end.month}月{end.day}日" if same_year else f"{end.year}年{end.month}月{end.day}日"
    return f"{left} - {right}"


def resolve(
    request: PeriodRequest,
    *,
    today: date,
    week_starts_on: int = 0,
    data_range: tuple[date | None, date | None] = (None, None),
) -> Period:
    """把请求展开成具体日期区间。

    ``data_range`` 只在 ``range=total`` 时用到：起点取"有数据的第一天"，没有数据时
    退化成今天当天（空库必须返回结构完整的空数据，不能 500——11 文档 §4.3）。
    """
    anchor = request.anchor or today
    if request.range == "custom":
        start = request.start or anchor
        end = request.end or anchor
    elif request.range == "day":
        start = end = anchor
    elif request.range == "week":
        start = week_start(anchor, week_starts_on)
        end = start + timedelta(days=6)
    elif request.range == "month":
        start, end = month_start(anchor), month_end(anchor)
    elif request.range == "year":
        start, end = date(anchor.year, 1, 1), date(anchor.year, 12, 31)
    elif request.range == "total":
        first, last = data_range
        start = first or today
        end = max(last or today, today)
    else:  # pragma: no cover - 取值范围由 validators 保证
        raise ValueError(f"未知的 range：{request.range!r}")

    truncated = min(end, today)
    if truncated < start:
        # 请求了一个完全在未来的区间。不报错——用户点"下一周"翻过头是正常操作——
        # 但把它压成空区间，让所有查询自然返回 0 行。
        truncated = start
    return Period(
        range=request.range,
        anchor=anchor,
        start=start,
        end=end,
        truncated_end=truncated,
        granularity=GRANULARITY[request.range],
        is_current=start <= today <= end,
        label=_label(request.range, start, end),
    )


def previous(period: Period, *, today: date, week_starts_on: int = 0) -> Period | None:
    """上一个同粒度周期，供 ``delta_vs_previous`` 使用。``total`` 没有上一周期。

    **同比必须与本期同粒度、同长度**，否则"比上期多 12.9%"这句话没有意义。月与年
    用锚点回退（自然月长度不同），日/周/自定义用天数平移。
    """
    if period.range == "total":
        return None
    if period.range == "month":
        anchor = month_start(period.start) - timedelta(days=1)
    elif period.range == "year":
        anchor = date(period.start.year - 1, 1, 1)
    elif period.range == "custom":
        span = (period.end - period.start).days + 1
        request = PeriodRequest(
            "custom",
            start=period.start - timedelta(days=span),
            end=period.start - timedelta(days=1),
        )
        return resolve(request, today=today, week_starts_on=week_starts_on)
    else:
        span = (period.end - period.start).days + 1
        anchor = period.start - timedelta(days=span)
    return resolve(
        PeriodRequest(period.range, anchor=anchor), today=today, week_starts_on=week_starts_on
    )


def buckets(period: Period) -> list[tuple[str, str]]:
    """趋势图的 ``(bucket, label)`` 序列，**含没有数据的桶**。

    缺口必须由后端补齐：前端拿到一串不连续的桶只能自己推断"是没数据还是没这一天"，
    而那正是后端已经知道的事。
    """
    return buckets_for(period.granularity, period.start, period.truncated_end)


def buckets_for(grain: str, start: date, end: date) -> list[tuple[str, str]]:
    """给定粒度的桶序列。

    **粒度是显式参数，不从 :class:`Period` 里推。** ``/keyboard/timeline`` 的月/年视图
    用一个 ``custom`` 区间表达"最近 12 个月"，而 ``custom`` 的 ``granularity`` 恒为
    ``day``——从周期里推粒度会生成一串日期桶去匹配月度数据，于是整个视图静默变成全 0。
    """
    if grain == "hour":
        return [(f"{hour:02d}", f"{hour}:00") for hour in range(24)]
    if grain == "day":
        days: list[tuple[str, str]] = []
        cursor = start
        while cursor <= end:
            days.append((cursor.isoformat(), f"{cursor.month}/{cursor.day}"))
            cursor += timedelta(days=1)
        return days
    if grain == "month":
        months: list[tuple[str, str]] = []
        cursor = month_start(start)
        while cursor <= end:
            months.append((f"{cursor.year}-{cursor.month:02d}", f"{cursor.month}月"))
            cursor = month_end(cursor) + timedelta(days=1)
        return months
    return [(str(year), str(year)) for year in range(start.year, end.year + 1)]


#: 桶粒度 → 该粒度下的聚合表后缀。``hour`` 没有对应的键桶表（它按 ``day + hour``
#: 存），因此单独处理。
BUCKET_TABLE_GRAIN: dict[str, str] = {"day": "day", "month": "month", "year": "year"}


def parse_date(text: str) -> date:
    """``YYYY-MM-DD`` → :class:`date`。**只接受这一种形态**。

    ``date.fromisoformat`` 从 Python 3.11 起还接受 ``20260831`` 与 ``2026-W35-1``
    这类写法，而它们经由 URL 传进来几乎一定是前端 bug；一并收下会让 bug 潜伏更久。
    """
    if len(text) != 10 or text[4] != "-" or text[7] != "-":
        raise ValueError(f"日期必须是 YYYY-MM-DD：{text!r}")
    return date.fromisoformat(text)


__all__ = [
    "GRANULARITY",
    "MAX_CUSTOM_SPAN_DAYS",
    "RANGES",
    "Period",
    "PeriodRequest",
    "buckets",
    "buckets_for",
    "month_end",
    "month_start",
    "parse_date",
    "previous",
    "resolve",
    "week_start",
]
