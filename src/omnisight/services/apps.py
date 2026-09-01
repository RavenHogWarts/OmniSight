"""应用目录、别名、分类、合并与图标（05 文档 §6）。

本文件承载两件事：

* :class:`AppLens` —— **合并与排除的唯一折叠点**。聚合表里 ``msedge.exe`` 与
  ``msedgewebview2.exe`` 永远是两行；用户把它们合并后，每一张榜单都必须表现为一个应用。
  折叠在服务层做（Python 侧，结果集只有几十到几百行），SQL 保持不变——反过来把
  ``merged_into`` 解析写进每条 SQL 会让每个查询都多一次自连接，且漏掉一处就出现
  "总和对不上"。
* :class:`AppService` —— 目录查询与用户编辑。

**``app_id = 0``（"未知"）不是应用。** 它是空闲/锁屏/被排除时段的按键归属（04 文档 §2.2），
没有前台会话，因此不参与任何应用榜单；它的按键量单独报为 ``unattributed_presses``，
这样"各应用按键之和 + 未归因 = 总按键数"仍然守恒。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ..adapters.ports import UNKNOWN_APP_ID, AppIdentity
from ..storage.repositories.apps import UNSET, AppMeta, icon_is_stale
from . import categories, formatting
from .context import ServiceContext
from .period import Period, PeriodRequest

logger = logging.getLogger(__name__)

#: 图标请求的默认边长。沿用现状（TimeLens 取 32px 后按 DPR 放大）。
ICON_SIZE = 32


@dataclass(frozen=True, slots=True)
class AppLens:
    """一份应用元数据快照 + 合并关系。按 ``data_version`` 缓存，请求期内不变。"""

    metas: dict[int, AppMeta]
    merges: dict[int, int]

    def root(self, app_id: int) -> int:
        return self.merges.get(app_id, app_id)

    def meta(self, app_id: int) -> AppMeta | None:
        return self.metas.get(self.root(app_id))

    def name(self, app_id: int) -> str:
        meta = self.meta(app_id)
        return meta.display if meta else "未知"

    def category(self, app_id: int) -> str:
        meta = self.meta(app_id)
        return meta.category if meta else categories.UNCATEGORIZED

    def is_excluded(self, app_id: int) -> bool:
        """被排除的应用不参与统计（03 文档 §2.2）。合并后以**根**的设置为准。"""
        meta = self.meta(app_id)
        return bool(meta and meta.excluded)

    def is_real_app(self, app_id: int) -> bool:
        return app_id != UNKNOWN_APP_ID and not self.is_excluded(app_id)

    def fold(
        self,
        rows: list[dict],
        *,
        sum_fields: tuple[str, ...] = (),
        max_fields: tuple[str, ...] = (),
        keep_unknown: bool = False,
    ) -> list[dict]:
        """按根 ``app_id`` 合并行并丢掉被排除的应用。"""
        merged: dict[int, dict] = {}
        for row in rows:
            app_id = int(row["app_id"])
            if not keep_unknown and not self.is_real_app(app_id):
                continue
            root = self.root(app_id)
            target = merged.get(root)
            if target is None:
                merged[root] = {**row, "app_id": root}
                continue
            for name in sum_fields:
                target[name] = (target.get(name) or 0) + (row.get(name) or 0)
            for name in max_fields:
                target[name] = max(target.get(name) or 0, row.get(name) or 0)
        return list(merged.values())

    def fold_counts(self, counts: dict[int, int], *, keep_unknown: bool = False) -> dict[int, int]:
        merged: dict[int, int] = {}
        for app_id, value in counts.items():
            if not keep_unknown and not self.is_real_app(app_id):
                continue
            root = self.root(app_id)
            merged[root] = merged.get(root, 0) + value
        return merged


class AppService:
    __slots__ = ("_ctx",)

    def __init__(self, ctx: ServiceContext) -> None:
        self._ctx = ctx

    # ── 透镜 ────────────────────────────────────────────────────────────
    def lens(self) -> AppLens:
        """按 ``data_version`` 缓存的元数据快照。

        一次请求里会被四五个地方用到（榜单、分类、洞察、时间线），每次重查全表既浪费又
        可能在同一响应内看到两份不一致的元数据。
        """
        return self._ctx.cached(
            ("app_lens",),
            lambda: AppLens(self._ctx.app_repo.all_meta(), self._ctx.app_repo.merge_map()),
        )

    def invalidate(self) -> None:
        self._ctx.cache.clear()

    # ── 目录 ────────────────────────────────────────────────────────────
    def list_apps(
        self,
        *,
        query: str = "",
        category: str | None = None,
        include_excluded: bool = False,
        sort: str = "name",
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, object]:
        metas, total = self._ctx.app_repo.search(
            query=query,
            category=category,
            include_excluded=include_excluded,
            sort=sort,
            limit=limit,
            offset=offset,
        )
        totals = {row["app_id"]: row for row in self._ctx.usage_repo.app_durations_total()}
        presses = self._ctx.insight_repo.app_presses_all_time()
        return {
            "apps": [
                self.summary(meta, totals.get(meta.app_id), presses.get(meta.app_id, 0))
                for meta in metas
            ],
            "categories": categories.catalog(),
            "pagination": {"total": total, "limit": limit, "offset": offset},
        }

    def summary(
        self, meta: AppMeta, totals: dict | None, presses: int
    ) -> dict[str, object]:
        duration_ms = int((totals or {}).get("duration_ms") or 0)
        return {
            "app_id": meta.app_id,
            "display_name": meta.display,
            "process_name": meta.process_name,
            "user_alias": meta.user_alias,
            "category": meta.category,
            "category_source": meta.category_source,
            "excluded": meta.excluded,
            "merged_into": meta.merged_into,
            "icon_url": self.icon_url(meta),
            "icon_state": meta.icon_state,
            "first_seen_at": meta.first_seen_at,
            "last_seen_at": meta.last_seen_at,
            "total_seconds": round(duration_ms / 1000, 1),
            "total_seconds_formatted": formatting.format_duration(duration_ms / 1000),
            "total_presses": presses,
            "session_count": int((totals or {}).get("session_count") or 0),
        }

    def icon_url(self, meta: AppMeta) -> str | None:
        """``capabilities.icons == False`` 时返回 ``None``，前端直接走首字母色块。

        不返回一个注定 204 的地址是刻意的：那会让每个应用都发一次无谓的请求
        （04 文档 §6 结尾）。
        """
        if not self._ctx.capabilities.icons:
            return None
        return f"/api/v1/apps/{meta.app_id}/icon"

    def running_app_keys(self) -> frozenset[str]:
        """当前有可见窗口的应用（``is_running`` 字段的来源）。

        探测失败一律当"不知道"而不是"没在运行"：这个字段只是列表上的一个小圆点，
        为它让整个响应失败是不值当的。
        """
        source = getattr(self._ctx.adapters, "foreground", None)
        if source is None:
            return frozenset()
        try:
            return frozenset(identity.app_key for identity in source.list_running())
        except Exception:  # pragma: no cover - 平台探测失败
            logger.debug("枚举可见窗口失败", exc_info=True)
            return frozenset()

    def running_apps(self) -> list[dict[str, object]]:
        source = getattr(self._ctx.adapters, "foreground", None)
        if source is None:
            return []
        lens = self.lens()
        by_key = {meta.app_key: meta for meta in lens.metas.values()}
        try:
            identities = source.list_running()
        except Exception:  # pragma: no cover
            logger.debug("枚举可见窗口失败", exc_info=True)
            return []
        result: list[dict[str, object]] = []
        for identity in identities:
            meta = by_key.get(identity.app_key)
            result.append(
                {
                    "app_id": meta.app_id if meta else None,
                    "app_key": identity.app_key,
                    "display_name": meta.display if meta else identity.display_name,
                    "process_name": identity.process_name,
                    "known": meta is not None,
                }
            )
        return result

    # ── 用户编辑 ────────────────────────────────────────────────────────
    def patch(
        self,
        app_id: int,
        *,
        user_alias: object = UNSET,
        category: object = UNSET,
        excluded: object = UNSET,
    ) -> dict[str, object]:
        """改别名 / 分类 / 排除。返回实际生效的字段。"""
        self._ctx.app_repo.update(
            app_id, user_alias=user_alias, category=category, excluded=excluded
        )
        self.invalidate()
        meta = self._ctx.app_repo.get(app_id)
        applied = [
            name
            for name, value in (
                ("user_alias", user_alias),
                ("category", category),
                ("excluded", excluded),
            )
            if value is not UNSET
        ]
        return {"applied": applied, "app": self.summary(meta, None, 0) if meta else None}

    def merge(self, app_id: int, into_app_id: int | None) -> dict[str, object]:
        self._ctx.app_repo.set_merge(app_id, into_app_id)
        self.invalidate()
        return {"app_id": app_id, "merged_into": into_app_id}

    # ── 图标 ────────────────────────────────────────────────────────────
    def icon_bytes(self, app_id: int) -> bytes | None:
        """命中缓存立刻返回；未命中返回 ``None`` 并**排队后台解析**。

        04 文档 §6"改动二"：现状首次请求会在 Flask 请求线程里遍历注册表，可能耗时数百
        毫秒到数秒，仪表盘首屏因此被图标拖慢。这里请求线程只做一次主键点查。
        """
        entry = self._ctx.app_repo.icon(app_id)
        if entry and entry.get("png"):
            return bytes(entry["png"])
        if icon_is_stale(entry, now=self._ctx.clock.now()):
            self.resolve_icon(app_id)
            refreshed = self._ctx.app_repo.icon(app_id)
            if refreshed and refreshed.get("png"):
                return bytes(refreshed["png"])
        return None

    def resolve_icon(self, app_id: int) -> bool:
        """真正去平台取图标并写缓存。返回是否取到。

        同步实现：Windows 上单个应用的解析是毫秒级（``SHGetFileInfoW``），只有注册表
        回退路径慢。后台线程池排在 M7 与 SSE ``icon_ready`` 一起做；现在的关键是
        **结果被持久化**，重启不必重来。
        """
        source = getattr(self._ctx.adapters, "icons", None)
        meta = self._ctx.app_repo.get(app_id)
        if source is None or meta is None or app_id == UNKNOWN_APP_ID:
            return False
        identity = AppIdentity(
            app_key=meta.app_key,
            identity_kind=meta.identity_kind,
            display_name=meta.display_name,
            process_name=meta.process_name,
            exe_path=meta.exe_path,
        )
        try:
            png = source.icon_png(identity, ICON_SIZE)
        except Exception:  # pragma: no cover - 平台调用失败
            logger.debug("提取图标失败 app_id=%s", app_id, exc_info=True)
            png = None
        self._ctx.app_repo.store_icon(
            app_id,
            png,
            size=ICON_SIZE,
            source_path=meta.exe_path,
            now=self._ctx.clock.now(),
        )
        return png is not None

    # ── 单应用详情 ──────────────────────────────────────────────────────
    def detail(self, app_id: int) -> dict[str, object] | None:
        """05 文档 §6 的单应用响应：基础信息 + 各周期汇总 + 键盘概况 + 趋势。"""
        meta = self._ctx.app_repo.get(app_id)
        if meta is None:
            return None
        lens = self.lens()
        members = [
            member for member, root in lens.merges.items() if root == app_id
        ] or []
        ids = {app_id, *members}

        totals: dict[str, object] = {}
        for name in ("day", "week", "month"):
            period = self._ctx.resolve_period(PeriodRequest(name))
            totals[name] = self._period_totals(ids, period)
        total_rows = {
            row["app_id"]: row for row in self._ctx.usage_repo.app_durations_total()
        }
        presses_all = self._ctx.insight_repo.app_presses_all_time()
        duration_ms = sum(int((total_rows.get(i) or {}).get("duration_ms") or 0) for i in ids)
        sessions = sum(int((total_rows.get(i) or {}).get("session_count") or 0) for i in ids)
        presses = sum(presses_all.get(i, 0) for i in ids)
        totals["total"] = {
            "seconds": round(duration_ms / 1000, 1),
            "seconds_formatted": formatting.format_duration(duration_ms / 1000),
            "presses": presses,
            "session_count": sessions,
        }

        month = self._ctx.resolve_period(PeriodRequest("month"))
        series = {}
        for member in ids:
            for day, value in self._ctx.usage_repo.app_day_series(
                member, month.start_day, month.end_day
            ).items():
                series[day] = series.get(day, 0) + value
        top_keys, modifier_breakdown, modifier_total = self._key_profile(ids)
        kpm = formatting.ratio_per_minute(presses, duration_ms)
        return {
            "app": {
                "app_id": meta.app_id,
                "display_name": meta.display,
                "process_name": meta.process_name,
                "user_alias": meta.user_alias,
                "exe_path": meta.exe_path,
                "category": meta.category,
                "category_source": meta.category_source,
                "excluded": meta.excluded,
                "merged_into": meta.merged_into,
                "merged_members": sorted(members),
                "icon_url": self.icon_url(meta),
                "icon_state": meta.icon_state,
                "first_seen_at": meta.first_seen_at,
                "last_seen_at": meta.last_seen_at,
            },
            "totals": totals,
            "keyboard": {
                "kpm": kpm,
                "profile": profile_for(kpm),
                "profile_name": PROFILE_NAMES[profile_for(kpm)],
                "top_keys": top_keys,
                # 快捷键偏好（M4）：修饰键自身的细分。口径同 /insights/app-keyboard。
                "modifier_percent": formatting.percent(modifier_total, presses),
                "modifier_breakdown": modifier_breakdown,
                "kpm_basis": "该应用前台时长（不含空闲与无前台时段），全期口径",
            },
            "trend": {
                "granularity": "day",
                "buckets": [
                    {
                        "bucket": bucket,
                        "label": label,
                        "seconds": round(series.get(bucket, 0) / 1000, 1),
                    }
                    for bucket, label in _month_buckets(month)
                ],
            },
        }

    def _period_totals(self, ids: set[int], period: Period) -> dict[str, object]:
        rows = {
            row["app_id"]: row
            for row in self._ctx.usage_repo.app_durations(period.start_day, period.end_day)
        }
        presses = self._ctx.insight_repo.app_presses(period.start_day, period.end_day)
        duration_ms = sum(int((rows.get(i) or {}).get("duration_ms") or 0) for i in ids)
        return {
            "seconds": round(duration_ms / 1000, 1),
            "seconds_formatted": formatting.format_duration(duration_ms / 1000),
            "presses": sum(presses.get(i, 0) for i in ids),
            "session_count": sum(int((rows.get(i) or {}).get("session_count") or 0) for i in ids),
        }

    def _key_profile(
        self, ids: set[int], limit: int = 8
    ) -> tuple[list[dict[str, object]], list[dict[str, object]], int]:
        """常用键 + 修饰键细分，同一次读取算出（两次查询之间落一批数据就会对不上账）。

        返回 ``(top_keys, modifier_breakdown, modifier_total)``。
        """
        from ..capture import keymap

        merged: dict[str, int] = {}
        per_app = self._ctx.key_repo.app_key_totals_all_time()
        for member in ids:
            for key_id, count in per_app.get(member, {}).items():
                merged[key_id] = merged.get(key_id, 0) + count
        ordered = sorted(merged.items(), key=lambda item: item[1], reverse=True)[:limit]
        top_keys = [
            {"id": key_id, "label": keymap.label_for(key_id), "press_count": count}
            for key_id, count in ordered
        ]
        modifiers = [
            (key_id, count)
            for key_id, count in merged.items()
            if key_id in keymap.MODIFIER_KEYS and count > 0
        ]
        modifiers.sort(key=lambda item: item[1], reverse=True)
        modifier_total = sum(count for _key_id, count in modifiers)
        breakdown = [
            {
                "id": key_id,
                "label": keymap.label_for(key_id),
                "press_count": count,
                "percent": formatting.percent(count, modifier_total),
            }
            for key_id, count in modifiers
        ]
        return (top_keys, breakdown, modifier_total)


#: 输入强度画像的阈值（05 文档 §5）。KPM = 每前台分钟按键数。
PROFILE_THRESHOLDS: tuple[tuple[float, str], ...] = (
    (40.0, "input_heavy"),
    (10.0, "interactive"),
    (0.0001, "passive"),
)

PROFILE_NAMES: dict[str, str] = {
    "input_heavy": "主动输入",
    "interactive": "交互",
    "passive": "被动消费",
    "idle_open": "开着未用",
}


def profile_for(kpm: float) -> str:
    for threshold, name in PROFILE_THRESHOLDS:
        if kpm >= threshold:
            return name
    return "idle_open"


def _month_buckets(period: Period) -> list[tuple[str, str]]:
    from . import period as period_module

    return period_module.buckets(period)


__all__ = [
    "ICON_SIZE",
    "PROFILE_NAMES",
    "PROFILE_THRESHOLDS",
    "AppLens",
    "AppService",
    "profile_for",
]
