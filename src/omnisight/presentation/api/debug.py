"""``/api/v1/_debug/attribution`` —— M1 的纵切验证端点（12 文档 §2 的 M1 交付物）。

**这是临时端点，M2 起由正式接口取代。** 它的唯一职责是让"合并的核心假设成立"可以被
一次 HTTP 请求验证：按一次键 → Raw Input 捕获 → Coordinator 附加 app_id → 队列 →
写线程 → ``raw_key_events`` + ``agg_key_app_day`` → 这里查得到"某应用按了 N 次 X"。

下划线前缀是刻意的：它标明这不是契约的一部分，前端不该依赖它。它同样需要令牌
（不在 ``PUBLIC_ENDPOINTS`` 里），因此不会成为一个免鉴权的信息出口。

**不返回窗口标题**，与所有正式端点一致（08 文档的硬约束）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from flask import Flask, jsonify, request

from ...capture.keymap import label_for
from ..errors import ApiError

NOTE = "临时验证端点（M1），M2 起由正式接口取代，请勿依赖其形状"


def register(app: Flask, context: Any) -> None:
    @app.get("/api/v1/_debug/attribution")
    def debug_attribution():
        capture = context.capture
        if capture is None:
            raise ApiError(
                "本次运行没有装配采集管道", code="capture_unavailable", status=422
            )
        day = request.args.get("date") or datetime.now().astimezone().strftime("%Y-%m-%d")
        _require_day(day)
        app_id = request.args.get("app_id", type=int)
        key_id = request.args.get("key_id") or "control_left"

        names = capture.registry.display_names()
        attribution = capture.coordinator.attribution()
        if app_id is None:
            app_id = attribution.app_id

        return jsonify(
            {
                "note": NOTE,
                "date": day,
                "attribution": {
                    "app_id": attribution.app_id,
                    "app_name": names.get(attribution.app_id, "未知"),
                    "confidence": attribution.confidence,
                    "idle": capture.coordinator.idle,
                },
                "capture": capture.snapshot(),
                "keyboard": {
                    "press_total": capture.keys.press_total(),
                    "top_keys": [
                        {**item, "label": label_for(item["key_id"])}
                        for item in capture.keys.top_keys(10)
                    ],
                    "hourly": capture.keys.hourly(day),
                },
                "usage": {
                    "day_total_ms": capture.usage.day_total_ms(day),
                    "ranking": capture.usage.day_ranking(day, limit=10),
                    "data_range": dict(
                        zip(("min_date", "max_date"), capture.usage.data_range(), strict=True)
                    ),
                },
                # ★ 合并的核心产出：一次主键范围查就拿到"这个应用按了哪些键"。
                "app_keyboard": {
                    "app_id": app_id,
                    "app_name": names.get(app_id, "未知"),
                    "keys": _labelled(capture.keys.app_heatmap(app_id)),
                },
                # ★ 反向视图：某个键主要被哪些应用按。合并前完全无法回答。
                "key_apps": {
                    "key_id": key_id,
                    "label": label_for(key_id),
                    "apps": [
                        {**row, "name": names.get(row["app_id"], "未知")}
                        for row in capture.keys.apps_for_key(key_id)
                    ],
                },
                "consistency": _consistency(context),
            }
        )


def _labelled(heatmap: dict[str, dict]) -> list[dict]:
    return sorted(
        ({"key_id": key_id, "label": label_for(key_id), **metrics}
         for key_id, metrics in heatmap.items()),
        key=lambda item: item["press_count"],
        reverse=True,
    )


def _consistency(context: Any) -> dict[str, Any]:
    """M1 的完成判据之一，做成端点上可见的自检。

    ``agg_key_day`` 之和、``agg_key_app_day`` 之和、``agg_app_key_total`` 之和三者必须
    相等——它们由同一个事务的三条 upsert 维护，不相等就意味着聚合漂移（R6），而这类问题
    不主动核对就永远不会被发现。
    """
    conn = context.database.connect()

    def total(sql: str) -> int:
        return int(conn.execute(sql).fetchone()[0] or 0)

    by_day = total("SELECT SUM(press_count) FROM agg_key_day")
    by_app_day = total("SELECT SUM(press_count) FROM agg_key_app_day")
    by_app_total = total("SELECT SUM(press_count) FROM agg_app_key_total")
    by_key_total = total("SELECT SUM(press_count) FROM agg_key_total")
    return {
        "agg_key_day": by_day,
        "agg_key_total": by_key_total,
        "agg_key_app_day": by_app_day,
        "agg_app_key_total": by_app_total,
        "match": by_day == by_app_day == by_app_total == by_key_total,
    }


def _require_day(day: str) -> None:
    try:
        datetime.strptime(day, "%Y-%m-%d")
    except ValueError as exc:
        # 非法参数一律 400，绝不静默回退到今天（05 文档 §1.5 对现状的关键改进）。
        raise ApiError(
            "date 必须使用 YYYY-MM-DD 格式", code="invalid_date", field="date"
        ) from exc


__all__ = ["register"]
