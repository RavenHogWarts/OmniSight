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

SCHEMA_VERSION = 2

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
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    app_id            INTEGER NOT NULL REFERENCES app(id),
    window_title      TEXT    NOT NULL DEFAULT '',
    start_ts_ns       INTEGER NOT NULL,
    end_ts_ns         INTEGER NOT NULL,
    duration_ms       INTEGER NOT NULL,
    day_bucket        TEXT    NOT NULL,
    idle_trimmed      INTEGER NOT NULL DEFAULT 0,
    end_reason        TEXT    NOT NULL DEFAULT 'switch',
    visit_start_ts_ns INTEGER NOT NULL DEFAULT 0
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

#: 日粒度独有的两列。
#:
#: ``longest_visit_ms``：月/年/总的最长访问就是各日之最大值，而心跳落盘让
#: ``MAX(usage_session.duration_ms)`` 恒等于心跳间隔（见 ``UsageSession.visit_duration_ms``），
#: 因此这一列必须由写入侧维护。
#:
#: ``press_count``：同一事实在 ``agg_key_app_day`` 里按 (日, 应用, **键**) 存，而
#: "这个应用这段时间按了多少次"用不到键维度——一年 480k 行 vs 4.4k 行（实测 46ms → <1ms）。
#: 这个查询在 ``/usage/period`` / ``/apps`` / ``/overview`` / ``/insights/app-keyboard``
#: 上都要跑，是 M2 基准里第二大的单项开销。**只加在日粒度**：月/年区间由日行汇总即可
#: （一年 4.4k 行），再复制到月/年表得不偿失。
AGG_APP_DAY_EXTRA_COLUMNS: tuple[tuple[str, str], ...] = (
    ("longest_visit_ms", "INTEGER NOT NULL DEFAULT 0"),
    ("press_count", "INTEGER NOT NULL DEFAULT 0"),
)

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

#: 每分钟的按键总数。**为 ``peak_kpm`` 而存在**：05 文档 §5 要求给出峰值 KPM
#: 及其发生时刻（分钟精度），而小时聚合只能给出"某小时的平均 KPM"——把平均值
#: 叫成峰值是在编数据。一天最多 1440 行（≈6 MB/年），代价与它换来的诚实相称。
#: 同时它也是 ``active_hours.first/last``（"09:12"）的唯一数据来源。
#: 小时粒度的**键无关**按键总量。``agg_key_hour`` 已经按 (日, 小时, 键) 存了同样的事实，
#: 但"我一般几点在敲键盘"这个问题不需要按键拆分，而按键拆分让它贵了一百倍：三年
#: 是 2.9M 行 vs 26k 行（实测 200ms → <1ms）。这个查询出现在 ``/usage/timeline`` 与
#: ``/overview`` 的高亮里，是 M2 基准里最大的单项开销，因此值得一张表。
#:
#: ``agg_key_hour`` 保留给"某一个键的小时分布"与"某一天按键的小时分布"——那两处确实
#: 需要按键维度。
AGG_PRESS_HOUR_DDL = """
CREATE TABLE IF NOT EXISTS agg_press_hour (
    day_bucket        TEXT    NOT NULL,
    hour              INTEGER NOT NULL,
    press_count       INTEGER NOT NULL DEFAULT 0,
    duration_total_ms REAL    NOT NULL DEFAULT 0,
    PRIMARY KEY (day_bucket, hour)
) WITHOUT ROWID
"""

AGG_PRESS_MINUTE_DDL = """
CREATE TABLE IF NOT EXISTS agg_press_minute (
    day_bucket  TEXT    NOT NULL,
    minute      INTEGER NOT NULL,
    press_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (day_bucket, minute)
) WITHOUT ROWID
"""

#: 图标缓存。**不放进 ``app`` 维表**：几乎每个查询都要 JOIN ``app`` 取展示名，
#: 而 SQLite 的行是内联存储的——把几十 KB 的 PNG 塞进去会把 ``app`` 的行挤到
#: 溢出页上，让所有查询变慢。04 文档 §6"改动一"要的是"解析结果持久化"，独立表
#: 同样满足，且顺带让"清空图标缓存"变成一句 DELETE。
#:
#: ``png IS NULL`` = 解析失败；``failed_at`` 使失败可以在 7 天后重试（"改动三"：
#: 现状把失败永久缓存为 ``b""``，用户装好程序后图标永远不出现）。
APP_ICON_DDL = """
CREATE TABLE IF NOT EXISTS app_icon (
    app_id      INTEGER PRIMARY KEY REFERENCES app(id),
    png         BLOB,
    size        INTEGER NOT NULL DEFAULT 0,
    source_path TEXT    NOT NULL DEFAULT '',
    resolved_at TEXT    NOT NULL,
    failed_at   TEXT
)
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
    # 一次"访问"在库里就是 end_reason <> 'heartbeat' 的那一行。部分索引让"某周期的
    # 访问列表"只扫访问数（几百行/天）而不是会话段数（心跳每 10 秒一段，8000 行/天）。
    "CREATE INDEX IF NOT EXISTS idx_session_visits ON usage_session(day_bucket, app_id) "
    "WHERE end_reason <> 'heartbeat'",
    "CREATE INDEX IF NOT EXISTS idx_agg_app_total_dur  ON agg_app_total(duration_ms DESC)",
    "CREATE INDEX IF NOT EXISTS idx_agg_app_total_last ON agg_app_total(last_used_ts_ns DESC)",
    "CREATE INDEX IF NOT EXISTS idx_agg_kad_app ON agg_key_app_day(app_id, day_bucket)",
    # 下面两条都是同一个形状的问题：聚合表的主键把日期放在最前（写入侧要顺序追加），
    # 而"某一个键在这段时间里"的查询需要先按键定位。没有反向索引时它们要扫掉整个日期
    # 范围内的全部键。两条索引都**带上被查询的列**（覆盖索引）——WITHOUT ROWID 表的
    # 索引回表是一次主键 seek，26k 次 seek 就是 24ms，而覆盖之后是 0。
    "CREATE INDEX IF NOT EXISTS idx_agg_key_hour_key ON agg_key_hour"
    "(key_id, day_bucket, hour, press_count, duration_total_ms)",
    "CREATE INDEX IF NOT EXISTS idx_agg_kad_key ON agg_key_app_day"
    "(key_id, day_bucket, app_id, press_count, duration_total_ms)",
)

def _agg_app_day_ddl() -> str:
    """在通用模板上追加日粒度独有的列，避免为一张表复制整段 DDL。"""
    extra = "".join(f",{chr(10)}    {name} {decl}" for name, decl in AGG_APP_DAY_EXTRA_COLUMNS)
    base = _AGG_APP_BUCKET_DDL.format(grain="day", bucket="day_bucket")
    return base.replace(
        "    session_count INTEGER NOT NULL DEFAULT 0,",
        f"    session_count INTEGER NOT NULL DEFAULT 0{extra},",
    )


TABLES: tuple[str, ...] = (
    META_DDL,
    APP_DDL,
    USAGE_SESSION_DDL,
    _agg_app_day_ddl(),
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
    AGG_PRESS_HOUR_DDL,
    AGG_PRESS_MINUTE_DDL,
    APP_ICON_DDL,
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
        "agg_press_hour",
        "agg_press_minute",
        "app_icon",
        "archive_log",
        "health_stat",
        "capture_capability",
    }
)
