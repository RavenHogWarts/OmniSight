"""服务层：把仓储返回的事实拼成 05 文档定义的响应形状。

分层约定（02 文档 §1）：**表现层只认识服务，服务只认识仓储，仓储独占 SQL。**
表现层拿不到 :class:`~omnisight.services.context.ServiceContext`，因此不可能绕过服务
直接查库——这条边界靠"``presentation/`` 里没有 ``SELECT``"的静态检查兜住。

:class:`Services` 是这一层的组合根，也是 ``/api/v1/overview`` 的家：概览横跨时长、键盘
与洞察三个服务，放进任何单一服务都会让那个服务反向依赖另外两个。
"""

from __future__ import annotations

from dataclasses import dataclass
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
    "top_apps",
    "highlights",
)


@dataclass(slots=True)
class Services:
    context: ServiceContext
    apps: AppService
    usage: UsageService
    keyboard: KeyboardService
    insights: InsightService
    settings: SettingsService
    export: ExportService

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
        return cls(
            context=context,
            apps=apps,
            usage=usage,
            keyboard=keyboard,
            insights=insights,
            settings=settings,
            export=export,
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
        return {
            "granularity": period.granularity,
            "buckets": [
                {
                    "bucket": bucket,
                    "label": label,
                    "seconds": seconds.get(bucket, 0.0),
                    "presses": int(presses.get(bucket, 0)),
                }
                for bucket, label in period_module.buckets(period)
            ],
        }


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
    "ServiceContext",
    "Services",
    "SettingsService",
    "UsageService",
]
