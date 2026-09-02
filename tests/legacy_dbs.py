"""合成旧库构造器（M5 导入测试的夹具）。

真实的旧库在 ``refer/data/`` 下，但它被 gitignore（也不该进版本库——那是用户的
真实数据）。测试因此按两个旧项目的**真实 schema**（TimeLens ``database.py`` 与
KeyTrace ``database.py`` 的建表语句逐列对照）造小型确定性数据库；真实库的验证
由一次性脚本跑过并把数字记进 PROGRESS。
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

TIMELENS_DDL = """
CREATE TABLE app_usage (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    app_name    TEXT NOT NULL,
    process_name TEXT NOT NULL,
    exe_path    TEXT NOT NULL DEFAULT '',
    window_title TEXT NOT NULL DEFAULT '',
    start_time  TEXT NOT NULL,
    end_time    TEXT NOT NULL,
    duration_seconds REAL NOT NULL,
    date        TEXT NOT NULL
);
CREATE TABLE app_usage_summary (
    process_key    TEXT PRIMARY KEY,
    app_name       TEXT NOT NULL,
    process_name   TEXT NOT NULL,
    exe_path       TEXT NOT NULL DEFAULT '',
    last_used_at   TEXT NOT NULL,
    total_seconds  REAL NOT NULL DEFAULT 0,
    session_count  INTEGER NOT NULL DEFAULT 0,
    latest_usage_id INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE key_usage (
    date        TEXT NOT NULL,
    hour        INTEGER NOT NULL,
    key_name    TEXT NOT NULL,
    press_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (date, hour, key_name)
);
"""

_AGG_DDL = """
CREATE TABLE {table} (
    {first} TEXT NOT NULL,
    key_id TEXT NOT NULL,
    press_count INTEGER NOT NULL DEFAULT 0,
    duration_total_ms REAL NOT NULL DEFAULT 0,
    duration_max_ms REAL NOT NULL DEFAULT 0,
    PRIMARY KEY({first}, key_id)
) WITHOUT ROWID
"""

KEYTRACE_META_DDL = "CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"

_RAW_DDL = """
CREATE TABLE raw_key_events_{suffix} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key_id TEXT NOT NULL,
    down_ts_ns INTEGER NOT NULL,
    up_ts_ns INTEGER NOT NULL,
    duration_ms REAL NOT NULL,
    scan_code INTEGER,
    virtual_key_code INTEGER
)
"""

#: 与 tests/seeded.py 一致的时区：导入器的分桶时区、撤销重算都用它。
TZ = ZoneInfo("Asia/Shanghai")


def local_noon_ns(day: str, hour: int = 12, minute: int = 0, second: int = 0) -> int:
    """某本地日正午附近的纳秒。正午让任何合理时区下都在同一天。"""
    moment = datetime.fromisoformat(day).replace(hour=hour, minute=minute, second=second)
    return int(moment.astimezone().timestamp() * 1_000_000_000)


def tz_noon_ns(day: str, hour: int = 12) -> int:
    """上海时区某日某时的纳秒（KeyTrace 事件的时间戳基准）。"""
    moment = datetime.fromisoformat(day).replace(hour=hour, tzinfo=TZ)
    return int(moment.timestamp() * 1_000_000_000)


def make_timelens_db(
    path: Path,
    *,
    sessions: list[tuple],
    key_usage: list[tuple],
) -> Path:
    """造 TimeLens ``usage.db``。

    ``sessions`` 的行由 :func:`timelens_row` 构造：时间为 **naive 本地**
    isoformat——这正是旧库的形态（03 文档 §7.2 的歧义点）。
    """
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(TIMELENS_DDL)
        conn.executemany(
            "INSERT INTO app_usage (app_name, process_name, exe_path, window_title,"
            " start_time, end_time, duration_seconds, date)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            sessions,
        )
        conn.executemany(
            "INSERT INTO key_usage (date, hour, key_name, press_count) VALUES (?, ?, ?, ?)",
            key_usage,
        )
        conn.commit()
    finally:
        conn.close()
    return path


def make_keytrace_db(
    path: Path,
    *,
    events: list[tuple[str, str, int, float, int, int]],
) -> Path:
    """造 KeyTrace ``keytrace.sqlite3``。

    ``events``: ``(day, key_id, down_ts_ns, duration_ms, scan_code, vk)``。
    同时按 KeyTrace 的口径维护 ``agg_key_day`` / ``agg_key_total``——
    旧库的聚合与导入器无关，但扫描靠它判定覆盖日期（冲突规则）。
    """
    conn = sqlite3.connect(str(path))
    try:
        conn.execute(KEYTRACE_META_DDL)
        conn.execute("INSERT INTO meta (key, value) VALUES ('schema_version', '1')")
        for table in ("agg_key_day", "agg_key_month", "agg_key_year"):
            conn.execute(_AGG_DDL.format(table=table, first="bucket"))
        conn.execute("""
            CREATE TABLE agg_key_total (
                key_id TEXT PRIMARY KEY,
                press_count INTEGER NOT NULL DEFAULT 0,
                duration_total_ms REAL NOT NULL DEFAULT 0,
                duration_max_ms REAL NOT NULL DEFAULT 0
            ) WITHOUT ROWID
        """)
        by_month: dict[str, list[tuple]] = {}
        for day, key_id, down_ns, duration_ms, scan, vk in events:
            by_month.setdefault(day[:7], []).append(
                (key_id, down_ns, down_ns + int(duration_ms * 1_000_000),
                 duration_ms, scan, vk)
            )
        for month, rows in by_month.items():
            suffix = month.replace("-", "_")
            conn.execute(_RAW_DDL.format(suffix=suffix))
            conn.executemany(
                f"INSERT INTO raw_key_events_{suffix}"
                " (key_id, down_ts_ns, up_ts_ns, duration_ms, scan_code, virtual_key_code)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                rows,
            )
        for day, key_id, _down_ns, duration_ms, _scan, _vk in events:
            for table, bucket in (
                ("agg_key_day", day),
                ("agg_key_month", day[:7]),
                ("agg_key_year", day[:4]),
            ):
                conn.execute(
                    f"INSERT INTO {table} (bucket, key_id, press_count,"
                    " duration_total_ms, duration_max_ms) VALUES (?, ?, 1, ?, ?)"
                    " ON CONFLICT(bucket, key_id) DO UPDATE SET"
                    " press_count = press_count + 1,"
                    " duration_total_ms = duration_total_ms + excluded.duration_total_ms,"
                    " duration_max_ms = MAX(duration_max_ms, excluded.duration_max_ms)",
                    (bucket, key_id, duration_ms, duration_ms),
                )
            conn.execute(
                "INSERT INTO agg_key_total (key_id, press_count, duration_total_ms,"
                " duration_max_ms) VALUES (?, 1, ?, ?)"
                " ON CONFLICT(key_id) DO UPDATE SET"
                " press_count = press_count + 1,"
                " duration_total_ms = duration_total_ms + excluded.duration_total_ms,"
                " duration_max_ms = MAX(duration_max_ms, excluded.duration_max_ms)",
                (key_id, duration_ms, duration_ms),
            )
        conn.commit()
    finally:
        conn.close()
    return path


def timelens_row(
    day: str,
    app_name: str,
    process_name: str,
    start_hhmmss: str,
    duration_seconds: float,
    *,
    title: str = "",
    exe: str = "",
) -> tuple:
    """TimeLens session 行的便捷构造。时间为 naive 本地（旧库的真实形态）。"""
    start = datetime.fromisoformat(f"{day}T{start_hhmmss}")
    end = start + timedelta(seconds=duration_seconds)
    return (
        app_name,
        process_name,
        exe,
        title,
        start.isoformat(),
        end.isoformat(),
        duration_seconds,
        day,
    )


__all__ = [
    "TZ",
    "local_noon_ns",
    "make_keytrace_db",
    "make_timelens_db",
    "timelens_row",
    "tz_noon_ns",
]
