"""服务层的共享上下文与响应外壳。

**为什么需要这个模块**：05 文档 §1.4 规定每个统计响应都带同一套元信息
（``period`` / ``generated_at`` / ``data_version`` / ``coverage`` / ``warnings``），
而六个服务都需要同一组依赖（库、配置、时钟、能力、缓存、仓储）。没有共同的家，这套
外壳会被抄六遍，然后慢慢分叉——``coverage`` 少一个字段这种缺陷在 UI 上看不出来。

02 文档 §2 的目录树里没有这个文件，它是实现时才浮现的需求。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, tzinfo
from typing import Any

from ..adapters.ports import Capabilities
from ..core.clock import Clock, SystemClock, resolve_timezone, timezone_label
from ..core.config import Config
from ..storage.database import Database
from ..storage.repositories.apps import AppDirectory
from ..storage.repositories.insights import InsightsRepository
from ..storage.repositories.keys import KeyRepository
from ..storage.repositories.usage import UsageRepository
from . import coverage as coverage_module
from . import period as period_module
from .cache import QueryCache


@dataclass(slots=True)
class ServiceContext:
    """一次运行里服务层需要的全部东西。表现层只拿到服务，拿不到它。"""

    database: Database
    config: Config
    capabilities: Capabilities
    clock: Clock = field(default_factory=SystemClock)
    cache: QueryCache = field(default_factory=QueryCache)
    #: 采集管道（``CaptureBundle``）。用 ``Any`` 持有以免 services → core.lifecycle 成环；
    #: 服务层只用到它的 ``snapshot()`` 与暂停开关。
    capture: Any = None
    #: 适配器集合。图标与"正在运行的应用"要用到，其余服务不碰它。
    adapters: Any = None
    usage_repo: UsageRepository | None = None
    key_repo: KeyRepository | None = None
    app_repo: AppDirectory | None = None
    insight_repo: InsightsRepository | None = None

    def __post_init__(self) -> None:
        self.usage_repo = self.usage_repo or UsageRepository(self.database)
        self.key_repo = self.key_repo or KeyRepository(self.database)
        self.app_repo = self.app_repo or AppDirectory(self.database)
        self.insight_repo = self.insight_repo or InsightsRepository(self.database)

    # ── 时间 ────────────────────────────────────────────────────────────
    @property
    def timezone(self) -> tzinfo:
        return resolve_timezone(self.config.ui.timezone)

    def today(self) -> date:
        return self.clock.now().date()

    # ── 周期 ────────────────────────────────────────────────────────────
    def resolve_period(self, request: period_module.PeriodRequest) -> period_module.Period:
        """展开周期。``total`` 要知道数据的起止日期，因此展开发生在这里而不是表现层。"""
        data_range = (None, None)
        if request.range == "total":
            first, last = self.usage_repo.data_range()
            data_range = (
                period_module.parse_date(first) if first else None,
                period_module.parse_date(last) if last else None,
            )
        return period_module.resolve(
            request,
            today=self.today(),
            week_starts_on=self.config.ui.week_starts_on,
            data_range=data_range,
        )

    def previous_period(self, period: period_module.Period) -> period_module.Period | None:
        return period_module.previous(
            period, today=self.today(), week_starts_on=self.config.ui.week_starts_on
        )

    # ── 版本与外壳 ──────────────────────────────────────────────────────
    def data_version(self) -> int:
        return self.database.data_version()

    def coverage(self, period: period_module.Period) -> dict[str, object]:
        return coverage_module.summarize(
            self.database.connect(), period.start_day, period.end_day, period.days
        )

    def envelope(
        self,
        period: period_module.Period | None = None,
        *,
        warnings: list[dict[str, str]] | None = None,
        with_coverage: bool = True,
    ) -> dict[str, object]:
        """响应的公共部分。

        ``generated_at`` 与 ``is_current`` 依赖墙钟，因此外壳**永不进缓存**——跨零点时
        ``is_current`` 会翻转而 ``data_version`` 没变（见 :mod:`.cache` 的说明）。
        """
        payload: dict[str, object] = {
            "generated_at": self.clock.now().isoformat(timespec="milliseconds"),
            "data_version": self.data_version(),
            "warnings": warnings or [],
        }
        if period is not None:
            payload["period"] = period.to_dict()
            if with_coverage:
                payload["coverage"] = self.coverage(period)
        return payload

    def cached(self, key: tuple, compute) -> Any:
        return self.cache.get_or_compute(key, self.data_version(), compute)


def timezone_warning(client_tz: str | None, server_tz: tzinfo) -> dict[str, str] | None:
    """前端传来的时区与后端不一致时的 ``warnings`` 条目（05 文档 §1.2 的 ``tz_check``）。

    不报错也不改行为：日期桶在写入时就按后端时区算好了，事后换时区解释同一批数据只会
    造出第二套口径。但用户需要知道"你看到的日期是按 Asia/Shanghai 切的"，否则出差时
    会觉得数据错了。
    """
    if not client_tz:
        return None
    server = timezone_label(server_tz)
    if client_tz == server:
        return None
    return {
        "code": "timezone_mismatch",
        "message": f"浏览器时区为 {client_tz}，而日期按 {server} 切分",
    }


__all__ = ["ServiceContext", "timezone_warning"]
