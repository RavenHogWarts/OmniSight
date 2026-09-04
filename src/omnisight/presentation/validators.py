"""请求参数校验（05 文档 §9）。

**一条铁律：非法参数一律 400，绝不静默回退。** 旧 TimeLens 的 ``_validate_date`` 遇到坏
日期就悄悄用今天，于是前端 bug 与用户的真实意图同时被掩盖——用户以为自己看的是 8 月 3 日
的数据，实际是今天的。

**只做语法校验，不做语义展开。** ``range=total`` 要展开成"有数据的第一天到今天"，而
"哪天有数据"是存储事实——那一步在 :mod:`omnisight.services.period` 里做。表现层产出
:class:`~omnisight.services.period.PeriodRequest`，服务层把它变成 ``Period``。
（05 文档 §9 的示例把两件事写在一个函数里，这里刻意分开。）
"""

from __future__ import annotations

from datetime import date
from typing import Any

from flask import request

from ..services import period as period_module
from ..services.keyboard import METRICS, TIMELINE_VIEWS
from ..services.period import MAX_CUSTOM_SPAN_DAYS, RANGES, PeriodRequest
from .errors import ApiError

#: 统一上限（05 文档 §9）。分页上限存在的理由是"一次请求能算完并且能渲染"。
MAX_LIMIT = 1000
MAX_PROCESS_NAME = 260

_SORTS_USAGE = ("seconds", "presses", "sessions", "name", "last_seen")
_SORTS_APPS = ("name", "last_seen", "first_seen", "process")


def _date(value: str, field: str) -> date:
    try:
        return period_module.parse_date(value)
    except ValueError as exc:
        raise ApiError(
            "日期必须使用 YYYY-MM-DD 格式", code="invalid_date", field=field
        ) from exc


def optional_date(args, field: str) -> date | None:
    raw = (args.get(field) or "").strip()
    return _date(raw, field) if raw else None


def parse_period(args) -> PeriodRequest:
    """校验 ``range`` / ``date`` / ``start`` / ``end``，返回未展开的请求。"""
    range_name = (args.get("range") or "day").strip()
    if range_name not in RANGES:
        raise ApiError(
            f"range 必须是 {'、'.join(RANGES)}", code="invalid_range", field="range"
        )
    if range_name == "custom":
        start = optional_date(args, "start")
        end = optional_date(args, "end")
        if start is None or end is None:
            raise ApiError(
                "range=custom 需要同时提供 start 与 end",
                code="invalid_param",
                field="start" if start is None else "end",
            )
        if start > end:
            raise ApiError("start 不能晚于 end", code="invalid_param", field="start")
        if (end - start).days + 1 > MAX_CUSTOM_SPAN_DAYS:
            raise ApiError(
                f"自定义区间不能超过 {MAX_CUSTOM_SPAN_DAYS} 天",
                code="invalid_param",
                field="end",
            )
        return PeriodRequest("custom", start=start, end=end)
    return PeriodRequest(range_name, anchor=optional_date(args, "date"))


def parse_metric(args, field: str = "metric") -> str:
    metric = (args.get(field) or "press_count").strip()
    if metric not in METRICS:
        raise ApiError(
            f"metric 必须是 {'、'.join(METRICS)}", code="invalid_metric", field=field
        )
    return metric


def parse_int(args, field: str, *, default: int | None = None, minimum: int = 0,
              maximum: int | None = None) -> int | None:
    raw = args.get(field)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ApiError(f"{field} 必须是整数", code="invalid_param", field=field) from exc
    if value < minimum or (maximum is not None and value > maximum):
        bound = f"{minimum}–{maximum}" if maximum is not None else f"≥ {minimum}"
        raise ApiError(f"{field} 必须在 {bound} 之间", code="invalid_param", field=field)
    return value


def parse_app_id(args, field: str = "app_id") -> int | None:
    """``app_id`` 必须是正整数。0 是"未知"哨兵，不接受用户按它查询——它不是一个应用。"""
    return parse_int(args, field, default=None, minimum=1)


def parse_limit(args, *, default: int = 50, maximum: int = MAX_LIMIT) -> int:
    return int(parse_int(args, "limit", default=default, minimum=1, maximum=maximum))


def parse_offset(args) -> int:
    return int(parse_int(args, "offset", default=0, minimum=0))


def parse_bool(args, field: str, *, default: bool = False) -> bool:
    raw = args.get(field)
    if raw is None or raw == "":
        return default
    lowered = str(raw).strip().casefold()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    raise ApiError(f"{field} 必须是 true 或 false", code="invalid_param", field=field)


def parse_choice(args, field: str, choices: tuple[str, ...], default: str) -> str:
    value = (args.get(field) or default).strip()
    if value not in choices:
        raise ApiError(
            f"{field} 必须是 {'、'.join(choices)}", code="invalid_param", field=field
        )
    return value


def parse_sort(args, *, kind: str = "usage") -> str:
    choices = _SORTS_APPS if kind == "apps" else _SORTS_USAGE
    return parse_choice(args, "sort", choices, choices[0])


def parse_views(args) -> tuple[str, ...]:
    """``view=hours,days`` → 多视图。一次取回把 KeyTrace 首屏的 4 个请求合成 1 个。"""
    raw = (args.get("view") or "days").strip()
    views = tuple(item.strip() for item in raw.split(",") if item.strip())
    unknown = [view for view in views if view not in TIMELINE_VIEWS]
    if not views or unknown:
        raise ApiError(
            f"view 必须是 {'、'.join(TIMELINE_VIEWS)} 的逗号分隔组合",
            code="invalid_param",
            field="view",
        )
    # 去重但保持请求顺序：前端按这个顺序渲染。
    return tuple(dict.fromkeys(views))


def parse_include(args, allowed: tuple[str, ...]) -> tuple[str, ...]:
    raw = (args.get("include") or "").strip()
    if not raw:
        return allowed
    parts = tuple(item.strip() for item in raw.split(",") if item.strip())
    unknown = [item for item in parts if item not in allowed]
    if unknown:
        raise ApiError(
            f"include 只能包含 {'、'.join(allowed)}", code="invalid_param", field="include"
        )
    return parts


def parse_key_id(value: str) -> str:
    """键 id 只允许小写字母、数字与下划线。

    它会被当作 SQL 参数（安全）也会被当作字典键（无害），但**长度与字符集必须限住**：
    这个值来自 URL 路径，而"任意长字符串进日志"本身就是一条噪声通道。
    """
    key_id = (value or "").strip()
    if not key_id or len(key_id) > 32 or not all(
        char.islower() or char.isdigit() or char == "_" for char in key_id
    ):
        raise ApiError("key_id 形态非法", code="invalid_param", field="key_id")
    return key_id


def parse_process_name(args, field: str = "process_name") -> str | None:
    raw = (args.get(field) or "").strip()
    if not raw:
        return None
    if len(raw) > MAX_PROCESS_NAME:
        raise ApiError(
            f"{field} 不能超过 {MAX_PROCESS_NAME} 个字符", code="invalid_param", field=field
        )
    return raw


def parse_query(args, field: str = "q") -> str:
    raw = (args.get(field) or "").strip()
    if len(raw) > MAX_PROCESS_NAME:
        raise ApiError(
            f"{field} 过长", code="invalid_param", field=field
        )
    return raw


# ── 写操作 ──────────────────────────────────────────────────────────────
def require_same_site() -> None:
    """写操作的第二道闸（08 文档 §3.2d）。

    令牌防的是"任意网页能不能读数据"；这一条防的是"能不能让浏览器代替用户发起写操作"。
    ``Sec-Fetch-Site`` 由浏览器填写、网页改不了；``none`` 表示用户直接在地址栏发起。
    不支持这个头的老浏览器会落到 ``Origin`` 判断上。
    """
    site = request.headers.get("Sec-Fetch-Site")
    if site in {"same-origin", "none"}:
        return
    if site is None:
        origin = request.headers.get("Origin")
        if not origin or origin.rstrip("/") == request.host_url.rstrip("/"):
            return
    raise ApiError(
        "写操作只接受同源请求", code="cross_site_denied", status=403
    )


def json_body() -> dict[str, Any]:
    """请求体必须是 JSON 对象。**不接受表单**——表单能被跨站提交，JSON 不能（预检）。"""
    if not request.is_json:
        raise ApiError("请求体必须是 JSON", code="invalid_param")
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ApiError("请求体必须是 JSON 对象", code="invalid_param")
    return payload


def body_bool(payload: dict[str, Any], field: str, *, default: bool | None = None) -> bool:
    value = payload.get(field, default)
    if not isinstance(value, bool):
        raise ApiError(f"{field} 必须是 true 或 false", code="invalid_param", field=field)
    return value


__all__ = [
    "MAX_LIMIT",
    "MAX_PROCESS_NAME",
    "body_bool",
    "json_body",
    "optional_date",
    "parse_app_id",
    "parse_bool",
    "parse_choice",
    "parse_include",
    "parse_int",
    "parse_key_id",
    "parse_limit",
    "parse_metric",
    "parse_offset",
    "parse_period",
    "parse_process_name",
    "parse_query",
    "parse_sort",
    "parse_views",
    "require_same_site",
]
