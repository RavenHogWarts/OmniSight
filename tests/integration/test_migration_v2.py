"""m002：v1 库升到 v2（03 文档 §8、09 文档）。

M2 的查询层需要三样 v1 没有的东西：``usage_session`` 的访问起点、``agg_app_day`` 的两个
派生列、以及三张新表。这个文件盯住两件事：

1. **升级不丢数据**，且能在真实的 v1 结构上跑（不是在已经是 v2 的库上跑一遍空操作）；
2. **不回填历史**。v1 期间没有记录访问起点，无法事后推断哪些段属于同一次访问；硬猜会把
   "最长使用 3 小时"这类结论建立在编造的数据上。这是一个刻意的取舍，因此必须有断言，
   否则日后某次"顺手补一下历史数据"就悄悄发生了。
"""

from __future__ import annotations

import pytest

from omnisight.storage import schema
from omnisight.storage.database import Database, SchemaTooNewError
from omnisight.storage.migrations import TARGET_VERSION, m001_initial, m002_query_support, migrate

#: v1 里没有的列与表。清单从生产代码里取，避免测试与实现各写一份。
V2_COLUMNS = m002_query_support.ADDED_COLUMNS
V2_TABLES = ("agg_press_hour", "agg_press_minute", "app_icon")


@pytest.fixture
def v1_database(tmp_path) -> Database:
    """一个**真正的 v1 库**：只跑 m001，然后把 v2 的列与表拆掉。

    直接调 ``m001_initial.up`` 拿到的已经是当前的 DDL（m001 会跟着 schema.py 一起演进），
    因此这里显式退回 v1 形态——否则这组用例测的是"在 v2 上再跑一次 m002"，永远绿。
    """
    db = Database(tmp_path / "v1.db")
    with db.transaction() as conn:
        m001_initial.up(conn)
        conn.execute("DROP TABLE IF EXISTS agg_app_day")
        conn.execute(
            "CREATE TABLE agg_app_day ("
            "  day_bucket TEXT NOT NULL, app_id INTEGER NOT NULL,"
            "  duration_ms INTEGER NOT NULL DEFAULT 0,"
            "  session_count INTEGER NOT NULL DEFAULT 0,"
            "  PRIMARY KEY (day_bucket, app_id)) WITHOUT ROWID"
        )
        conn.execute("DROP TABLE IF EXISTS usage_session")
        conn.execute(
            "CREATE TABLE usage_session ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  app_id INTEGER NOT NULL REFERENCES app(id),"
            "  window_title TEXT NOT NULL DEFAULT '',"
            "  start_ts_ns INTEGER NOT NULL, end_ts_ns INTEGER NOT NULL,"
            "  duration_ms INTEGER NOT NULL DEFAULT 0,"
            "  day_bucket TEXT NOT NULL,"
            "  idle_trimmed INTEGER NOT NULL DEFAULT 0)"
        )
        for table in V2_TABLES:
            conn.execute(f"DROP TABLE IF EXISTS {table}")
        conn.execute("INSERT INTO app (id, app_key, identity_kind, platform_id, process_name, "
                     "display_name, first_seen_at, last_seen_at) "
                     "VALUES (7, 'code.exe', 'process', 'windows', 'code.exe', 'Code', '', '')")
        conn.execute(
            "INSERT INTO usage_session (app_id, window_title, start_ts_ns, end_ts_ns, "
            "duration_ms, day_bucket, idle_trimmed) VALUES (7, '', 1000, 11000, 10, "
            "'2026-08-01', 0)"
        )
        conn.execute(
            "INSERT INTO agg_app_day (day_bucket, app_id, duration_ms, session_count) "
            "VALUES ('2026-08-01', 7, 600000, 42)"
        )
    db.meta_set("schema_version", "1")
    yield db
    db.close()


def _columns(db: Database, table: str) -> set[str]:
    return {row[1] for row in db.connect().execute(f"PRAGMA table_info({table})")}


def test_the_v1_fixture_really_is_v1(v1_database: Database):
    """保护下面所有用例：夹具一旦"已经是 v2"，它们会全部静默通过。"""
    assert v1_database.schema_version() == 1
    assert "visit_start_ts_ns" not in _columns(v1_database, "usage_session")
    assert "press_count" not in _columns(v1_database, "agg_app_day")
    for table in V2_TABLES:
        assert not v1_database.table_exists(table)


def test_migration_adds_every_column_and_table(v1_database: Database):
    assert migrate(v1_database) == TARGET_VERSION
    for table, column, _decl in V2_COLUMNS:
        assert column in _columns(v1_database, table), f"{table}.{column} 没建出来"
    for table in V2_TABLES:
        assert v1_database.table_exists(table)
    assert v1_database.table_names() >= schema.EXPECTED_TABLES


def test_migration_preserves_existing_rows(v1_database: Database):
    migrate(v1_database)
    conn = v1_database.connect()
    row = conn.execute("SELECT app_id, duration_ms, day_bucket FROM usage_session").fetchone()
    assert (row["app_id"], row["duration_ms"], row["day_bucket"]) == (7, 10, "2026-08-01")
    agg = conn.execute("SELECT duration_ms, session_count FROM agg_app_day").fetchone()
    assert (agg["duration_ms"], agg["session_count"]) == (600000, 42)


def test_migration_does_not_invent_history(v1_database: Database):
    """v1 的日子里访问起点确实不存在。默认值必须是"未知"，不是一个猜出来的数。"""
    migrate(v1_database)
    conn = v1_database.connect()
    row = conn.execute(
        "SELECT end_reason, visit_start_ts_ns FROM usage_session"
    ).fetchone()
    assert row["visit_start_ts_ns"] == 0, "0 = 未记录，由模型回退到 start_ts_ns"
    assert row["end_reason"] == "switch"
    derived = conn.execute("SELECT longest_visit_ms, press_count FROM agg_app_day").fetchone()
    assert derived["longest_visit_ms"] == 0
    assert derived["press_count"] == 0


def test_migration_is_idempotent(v1_database: Database):
    assert migrate(v1_database) == TARGET_VERSION
    assert migrate(v1_database) == TARGET_VERSION
    m002_query_support.up(v1_database.connect())  # 直接重放也不该炸
    assert v1_database.schema_version() == TARGET_VERSION


def test_migration_backs_up_first(v1_database: Database, tmp_path):
    """降级或回滚时唯一的保险。"""
    migrate(v1_database)
    backups = list((tmp_path / "backup").rglob("v1.db"))
    assert backups, "升级前没有备份"


def test_a_newer_database_is_refused_rather_than_written_to(v1_database: Database):
    """用户装了新版又退回旧版时必须明确报错，而不是在不认识的 schema 上继续写。"""
    v1_database.meta_set("schema_version", str(TARGET_VERSION + 5))
    with pytest.raises(SchemaTooNewError):
        migrate(v1_database)


def test_a_fresh_database_lands_directly_on_v2(database: Database):
    """全新库由 m001 建成当前结构，m002 只是发现列与表都已存在并跳过。"""
    assert database.schema_version() == TARGET_VERSION
    for table, column, _decl in V2_COLUMNS:
        assert column in _columns(database, table)
