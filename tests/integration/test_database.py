"""建库、迁移与分表。

M0 完成判据里"全新目录首次运行自动生成配置与数据库，表结构与 03 文档一致"
这一条由本文件固定。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from omnisight.storage import capability, schema
from omnisight.storage.database import Database, SchemaTooNewError
from omnisight.storage.migrations import TARGET_VERSION, migrate


def test_fresh_database_has_exactly_the_documented_tables(database: Database):
    assert database.table_names() == schema.EXPECTED_TABLES


def test_schema_version_recorded(database: Database):
    assert database.schema_version() == TARGET_VERSION


def test_migrate_is_idempotent(database: Database):
    assert migrate(database) == TARGET_VERSION
    assert migrate(database) == TARGET_VERSION


def test_unknown_app_sentinel_exists(database: Database):
    """键盘总量必须守恒：空闲/被排除应用期间的按键归到 app_id = 0。"""
    row = (
        database.connect()
        .execute("SELECT * FROM app WHERE id = ?", (schema.UNKNOWN_APP_ID,))
        .fetchone()
    )
    assert row is not None
    assert row["display_name"] == schema.UNKNOWN_APP_NAME


def test_autoincrement_starts_after_sentinel(database: Database):
    now = datetime.now(UTC).isoformat()
    with database.transaction() as conn:
        conn.execute(
            "INSERT INTO app (app_key, identity_kind, platform_id, display_name,"
            " first_seen_at, last_seen_at) VALUES ('code.exe','process','windows','Code',?,?)",
            (now, now),
        )
    app_id = (
        database.connect()
        .execute("SELECT id FROM app WHERE app_key='code.exe'")
        .fetchone()["id"]
    )
    assert app_id > schema.UNKNOWN_APP_ID


def test_app_identity_is_unique_per_platform_and_kind(database: Database):
    """同一个逻辑应用在两个系统上是两行，靠 merged_into 手工归并（03 文档 §2.2）。"""
    now = datetime.now(UTC).isoformat()
    with database.transaction() as conn:
        conn.execute(
            "INSERT INTO app (app_key, identity_kind, platform_id, display_name,"
            " first_seen_at, last_seen_at) VALUES ('code.exe','process','windows','Code',?,?)",
            (now, now),
        )
        conn.execute(
            "INSERT INTO app (app_key, identity_kind, platform_id, display_name,"
            " first_seen_at, last_seen_at) VALUES"
            " ('com.microsoft.VSCode','bundle','macos','Code',?,?)",
            (now, now),
        )
    assert database.connect().execute("SELECT COUNT(*) c FROM app").fetchone()["c"] == 3


def test_wal_and_secure_delete_are_enabled(database: Database):
    conn = database.connect()
    assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    assert conn.execute("PRAGMA secure_delete").fetchone()[0] == 1
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    # DROP 老月表后靠 incremental_vacuum 回收，不需要重写整库（03 文档 §6）。
    assert conn.execute("PRAGMA auto_vacuum").fetchone()[0] == 2


def test_raw_partition_can_be_created_on_demand(database: Database):
    with database.transaction() as conn:
        for statement in schema.raw_partition_ddl("2026-09"):
            conn.execute(statement)
    assert database.table_exists("raw_key_events_2026_09")


def test_partition_defaults_app_id_to_unknown(database: Database):
    with database.transaction() as conn:
        for statement in schema.raw_partition_ddl("2026-09"):
            conn.execute(statement)
        conn.execute(
            "INSERT INTO raw_key_events_2026_09 (key_id, down_ts_ns, up_ts_ns, duration_ms)"
            " VALUES ('key_a', 1, 2, 1.0)"
        )
    row = database.connect().execute("SELECT app_id FROM raw_key_events_2026_09").fetchone()
    assert row["app_id"] == schema.UNKNOWN_APP_ID


def test_forward_compatibility_guard(database: Database):
    """用户装了新版又退回旧版时，旧版必须报错而不是在陌生 schema 上乱写。"""
    database.meta_set("schema_version", str(TARGET_VERSION + 5))
    with pytest.raises(SchemaTooNewError):
        migrate(database)


def test_migration_backs_up_before_upgrading(tmp_path: Path, monkeypatch):
    """升级一个已有数据的库之前必须留下备份——这是回滚的唯一保险。

    用一条假的 m002 来模拟"下一个版本"，而不是把 ``schema_version`` 改回 0：
    后者是新建库的状态，此时无数据可丢，备份反而是多余的。
    """
    import omnisight.storage.migrations as migrations

    db = Database(tmp_path / "omnisight.db")
    migrate(db)

    applied: list[int] = []
    future = migrations.Migration(
        TARGET_VERSION + 1, "fake next version", lambda conn: applied.append(1)
    )
    monkeypatch.setattr(migrations, "MIGRATIONS", (*migrations.MIGRATIONS, future))
    monkeypatch.setattr(migrations, "TARGET_VERSION", future.version)

    assert migrations.migrate(db) == future.version
    assert applied == [1]
    assert list((tmp_path / "backup").glob("*/omnisight.db")), "升级前没有备份"
    db.close()


def test_transaction_rolls_back_on_error(database: Database):
    now = datetime.now(UTC).isoformat()
    with pytest.raises(RuntimeError), database.transaction() as conn:
        conn.execute(
            "INSERT INTO app (app_key, identity_kind, platform_id, display_name,"
            " first_seen_at, last_seen_at) VALUES ('x','process','windows','X',?,?)",
            (now, now),
        )
        raise RuntimeError("boom")
    remaining = (
        database.connect()
        .execute("SELECT COUNT(*) c FROM app WHERE app_key='x'")
        .fetchone()["c"]
    )
    assert remaining == 0


def test_quick_check_passes_on_healthy_database(database: Database):
    assert database.quick_check() is True


def test_backup_produces_a_readable_copy(database: Database, tmp_path: Path):
    target = database.backup_to(tmp_path / "copy" / "omnisight.db")
    clone = Database(target)
    assert clone.schema_version() == TARGET_VERSION
    clone.close()


def test_capability_rows_split_by_backend(database: Database):
    """同一天换过后端要留下两行，如实反映"上午一种、下午另一种"。"""
    now = datetime.now(UTC)
    day = capability.day_bucket(now)
    with database.transaction() as conn:
        capability.upsert(
            conn, day_bucket=day, platform_id="windows", keyboard_backend="raw_input",
            foreground_available=True, titles_recorded=False, key_position_stable=True, now=now,
        )
        capability.upsert(
            conn, day_bucket=day, platform_id="windows", keyboard_backend="pynput",
            foreground_available=True, titles_recorded=False, key_position_stable=False,
            now=now + timedelta(hours=1),
        )
    rows = database.connect().execute(
        "SELECT keyboard_backend FROM capture_capability ORDER BY keyboard_backend"
    ).fetchall()
    assert [r["keyboard_backend"] for r in rows] == ["pynput", "raw_input"]


def test_titles_recorded_is_never_downgraded(database: Database):
    """当天记过标题就是记过了，之后关掉开关也不能把这个事实抹掉。"""
    now = datetime.now(UTC)
    day = capability.day_bucket(now)
    common = dict(
        day_bucket=day, platform_id="windows", keyboard_backend="raw_input",
        foreground_available=True, key_position_stable=True,
    )
    with database.transaction() as conn:
        capability.upsert(conn, titles_recorded=True, now=now, **common)
        capability.upsert(conn, titles_recorded=False, now=now + timedelta(minutes=5), **common)
    row = database.connect().execute("SELECT titles_recorded FROM capture_capability").fetchone()
    assert row["titles_recorded"] == 1
