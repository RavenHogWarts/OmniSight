"""系统状态与只读自检（05 文档 §7）。

``/api/v1/status`` 是**前端唯一的降级依据**：它给出 ``capabilities`` 与 ``degraded``，
前端不判断 ``navigator.platform``、不判断 ``platform.id``（07 文档 §10）。

``capabilities`` **不在这里另算一份**——它是装配阶段 ``reconcile()`` 产出的那一个对象
（12 文档 M2 的完成判据）。注意语义：上报的是**有效能力**（环境允许 ∧ 本版本已实现 ∧
已成功启动），不是 ``detect()`` 的环境能力。判据原文写的是"与 detect() 完全一致"，
但 M0 的偏离 2 已经确定 UI 与接口该信的是有效能力——判据的实质是"不许另算一份"。
"""

from __future__ import annotations

import logging
from typing import Any

from flask import Flask, jsonify

from ... import __version__
from ...core import paths

logger = logging.getLogger(__name__)


def register(app: Flask, context: Any) -> None:
    @app.get("/api/v1/status")
    def status():
        return jsonify(build_status(context))

    @app.get("/api/v1/maintenance/integrity")
    def integrity():
        """聚合表之间的一致性自检。

        它接替了 M1 的临时端点 ``/api/v1/_debug/attribution`` 里最有价值的那一段：
        ``agg_key_day`` / ``agg_key_app_day`` / ``agg_app_key_total`` / ``agg_key_total``
        四张表由同一个事务的四条 upsert 维护，四者之和必须相等，不相等就意味着聚合漂移
        （12 文档 R6）。这类问题不主动核对就永远不会被发现，因此做成一个**永久**的只读
        端点，冒烟测试也据此验证打包产物（11 文档 §5）。
        """
        return jsonify(aggregate_integrity(context))


def build_status(context: Any) -> dict[str, Any]:
    """``/api/v1/status`` 的响应体。

    ``platform`` 仅用于展示与排查，不参与任何逻辑分支——这与后端"能力探测，不做平台
    判断"的原则是同一条规则的两端。
    """
    caps = context.capabilities
    database_path = context.database.path
    min_date, max_date = _data_range(context)
    return {
        "app": "OmniSight",
        "version": __version__,
        "port": context.config.server.port,
        "started_at": context.started_at,
        "platform": {
            "id": caps.platform_id,
            "tier": caps.tier,
            "os_version": caps.os_version,
        },
        "capabilities": caps.to_dict(),
        "capture": _capture_status(context),
        "database": {
            "path": str(database_path),
            "schema_version": context.schema_version,
            "size_bytes": database_path.stat().st_size if database_path.exists() else 0,
        },
        "paths": paths.describe(),
        "data_range": {"min_date": min_date, "max_date": max_date},
        "data_version": context.database.data_version(),
        "degraded": [_notice_to_dict(notice) for notice in caps.degraded],
        "warnings": [],
    }


#: 每一张按键总量必须相等的聚合表。**七张表存的是同一个事实的七种切法**，任何一张对不上
#: 就说明写入侧的某条 upsert 漏了或多了——而这种漂移在界面上看不出来（每张图各自都
#: "自洽"），只有主动核对才会暴露（R6）。
PRESS_TOTAL_SOURCES: tuple[tuple[str, str], ...] = (
    ("agg_key_day", "SELECT SUM(press_count) FROM agg_key_day"),
    ("agg_key_total", "SELECT SUM(press_count) FROM agg_key_total"),
    ("agg_key_hour", "SELECT SUM(press_count) FROM agg_key_hour"),
    ("agg_key_app_day", "SELECT SUM(press_count) FROM agg_key_app_day"),
    ("agg_app_key_total", "SELECT SUM(press_count) FROM agg_app_key_total"),
    ("agg_app_day", "SELECT SUM(press_count) FROM agg_app_day"),
    ("agg_press_hour", "SELECT SUM(press_count) FROM agg_press_hour"),
    ("agg_press_minute", "SELECT SUM(press_count) FROM agg_press_minute"),
)


def aggregate_integrity(context: Any) -> dict[str, Any]:
    conn = context.database.connect()
    aggregates = {
        name: int(conn.execute(sql).fetchone()[0] or 0) for name, sql in PRESS_TOTAL_SOURCES
    }
    return {
        "aggregates": aggregates,
        "match": len(set(aggregates.values())) == 1,
        "data_version": context.database.data_version(),
    }


def _capture_status(context: Any) -> dict[str, Any]:
    """采集管道的实时状态。没有管道时如实上报"没在跑"，不编造字段。"""
    if context.capture is None:
        return {
            "foreground": {"running": False, "backend": "none"},
            "keyboard": {"running": False, "backend": "none"},
            "writer": {"running": False},
            "paused": context.paused,
            "queue_depth": 0,
            "dropped_events": 0,
        }
    return context.capture.snapshot()


def _data_range(context: Any) -> tuple[str | None, str | None]:
    try:
        return context.services.context.usage_repo.data_range()
    except Exception:  # pragma: no cover - 状态接口绝不因为一次查询失败而 500
        logger.debug("读取数据日期范围失败", exc_info=True)
        return (None, None)


def _notice_to_dict(notice: Any) -> dict[str, Any]:
    return {
        "code": notice.code,
        "severity": notice.severity,
        "title": notice.title,
        "detail": notice.detail,
        "hint": notice.hint,
        "docs": notice.docs,
    }


__all__ = ["aggregate_integrity", "build_status", "register"]
