"""导出服务：CSV / JSON 流式输出（05 文档 §7）。

**流式而非先在内存里拼好。** 三年数据的会话明细是几百万行；``json.dumps`` 一次性拼出来
会让进程内存翻几倍，而导出恰好是用户最可能在数据量最大时才做的操作。

**导出的是聚合与会话，不是原始按键事件。** 原始事件是 08 文档里最敏感的一档（L4），
把它做成一键导出的默认选项等于给"拷走全部按键记录"提供便利。需要它的用户可以直接复制
数据库文件——那是一个明确得多的动作。
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterator

from .context import ServiceContext
from .period import Period

FORMATS: tuple[str, ...] = ("csv", "json")
SCOPES: tuple[str, ...] = ("usage", "keyboard", "sessions", "apps")

#: 每个 scope 的列定义。CSV 与 JSON 共用它，两种格式的字段因此不可能分叉。
COLUMNS: dict[str, tuple[str, ...]] = {
    "usage": ("app_id", "display_name", "process_name", "category", "seconds", "presses",
              "session_count", "longest_session_seconds"),
    "keyboard": ("key_id", "label", "finger", "row", "press_count", "duration_total_ms",
                 "duration_avg_ms", "duration_max_ms"),
    "sessions": ("id", "app_id", "display_name", "start", "end", "seconds", "end_reason"),
    "apps": ("app_id", "app_key", "display_name", "process_name", "category",
             "category_source", "excluded", "merged_into", "first_seen_at", "last_seen_at"),
}


class ExportService:
    __slots__ = ("_ctx", "_keyboard", "_usage")

    def __init__(self, ctx: ServiceContext, usage, keyboard) -> None:
        self._ctx = ctx
        self._usage = usage
        self._keyboard = keyboard

    def rows(self, scope: str, period: Period) -> list[dict[str, object]]:
        if scope == "usage":
            payload = self._usage.period_apps(period, limit=100_000)
            return [
                {
                    "app_id": app["app_id"],
                    "display_name": app["display_name"],
                    "process_name": app["process_name"],
                    "category": app["category"],
                    "seconds": app["seconds"],
                    "presses": app["presses"],
                    "session_count": app["session_count"],
                    "longest_session_seconds": app["longest_session_seconds"],
                }
                for app in payload["apps"]
            ]
        if scope == "keyboard":
            payload = self._keyboard.heatmap(period)
            return [
                {name: key[name] for name in COLUMNS["keyboard"] if name != "key_id"}
                | {"key_id": key["id"]}
                for key in [*payload["keys"], *payload["orphan_keys"]]
            ]
        if scope == "sessions":
            payload = self._usage.sessions(period, limit=100_000)
            return [
                {name: session.get(name) for name in COLUMNS["sessions"]}
                for session in payload["sessions"]
            ]
        metas = self._ctx.app_repo.all_meta()
        return [
            {
                "app_id": meta.app_id,
                "app_key": meta.app_key,
                "display_name": meta.display,
                "process_name": meta.process_name,
                "category": meta.category,
                "category_source": meta.category_source,
                "excluded": meta.excluded,
                "merged_into": meta.merged_into,
                "first_seen_at": meta.first_seen_at,
                "last_seen_at": meta.last_seen_at,
            }
            for meta in metas.values()
            if meta.app_id != 0
        ]

    def stream_csv(self, scope: str, period: Period) -> Iterator[str]:
        columns = COLUMNS[scope]
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        # BOM 让 Excel 正确识别 UTF-8。没有它，中文应用名在中文版 Excel 里是乱码，
        # 而"导出后打开是乱码"是导出功能最常见的一类投诉。
        yield "﻿" + _drain(buffer)
        for row in self.rows(scope, period):
            writer.writerow(row)
            yield _drain(buffer)

    def stream_json(self, scope: str, period: Period) -> Iterator[str]:
        header = json.dumps(period.to_dict(), ensure_ascii=False)
        yield '{"scope": ' + json.dumps(scope) + ', "period": ' + header + ', "rows": ['
        first = True
        for row in self.rows(scope, period):
            yield ("" if first else ",") + json.dumps(row, ensure_ascii=False)
            first = False
        yield "]}"

    def filename(self, scope: str, period: Period, fmt: str) -> str:
        return f"omnisight-{scope}-{period.start_day}_{period.end_day}.{fmt}"


def _drain(buffer: io.StringIO) -> str:
    value = buffer.getvalue()
    buffer.seek(0)
    buffer.truncate(0)
    return value


__all__ = ["COLUMNS", "FORMATS", "SCOPES", "ExportService"]
