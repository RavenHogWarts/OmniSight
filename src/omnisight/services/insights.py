"""洞察服务：应用 × 键盘、作息节奏、自然语言结论（05 文档 §5）。

这是**合并才可能存在**的一层。单独的 TimeLens 只能说"7 小时"，单独的 KeyTrace 只能说
"18422 次按键"；两者放在一个库里才能说"7 小时里有 4 小时是被动消费"。

每个结论都要能说出口径（12 文档 M4 的完成判据），因此：

* ``kpm`` 的分母是**该应用的前台时长**，不含空闲与无前台时段；
* ``modifier_percent`` 数的是修饰键自身被按下的次数（不是和弦，见
  :mod:`omnisight.services.keyboard`）；
* ``focus_blocks`` 的按键量来自分钟级聚合，边界那一分钟整格计入；
* ``unattributed_presses`` 把"空闲/锁屏/被排除应用期间的按键"单列，这样
  "各应用之和 + 未归因 = 总按键数"始终守恒（04 文档 §2.2）。
"""

from __future__ import annotations

from datetime import datetime, timedelta

from ..adapters.ports import UNKNOWN_APP_ID
from ..capture import keymap
from . import formatting
from .apps import PROFILE_NAMES, AppService, profile_for
from .context import ServiceContext
from .period import Period

#: 专注时段的下限。低于 10 分钟的连续使用算不上"专注"，列出来只会淹没真正的长块。
FOCUS_MIN_MINUTES = 10
FOCUS_BLOCK_LIMIT = 10


class InsightService:
    __slots__ = ("_apps", "_ctx", "_keyboard", "_usage")

    def __init__(self, ctx: ServiceContext, apps: AppService, usage, keyboard) -> None:
        self._ctx = ctx
        self._apps = apps
        self._usage = usage
        self._keyboard = keyboard

    # ── 应用 × 键盘 ─────────────────────────────────────────────────────
    def app_keyboard(self, period: Period, *, limit: int = 20) -> dict[str, object]:
        lens = self._apps.lens()
        rows = self._usage.app_rows(period)
        if period.range == "total":
            presses_raw = self._ctx.insight_repo.app_presses_all_time()
            per_app_keys = self._ctx.key_repo.app_key_totals_all_time()
        else:
            presses_raw = self._ctx.insight_repo.app_presses(period.start_day, period.end_day)
            per_app_keys = self._ctx.key_repo.app_key_totals(period.start_day, period.end_day)
        # 修饰键占比由 ``per_app_keys`` 直接汇总，不再单独查一次 ``agg_key_app_day``。
        # 省一次 480k 行的范围扫（实测 −14ms/年）之外还有一个正确性收益：同一批数字来自
        # 同一次读取，不可能因为两次查询之间落了一批数据而对不上。
        modifiers = lens.fold_counts(
            {
                app_id: sum(
                    count for key_id, count in keys.items() if key_id in keymap.MODIFIER_KEYS
                )
                for app_id, keys in per_app_keys.items()
            }
        )
        unattributed = presses_raw.get(UNKNOWN_APP_ID, 0)
        folded_keys: dict[int, dict[str, int]] = {}
        for app_id, keys in per_app_keys.items():
            if not lens.is_real_app(app_id):
                continue
            target = folded_keys.setdefault(lens.root(app_id), {})
            for key_id, count in keys.items():
                target[key_id] = target.get(key_id, 0) + count

        apps: list[dict[str, object]] = []
        for row in rows:
            app_id = row["app_id"]
            presses = row["presses"]
            kpm = row["kpm"]
            keys = folded_keys.get(app_id, {})
            top = sorted(keys.items(), key=lambda item: item[1], reverse=True)[:5]
            apps.append(
                {
                    "app_id": app_id,
                    "display_name": row["display_name"],
                    "seconds": round(row["duration_ms"] / 1000, 1),
                    "seconds_formatted": formatting.format_duration(row["duration_ms"] / 1000),
                    "presses": presses,
                    "kpm": kpm,
                    "profile": profile_for(kpm),
                    "profile_name": PROFILE_NAMES[profile_for(kpm)],
                    "modifier_percent": formatting.percent(modifiers.get(app_id, 0), presses),
                    "top_keys": [
                        {"id": key_id, "label": keymap.label_for(key_id), "press_count": count}
                        for key_id, count in top
                    ],
                }
            )
        apps.sort(key=lambda item: item["kpm"], reverse=True)
        for index, item in enumerate(apps, start=1):
            item["intensity_rank"] = index
        apps.sort(key=lambda item: item["seconds"], reverse=True)
        return {
            "apps": apps[:limit],
            "distribution": _distribution(apps),
            "unattributed_presses": unattributed,
            "kpm_basis": "该应用前台时长（不含空闲与无前台时段）",
        }

    # ── 作息节奏 ────────────────────────────────────────────────────────
    def rhythm(self, period: Period) -> dict[str, object]:
        lens = self._apps.lens()
        first_minute, last_minute = self._ctx.key_repo.minute_bounds(
            period.start_day, period.end_day
        )
        blocks = [
            block
            for block in self._ctx.usage_repo.longest_visits(
                period.start_day,
                period.end_day,
                limit=FOCUS_BLOCK_LIMIT,
                min_ms=FOCUS_MIN_MINUTES * 60_000,
            )
            if lens.is_real_app(block["app_id"])
        ]
        focus_blocks = [self._focus_payload(block, lens) for block in blocks]
        switch_count = self._ctx.usage_repo.switch_count(period.start_day, period.end_day)
        total_ms = sum(row["duration_ms"] for row in self._usage.app_rows(period))
        hours = total_ms / 3_600_000
        peak = self._ctx.key_repo.minute_peak(period.start_day, period.end_day)
        return {
            "active_hours": {
                "first": _clock_label(first_minute),
                "last": _clock_label(last_minute),
                "span_hours": (
                    round((last_minute - first_minute) / 60, 1)
                    if first_minute is not None and last_minute is not None
                    else 0.0
                ),
            },
            "focus_blocks": focus_blocks,
            "switch_count": switch_count,
            "switches_per_hour": round(switch_count / hours, 1) if hours else 0.0,
            "switches_basis": "每小时前台时长内的应用切换次数",
            "longest_focus_minutes": max(
                (block["minutes"] for block in focus_blocks), default=0.0
            ),
            "peak_kpm": (
                {
                    "value": peak["press_count"],
                    "at": self._minute_iso(peak["day"], peak["minute"]),
                }
                if peak
                else {"value": 0, "at": None}
            ),
        }

    def _focus_payload(self, block: dict, lens) -> dict[str, object]:
        minutes = round(block["duration_ms"] / 60_000, 1)
        presses = self._presses_between(block["start_ts_ns"], block["end_ts_ns"])
        return {
            "app_id": block["app_id"],
            "display_name": lens.name(block["app_id"]),
            "start": self._iso(block["start_ts_ns"]),
            "end": self._iso(block["end_ts_ns"]),
            "minutes": minutes,
            "presses": presses,
            "kpm": formatting.ratio_per_minute(presses, block["duration_ms"]),
            "end_reason": block["end_reason"],
        }

    def _presses_between(self, start_ts_ns: int, end_ts_ns: int) -> int:
        """跨日的块按天拆开累加。块数 ≤ 10，因此这是十次主键范围扫。"""
        tz = self._ctx.timezone
        start = datetime.fromtimestamp(start_ts_ns / 1_000_000_000, tz=tz)
        end = datetime.fromtimestamp(end_ts_ns / 1_000_000_000, tz=tz)
        total = 0
        cursor = start
        while cursor.date() <= end.date():
            day = cursor.strftime("%Y-%m-%d")
            first = cursor.hour * 60 + cursor.minute if cursor.date() == start.date() else 0
            last = end.hour * 60 + end.minute if cursor.date() == end.date() else 1439
            total += self._ctx.key_repo.presses_in_day_minutes(day, first, last)
            cursor = (cursor + timedelta(days=1)).replace(hour=0, minute=0)
        return total

    def _iso(self, ts_ns: int) -> str:
        return datetime.fromtimestamp(ts_ns / 1_000_000_000, tz=self._ctx.timezone).isoformat(
            timespec="seconds"
        )

    def _minute_iso(self, day: str, minute: int) -> str:
        moment = datetime.fromisoformat(day).replace(
            hour=minute // 60, minute=minute % 60, tzinfo=self._ctx.timezone
        )
        return moment.isoformat(timespec="seconds")

    # ── 概览的自然语言结论 ──────────────────────────────────────────────
    def highlights(
        self,
        period: Period,
        *,
        screen_time: dict,
        keyboard: dict,
        app_keyboard: dict,
        timeline: dict,
    ) -> list[dict[str, str]]:
        """把数据变成一句话。这是"数据变成认知"的最后一步（06 文档 §5）。

        每条结论都由已经算好的字段拼出来，**不另发查询**——概览是首屏唯一的请求，
        再为一句话多查五次库不划算。数据不足时该条不出现，绝不输出"0 小时是被动消费"
        这种正确但无用的句子。
        """
        notes: list[dict[str, str]] = []
        hours = timeline.get("hours") or []
        if hours:
            busiest = max(hours, key=lambda item: item["total_seconds"])
            if busiest["total_seconds"] > 0:
                notes.append(
                    {
                        "code": "peak_hour",
                        "text": f"{busiest['hour']}:00 是这段时间最活跃的时段",
                    }
                )
        distribution = app_keyboard.get("distribution") or {}
        passive = float(distribution.get("passive_seconds") or 0)
        total_seconds = float(screen_time.get("total_seconds") or 0)
        if passive > 0 and total_seconds > 0:
            notes.append(
                {
                    "code": "passive_share",
                    "text": (
                        f"{formatting.format_duration(total_seconds)}里有"
                        f"{formatting.format_duration(passive)}是被动消费"
                        f"（{formatting.percent(passive, total_seconds)}%）"
                    ),
                }
            )
        apps = app_keyboard.get("apps") or []
        ranked = sorted(apps, key=lambda item: item["kpm"], reverse=True)
        if len(ranked) >= 2 and ranked[0]["kpm"] > 0:
            others = [item["kpm"] for item in ranked[1:] if item["kpm"] > 0]
            average = sum(others) / len(others) if others else 0
            if average > 0 and ranked[0]["kpm"] >= average * 1.5:
                notes.append(
                    {
                        "code": "keyboard_heavy",
                        "text": (
                            f"{ranked[0]['display_name']}的输入强度是其他应用平均的"
                            f"{round(ranked[0]['kpm'] / average, 1)}倍"
                        ),
                    }
                )
        delta = screen_time.get("delta_vs_previous")
        if delta and delta.get("percent"):
            direction = "多" if delta["percent"] > 0 else "少"
            notes.append(
                {
                    "code": "vs_previous",
                    "text": f"比上一周期{direction}了{abs(delta['percent'])}%",
                }
            )
        if keyboard.get("kpm_peak"):
            notes.append(
                {
                    "code": "kpm_peak",
                    "text": f"峰值输入速度 {keyboard['kpm_peak']} 键/分钟",
                }
            )
        return notes


def _distribution(apps: list[dict]) -> dict[str, object]:
    """按画像把前台时长分桶——"时间去向"面板的数据（06 文档 §8）。"""
    buckets: dict[str, float] = {name: 0.0 for name in PROFILE_NAMES}
    for app in apps:
        buckets[str(app["profile"])] += float(app["seconds"])
    total = sum(buckets.values())
    return {
        "buckets": [
            {
                "id": profile,
                "name": PROFILE_NAMES[profile],
                "seconds": round(seconds, 1),
                "seconds_formatted": formatting.format_duration(seconds),
                "percent": formatting.percent(seconds, total),
            }
            for profile, seconds in buckets.items()
        ],
        "input_heavy_seconds": round(buckets["input_heavy"], 1),
        "passive_seconds": round(buckets["passive"] + buckets["idle_open"], 1),
        "passive_percent": formatting.percent(
            buckets["passive"] + buckets["idle_open"], total
        ),
        "total_seconds": round(total, 1),
    }


def _clock_label(minute: int | None) -> str | None:
    """``552`` → ``"09:12"``。分钟级精度来自 ``agg_press_minute``。"""
    if minute is None:
        return None
    return f"{minute // 60:02d}:{minute % 60:02d}"


__all__ = ["FOCUS_BLOCK_LIMIT", "FOCUS_MIN_MINUTES", "InsightService"]
