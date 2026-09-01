"""建表 DDL —— **全项目的事实基准**（03 文档 §2）。

声明式单一真源：迁移脚本执行这里的语句，测试断言这里的结构，任何"某个字段
到底存不存在"的问题都以本文件为准。

两条贯穿全表的约定：

* **时间一律是纳秒整数**，不用 ISO 字符串。旧 TimeLens 用文本时间戳，导致
  按小时归桶要把整表读进 Python 逐行 ``fromisoformat``（03 文档 §2.3）。
* **日期桶（``day_bucket`` 等）在写入时算好**，查询期绝不用 ``strftime``
  ——那会让索引失效。
"""

from __future__ import annotations

import re

SCHEMA_VERSION = 1

#: 未知前台（空闲、锁屏、被排除的应用）的哨兵应用。
#:
#: 03 文档 §2.5 原本写"``raw_key_events.app_id`` 为 NULL 表示未知"，但聚合表把
#: ``app_id`` 放进了主键，而 ``WITHOUT ROWID`` 表的主键列隐含 NOT NULL。两处用
#: 不同的表示会让"未知"在原始表与聚合表之间对不上账，因此统一用哨兵行 0。
UNKNOWN_APP_ID = 0
UNKNOWN_APP_NAME = "未知"

RAW_TABLE_RE = re.compile(r"^raw_key_events_\d{4}_\d{2}$")


def raw_table_name(month: str) -> str:
    """``"2026-08"`` → ``"raw_key_events_2026_08"``，并做白名单校验。

    表名无法参数化，这是全代码库唯一的动态 SQL 构造点（沿用 KeyTrace 的正则
    兜底思路）。任何不匹配的输入直接拒绝，绝不拼进 SQL。
    """
    table = f"raw_key_events_{month.replace('-', '_')}"
    if not RAW_TABLE_RE.fullmatch(table):
        raise ValueError(f"拒绝不安全的表名：{table!r}")
    return table


def raw_partition_ddl(month: str) -> tuple[str, ...]:
    """按月分表的建表与索引语句。分表让归档变成 ``DROP TABLE``（03 文档 §2.5）。"""
    table = raw_table_name(month)
    suffix = table.removeprefix("raw_key_events_")
    return (
        f"""
        CREATE TABLE IF NOT EXISTS {table} (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            key_id       TEXT    NOT NULL,
            app_id       INTEGER NOT NULL DEFAULT {UNKNOWN_APP_ID} REFERENCES app(id),
            down_ts_ns   INTEGER NOT NULL,
            up_ts_ns     INTEGER NOT NULL,
            duration_ms  REAL    NOT NULL,
            native_code  INTEGER,
            native_code2 INTEGER,
            hid_usage    INTEGER,
            confidence   INTEGER NOT NULL DEFAULT 2
        )
        """,
        f"CREATE INDEX IF NOT EXISTS idx_rke_{suffix}_down "
        f"ON {table}(down_ts_ns)",
        f"CREATE INDEX IF NOT EXISTS idx_rke_{suffix}_key_down "
        f"ON {table}(key_id, down_ts_ns)",
        f"CREATE INDEX IF NOT EXISTS idx_rke_{suffix}_app_down "
        f"ON {table}(app_id, down_ts_ns)",
    )


META_DDL = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
)
"""

APP_DDL = """
CREATE TABLE IF NOT EXISTS app (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    app_key         TEXT    NOT NULL,
    identity_kind   TEXT    NOT NULL,
    platform_id     TEXT    NOT NULL,
    process_name    TEXT    NOT NULL DEFAULT '',
    display_name    TEXT    NOT NULL,
    user_alias      TEXT,
    exe_path        TEXT    NOT NULL DEFAULT '',
    category        TEXT    NOT NULL DEFAULT 'uncategorized',
    category_source TEXT    NOT NULL DEFAULT 'auto',
    merged_into     INTEGER REFERENCES app(id),
    excluded        INTEGER NOT NULL DEFAULT 0,
    icon_state      TEXT    NOT NULL DEFAULT 'unknown',
    first_seen_at   TEXT    NOT NULL,
    last_seen_at    TEXT    NOT NULL,
    UNIQUE (platform_id, identity_kind, app_key)
)
"""

USAGE_SESSION_DDL = """
CREATE TABLE IF NOT EXISTS usage_session (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    app_id       INTEGER NOT NULL REFERENCES app(id),
    window_title TEXT    NOT NULL DEFAULT '',
    start_ts_ns  INTEGER NOT NULL,
    end_ts_ns    INTEGER NOT NULL,
    duration_ms  INTEGER NOT NULL,
    day_bucket   TEXT    NOT NULL,
    idle_trimmed INTEGER NOT NULL DEFAULT 0
)
"""

_AGG_APP_BUCKET_DDL = """
CREATE TABLE IF NOT EXISTS agg_app_{grain} (
    {bucket}      TEXT    NOT NULL,
    app_id        INTEGER NOT NULL,
    duration_ms   INTEGER NOT NULL DEFAULT 0,
    session_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY ({bucket}, app_id)
) WITHOUT ROWID
"""

AGG_APP_TOTAL_DDL = """
CREATE TABLE IF NOT EXISTS agg_app_total (
    app_id          INTEGER PRIMARY KEY,
    duration_ms     INTEGER NOT NULL DEFAULT 0,
    session_count   INTEGER NOT NULL DEFAULT 0,
    last_used_ts_ns INTEGER NOT NULL DEFAULT 0
) WITHOUT ROWID
"""

AGG_APP_HOUR_DDL = """
CREATE TABLE IF NOT EXISTS agg_app_hour (
    day_bucket  TEXT    NOT NULL,
    hour        INTEGER NOT NULL,
    app_id      INTEGER NOT NULL,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (day_bucket, hour, app_id)
) WITHOUT ROWID
"""

_AGG_KEY_BUCKET_DDL = """
CREATE TABLE IF NOT EXISTS agg_key_{grain} (
    bucket            TEXT NOT NULL,
    key_id            TEXT NOT NULL,
    press_count       INTEGER NOT NULL DEFAULT 0,
    duration_total_ms REAL    NOT NULL DEFAULT 0,
    duration_max_ms   REAL    NOT NULL DEFAULT 0,
    PRIMARY KEY (bucket, key_id)
) WITHOUT ROWID
"""

AGG_KEY_TOTAL_DDL = """
CREATE TABLE IF NOT EXISTS agg_key_total (
    key_id            TEXT PRIMARY KEY,
    press_count       INTEGER NOT NULL DEFAULT 0,
    duration_total_ms REAL    NOT NULL DEFAULT 0,
    duration_max_ms   REAL    NOT NULL DEFAULT 0
) WITHOUT ROWID
"""

AGG_KEY_HOUR_DDL = """
CREATE TABLE IF NOT EXISTS agg_key_hour (
    day_bucket        TEXT    NOT NULL,
    hour              INTEGER NOT NULL,
    key_id            TEXT    NOT NULL,
    press_count       INTEGER NOT NULL DEFAULT 0,
    duration_total_ms REAL    NOT NULL DEFAULT 0,
    PRIMARY KEY (day_bucket, hour, key_id)
) WITHOUT ROWID
"""

AGG_KEY_APP_DAY_DDL = """
CREATE TABLE IF NOT EXISTS agg_key_app_day (
    day_bucket        TEXT    NOT NULL,
    app_id            INTEGER NOT NULL,
    key_id            TEXT    NOT NULL,
    press_count       INTEGER NOT NULL DEFAULT 0,
    duration_total_ms REAL    NOT NULL DEFAULT 0,
    duration_max_ms   REAL    NOT NULL DEFAULT 0,
    PRIMARY KEY (day_bucket, app_id, key_id)
) WITHOUT ROWID
"""

AGG_APP_KEY_TOTAL_DDL = """
CREATE TABLE IF NOT EXISTS agg_app_key_total (
    app_id            INTEGER NOT NULL,
    key_id            TEXT    NOT NULL,
    press_count       INTEGER NOT NULL DEFAULT 0,
    duration_total_ms REAL    NOT NULL DEFAULT 0,
    duration_max_ms   REAL    NOT NULL DEFAULT 0,
    PRIMARY KEY (app_id, key_id)
) WITHOUT ROWID
"""

ARCHIVE_LOG_DDL = """
CREATE TABLE IF NOT EXISTS archive_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name TEXT    NOT NULL,
    action     TEXT    NOT NULL,
    row_count  INTEGER NOT NULL,
    file_path  TEXT,
    created_at TEXT    NOT NULL
)
"""

HEALTH_STAT_DDL = """
CREATE TABLE IF NOT EXISTS health_stat (
    day_bucket          TEXT PRIMARY KEY,
    dropped_events      INTEGER NOT NULL DEFAULT 0,
    write_errors        INTEGER NOT NULL DEFAULT 0,
    capture_downtime_ms INTEGER NOT NULL DEFAULT 0
)
"""

CAPTURE_CAPABILITY_DDL = """
CREATE TABLE IF NOT EXISTS capture_capability (
    day_bucket           TEXT    NOT NULL,
    platform_id          TEXT    NOT NULL,
    keyboard_backend     TEXT    NOT NULL,
    foreground_available INTEGER NOT NULL,
    titles_recorded      INTEGER NOT NULL,
    key_position_stable  INTEGER NOT NULL,
    first_seen_at        TEXT    NOT NULL,
    last_seen_at         TEXT    NOT NULL,
    PRIMARY KEY (day_bucket, platform_id, keyboard_backend,
                 foreground_available, key_position_stable)
) WITHOUT ROWID
"""

INDEXES: tuple[str, ...] = (
    "CREATE INDEX IF NOT EXISTS idx_app_category  ON app(category) WHERE excluded = 0",
    "CREATE INDEX IF NOT EXISTS idx_app_last_seen ON app(last_seen_at DESC) WHERE excluded = 0",
    "CREATE INDEX IF NOT EXISTS idx_session_day     ON usage_session(day_bucket)",
    "CREATE INDEX IF NOT EXISTS idx_session_app_day ON usage_session(app_id, day_bucket)",
    "CREATE INDEX IF NOT EXISTS idx_session_start   ON usage_session(start_ts_ns)",
    "CREATE INDEX IF NOT EXISTS idx_agg_app_total_dur  ON agg_app_total(duration_ms DESC)",
    "CREATE INDEX IF NOT EXISTS idx_agg_app_total_last ON agg_app_total(last_used_ts_ns DESC)",
    "CREATE INDEX IF NOT EXISTS idx_agg_kad_app ON agg_key_app_day(app_id, day_bucket)",
)

TABLES: tuple[str, ...] = (
    META_DDL,
    APP_DDL,
    USAGE_SESSION_DDL,
    _AGG_APP_BUCKET_DDL.format(grain="day", bucket="day_bucket"),
    _AGG_APP_BUCKET_DDL.format(grain="month", bucket="month_bucket"),
    _AGG_APP_BUCKET_DDL.format(grain="year", bucket="year_bucket"),
    AGG_APP_TOTAL_DDL,
    AGG_APP_HOUR_DDL,
    _AGG_KEY_BUCKET_DDL.format(grain="day"),
    _AGG_KEY_BUCKET_DDL.format(grain="month"),
    _AGG_KEY_BUCKET_DDL.format(grain="year"),
    AGG_KEY_TOTAL_DDL,
    AGG_KEY_HOUR_DDL,
    AGG_KEY_APP_DAY_DDL,
    AGG_APP_KEY_TOTAL_DDL,
    ARCHIVE_LOG_DDL,
    HEALTH_STAT_DDL,
    CAPTURE_CAPABILITY_DDL,
)

#: 期望存在的表名，供测试与启动自检比对。
EXPECTED_TABLES: frozenset[str] = frozenset(
    {
        "meta",
        "app",
        "usage_session",
        "agg_app_day",
        "agg_app_month",
        "agg_app_year",
        "agg_app_total",
        "agg_app_hour",
        "agg_key_day",
        "agg_key_month",
        "agg_key_year",
        "agg_key_total",
        "agg_key_hour",
        "agg_key_app_day",
        "agg_app_key_total",
        "archive_log",
        "health_stat",
        "capture_capability",
    }
)
