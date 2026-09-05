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
from ..errors import ApiError
from ..validators import json_body, require_same_site
from . import envelope

logger = logging.getLogger(__name__)

#: 「打开目录」允许的两个目标。**白名单里的两个词，不是路径参数**：接受路径就等于把"用文件
#: 管理器打开任意位置"开放给页面，而页面上的内容并不全由我们决定（窗口标题来自操作系统）。
REVEAL_TARGETS = ("data", "logs")


def _system(context: Any):
    """进程级动作的入口（18 文档 批 5）。

    装配层没给（测试里的应用工厂、以库的方式用它）时**如实回 503**，而不是 500：那不是一次
    失败的操作，是这个实例根本没有这条能力。
    """
    actions = getattr(context, "system", None)
    if actions is None:
        raise ApiError(
            "本实例没有进程控制入口", code="capability_unavailable", status=503
        )
    return actions


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

    @app.post("/api/v1/system/restart")
    def system_restart():
        """重新启动（18 文档 批 5）。

        **202 而不是 200**：动作还没做完——接班实例已经在启动，本实例马上停机。停机刻意排在
        响应之后（``lifecycle.stop_soon``），否则浏览器只看到连接被切断，而那一刻"正在重启"
        与"它崩了"分不开，该给用户看的东西却完全不同。

        接班实例沿用同一个访问令牌（``lifecycle._session_token``），因此页面等 ``/healthz``
        通了之后原地刷新就能接着用，不必让用户回托盘重开一遍。

        起不来就 500 且**本实例什么都不改**：先起后停这个顺序是这条路上唯一要紧的事。
        """
        require_same_site()
        if not _system(context).restart():
            raise ApiError(
                "没能启动接班实例，本实例仍在运行（原因见日志）",
                code="restart_failed",
                status=500,
            )
        return jsonify({**envelope(context), "restarting": True}), 202

    @app.post("/api/v1/system/quit")
    def system_quit():
        """退出。10 文档 §5.1 记着"没有托盘时退出依赖设置页的按钮"，这是那条路。

        托盘可用时它与菜单里的「退出」是同一条路径（都走 ``Lifecycle.shutdown``），因此不会
        出现"两个退出入口，行为不一样"。
        """
        require_same_site()
        _system(context).quit()
        return jsonify({**envelope(context), "stopping": True}), 202

    @app.post("/api/v1/system/reveal")
    def system_reveal():
        """打开数据目录或日志目录。

        浏览器里的页面开不了文件管理器，而"管理员模式下要降权打开"这件事后端本来就要负责
        （``lifecycle._open_external``：URL 与目录的处理方式还不一样，10 文档 §5.2 那段实测）。
        托盘那两项与设置页「数据」段因此是同一条路径。
        """
        require_same_site()
        target = str(json_body().get("target") or "data")
        if target not in REVEAL_TARGETS:
            raise ApiError(f"target 只能是 {list(REVEAL_TARGETS)}", field="target")
        if not _system(context).reveal(target):
            raise ApiError("没能打开那个目录（原因见日志）", code="internal_error", status=500)
        return jsonify({**envelope(context), "opened": target})


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
