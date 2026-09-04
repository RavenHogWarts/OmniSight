"""服务层：把仓储返回的事实拼成 05 文档定义的响应形状。

分层约定（02 文档 §1）：**表现层只认识服务，服务只认识仓储，仓储独占 SQL。**
表现层拿不到 :class:`~omnisight.services.context.ServiceContext`，因此不可能绕过服务
直接查库——这条边界靠"``presentation/`` 里没有 ``SELECT``"的静态检查兜住。

:class:`Services` 是这一层的组合根，也是 ``/api/v1/overview`` 的家：概览横跨时长、键盘
与洞察三个服务，放进任何单一服务都会让那个服务反向依赖另外两个。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from ..adapters.ports import Capabilities
from ..core.clock import Clock, SystemClock
from ..core.config import Config
from ..storage.database import Database
from .apps import AppService
from .cache import QueryCache
from .context import ServiceContext
from .export import ExportService
from .insights import InsightService
from .keyboard import KeyboardService
from .legacy import LegacyService
from .onboarding import OnboardingService
from .period import Period
from .settings import SettingsService
from .usage import UsageService

#: ``/api/v1/overview`` 的可裁剪段（``?include=screen_time,keyboard``）。
#: 轮询时只取变化的部分，而不是每次重算整屏（05 文档 §2）。
OVERVIEW_SECTIONS: tuple[str, ...] = (
    "screen_time",
    "keyboard",
    "categories",
    "trend",
    "context",
    "top_apps",
    "highlights",
)

#: 对照条：``range`` → (桶粒度, 桶数)。日看近 7 天、周看近 8 周、月看近 12 个月、
#: 年看全部年份（14 文档 §4.3）。
#:
#: ``total`` 与 ``custom`` 不在表里，因此响应里没有 ``context``，前端整块隐藏——
#: "全部"没有"上一档粒度的同周期序列"可比，硬凑一条会让"这段时间算不算多"失去参照物。
CONTEXT_SPANS: dict[str, tuple[str, int]] = {
    "day": ("day", 7),
    "week": ("week", 8),
    "month": ("month", 12),
    "year": ("year", 0),
}


@dataclass(slots=True)
class Services:
    context: ServiceContext
    apps: AppService
    usage: UsageService
    keyboard: KeyboardService
    insights: InsightService
    settings: SettingsService
    export: ExportService
    legacy: LegacyService
    onboarding: OnboardingService

    @classmethod
    def build(
        cls,
        *,
        database: Database,
        config: Config,
        capabilities: Capabilities,
        config_path: Path,
        clock: Clock | None = None,
        capture: Any = None,
        adapters: Any = None,
        cache: QueryCache | None = None,
        on_config_change: Any = None,
        bus: Any = None,
        data_dir: Path | None = None,
    ) -> Services:
        context = ServiceContext(
            database=database,
            config=config,
            capabilities=capabilities,
            clock=clock or SystemClock(),
            cache=cache or QueryCache(),
            capture=capture,
            adapters=adapters,
        )
        apps = AppService(context)
        usage = UsageService(context, apps)
        keyboard = KeyboardService(context, apps)
        insights = InsightService(context, apps, usage, keyboard)
        settings = SettingsService(context, config_path=config_path, on_change=on_config_change)
        export = ExportService(context, usage, keyboard)
        from ..core import paths as _paths
        from ..core.clock import resolve_timezone

        legacy = LegacyService(
            database,
            data_dir=data_dir or _paths.data_dir(),
            tz=resolve_timezone(config.ui.timezone) if config.ui.timezone else None,
            store_raw=config.capture.store_raw_key_events,
            platform_id=capabilities.platform_id,
            bus=bus,
        )
        return cls(
            context=context,
            apps=apps,
            usage=usage,
            keyboard=keyboard,
            insights=insights,
            settings=settings,
            export=export,
            legacy=legacy,
            onboarding=OnboardingService(context),
        )

    # ── 概览：首屏唯一的数据请求 ────────────────────────────────────────
    def overview(
        self, period: Period, *, include: tuple[str, ...] = OVERVIEW_SECTIONS
    ) -> dict[str, object]:
        """把旧的多个请求合并成一个（05 文档 §2）。

        旧 TimeLens 首屏发 3 个请求、旧 KeyTrace 发 5 个，而它们返回的数据高度重叠——
        应用榜单要算一次时长，趋势图再算一次，分类饼图第三次。这里每份事实只算一次。
        """
        payload: dict[str, object] = {}
        screen_time = self.usage.screen_time(period) if _wants(include, "screen_time") else {}
        keyboard = self.keyboard.summary(period) if _wants(include, "keyboard") else {}
        if screen_time:
            payload["screen_time"] = screen_time
        if keyboard:
            payload["keyboard"] = keyboard
        if _wants(include, "categories"):
            payload["categories"] = self.usage.category_breakdown(period)
        if _wants(include, "trend"):
            payload["trend"] = self._trend(period)
        if _wants(include, "context"):
            context = self._context(period)
            if context is not None:
                payload["context"] = context
        top_apps: list[dict] = []
        if _wants(include, "top_apps"):
            top_apps = self.usage.period_apps(period, limit=8)["apps"]
            payload["top_apps"] = top_apps
        if _wants(include, "highlights"):
            payload["highlights"] = self.insights.highlights(
                period,
                screen_time=screen_time or self.usage.screen_time(period),
                keyboard=keyboard or self.keyboard.summary(period),
                app_keyboard=self.insights.app_keyboard(period, limit=20),
                timeline=self.usage.timeline(period),
                # 只算"打字最密集 vs 屏幕最长"所需的两张小时表，不为结论卡跑完整
                # rhythm（分钟极值 + 专注块在三年库上 ~100ms，概览付不起）。
                rhythm=self.insights.hour_contrast(period),
            )
        return payload

    def _trend(self, period: Period) -> dict[str, object]:
        from . import period as period_module

        seconds = self.usage.trend_seconds(period)
        if period.granularity == "hour":
            hourly = self.context.key_repo.hourly_metrics(period.start_day, period.end_day)
            presses = {f"{hour:02d}": values["press_count"] for hour, values in hourly.items()}
        else:
            grain = period.granularity
            bounds = _grain_bounds(grain, period)
            presses = {
                bucket: values["press_count"]
                for bucket, values in self.context.key_repo.bucket_metrics(
                    grain, *bounds
                ).items()
            }
        # 类别构成与 seconds 同源（``trend_composition`` 的第一条口径决定），因此
        # 上面板的堆叠段加起来正好是柱高。空桶给空字典而不是省略这个键——前端不必
        # 为"缺席"和"全零"写两条分支。
        composition = self.usage.trend_composition(period)
        return {
            "granularity": period.granularity,
            "buckets": [
                {
                    "bucket": bucket,
                    "label": label,
                    "seconds": seconds.get(bucket, 0.0),
                    "presses": int(presses.get(bucket, 0)),
                    "categories": composition.get(bucket, {}),
                }
                for bucket, label in period_module.buckets(period)
            ],
        }


    # ── 对照条：这段时间算不算多 ────────────────────────────────────────
    def _context(self, period: Period) -> dict[str, object] | None:
        """当前周期所在的上一档粒度序列（14 文档 §4.3 的对照条）。

        它回答屏幕时间工具最该回答的那个问题——**今天算多还是算少**。指标卡上原来那条
        趋势线画的是"本周期内部"的桶（看"日"时是 24 个小时），与它上方的活动带同源，
        因此给不出任何跨周期的参照（14 文档 §2.18 记为 P2-7）。

        两个字段一起给：``seconds`` 与活动带同口径（都经 AppLens 折叠），当前那根柱子
        因此与英雄数值对得上；``presses`` 让按键卡复用同一条序列，不必再发一次请求。
        """
        spec = CONTEXT_SPANS.get(period.range)
        if spec is None:
            return None
        grain, count = spec
        keys = self._context_keys(period, grain, count)
        if not keys:
            return None
        seconds, presses = self._context_series(grain, keys)
        return {
            "grain": grain,
            "current": _context_current(period, grain),
            "buckets": [
                {
                    "bucket": key,
                    "label": label,
                    "seconds": seconds.get(key, 0.0),
                    "presses": presses.get(key, 0),
                }
                for key, label, _start, _end in keys
            ],
        }

    def _context_keys(
        self, period: Period, grain: str, count: int
    ) -> list[tuple[str, str, date, date]]:
        """``(桶键, 标签, 首日, 末日)`` 序列，序列以当前周期收尾（年粒度除外）。"""
        from . import period as period_module

        start = period.start
        if grain == "day":
            days = [start - timedelta(days=offset) for offset in range(count - 1, -1, -1)]
            return [(day.isoformat(), f"{day.month}/{day.day}", day, day) for day in days]
        if grain == "week":
            first = period_module.week_start(start, self.context.config.ui.week_starts_on)
            weeks = [first - timedelta(days=7 * offset) for offset in range(count - 1, -1, -1)]
            return [
                (week.isoformat(), f"{week.month}/{week.day}", week, week + timedelta(days=6))
                for week in weeks
            ]
        if grain == "month":
            cursor = period_module.month_start(start)
            months = []
            for _ in range(count):
                months.append(cursor)
                cursor = period_module.month_start(cursor - timedelta(days=1))
            months.reverse()
            return [
                (
                    f"{month.year}-{month.month:02d}",
                    f"{month.month}月",
                    month,
                    period_module.month_end(month),
                )
                for month in months
            ]
        # 年：全部年份，因此当前那一根不一定在末尾（看 2025 而库里有 2026 的时候）。
        first_day, last_day = self.context.usage_repo.data_range()
        first_year = int(first_day[:4]) if first_day else start.year
        last_year = max(int(last_day[:4]) if last_day else start.year, start.year)
        return [
            (str(year), str(year), date(year, 1, 1), date(year, 12, 31))
            for year in range(min(first_year, start.year), last_year + 1)
        ]

    def _context_series(
        self, grain: str, keys: list[tuple[str, str, date, date]]
    ) -> tuple[dict[str, float], dict[str, int]]:
        if grain == "week":
            # 没有周聚合表：拿日桶按周首归并。8 周 = 56 行，为它建第四张表不划算。
            week_of: dict[str, str] = {}
            for key, _label, first, last in keys:
                cursor = first
                while cursor <= last:
                    week_of[cursor.isoformat()] = key
                    cursor += timedelta(days=1)
            first_day = keys[0][2].isoformat()
            last_day = keys[-1][3].isoformat()
            seconds: dict[str, float] = {}
            for day, value in self.usage.bucket_seconds("day", first_day, last_day).items():
                bucket = week_of.get(day)
                if bucket:
                    seconds[bucket] = round(seconds.get(bucket, 0.0) + value, 1)
            presses: dict[str, int] = {}
            for day, values in self.context.key_repo.bucket_metrics(
                "day", first_day, last_day
            ).items():
                bucket = week_of.get(day)
                if bucket:
                    presses[bucket] = presses.get(bucket, 0) + int(values["press_count"] or 0)
            return seconds, presses
        first_key, last_key = keys[0][0], keys[-1][0]
        return (
            self.usage.bucket_seconds(grain, first_key, last_key),
            {
                bucket: int(values["press_count"] or 0)
                for bucket, values in self.context.key_repo.bucket_metrics(
                    grain, first_key, last_key
                ).items()
            },
        )


def _context_current(period: Period, grain: str) -> str:
    """对照条上"当前那一根"的键。emphasis 编码只认这一个值。"""
    if grain == "month":
        return f"{period.start.year}-{period.start.month:02d}"
    if grain == "year":
        return str(period.start.year)
    return period.start.isoformat()

def _wants(include: tuple[str, ...], section: str) -> bool:
    return section in include


def _grain_bounds(grain: str, period: Period) -> tuple[str, str]:
    if grain == "month":
        return (period.start_day[:7], period.end_day[:7])
    if grain == "year":
        return (period.start_day[:4], period.end_day[:4])
    return period.day_range


__all__ = [
    "OVERVIEW_SECTIONS",
    "AppService",
    "ExportService",
    "InsightService",
    "KeyboardService",
    "LegacyService",
    "OnboardingService",
    "ServiceContext",
    "Services",
    "SettingsService",
    "UsageService",
]
