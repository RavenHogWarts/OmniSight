"""旧数据导入的端到端测试（03 文档 §7、09 文档 §6 的验收清单）。

对照 M5 的完成判据：

* 计数可核对——逐格断言聚合表的具体数字，不查"字段存在"；
* 旧库文件只读——导入前后 sha256 与 mtime 相等；
* 断点续传——跑到一半取消，续传后无重复；
* 冲突以 KeyTrace 为准——重叠日的 TimeLens 按键计数被跳过且记录在案；
* 撤销——**对照库比对**：撤销后的全部聚合表与"从未导入过"的纯库逐行相等，
  这是比任何单点断言都强的验证（含重叠日的新采集保留、含 store_raw 关闭
  期间的无支撑量保留）。
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest

from legacy_dbs import (
    TZ,
    make_keytrace_db,
    make_timelens_db,
    timelens_row,
    tz_noon_ns,
)
from omnisight.storage.migrations import m003_import_legacy as m003
from omnisight.storage.migrations.m003_import_legacy import LegacyImporter, load_state

# ── 测试数据集 ───────────────────────────────────────────────────────────
#: 三个互不重叠的"角色日"：
#: * D_TL_KEY / D_KT：只有一方有数据 → 各自导入；
#: * D_BOTH（= seeded 的 2026-09-01）：两边都有 + 新采集也在 → 冲突 + 重叠重算。
D_TL_KEY = "2026-08-15"   # 只有 TimeLens key_usage
D_KT = "2026-08-14"       # 只有 KeyTrace 事件
D_BOTH = "2026-09-01"     # 冲突日（撤销测试里还叠着 seeded 的新采集）
D_TL_SESSIONS = "2026-08-16"

TL_SESSIONS = [
    # chrome 连续三段（间隙 1 秒 ≤ 15 秒）= 同一次访问的三个心跳段。
    timelens_row(D_TL_SESSIONS, "Google Chrome", "chrome.exe", "12:00:00", 10.0,
                 title="键迹 KeyTrace - Google Chrome", exe=r"C:\Chrome\chrome.exe"),
    timelens_row(D_TL_SESSIONS, "Google Chrome", "chrome.exe", "12:00:11", 10.0),
    timelens_row(D_TL_SESSIONS, "Google Chrome", "chrome.exe", "12:00:22", 8.0),
    # 隔了五分钟：一次新的访问。
    timelens_row(D_TL_SESSIONS, "Visual Studio Code", "code.exe", "12:05:00", 5.0),
]

TL_KEY_USAGE = [
    (D_TL_KEY, 10, "Space", 5),
    (D_TL_KEY, 10, "A", 3),
    (D_TL_KEY, 11, "\x01", 4),      # Ctrl+A 的控制字符 → 与 "A" 聚成 key_a
    (D_TL_KEY, 11, "Fn", 2),        # 无法映射 → unmapped
    (D_BOTH, 9, "Space", 9),        # 冲突日 → 跳过
]

KT_EVENTS = [
    (D_KT, "key_c", tz_noon_ns(D_KT, 12), 50.0, 46, 67),
    (D_KT, "key_c", tz_noon_ns(D_KT, 12) + 1_000_000_000, 60.0, 46, 67),
    (D_KT, "key_c", tz_noon_ns(D_KT, 12) + 2_000_000_000, 70.0, 46, 67),
    (D_KT, "enter", tz_noon_ns(D_KT, 13), 100.0, 28, 13),
    (D_BOTH, "space", tz_noon_ns(D_BOTH, 12), 10.0, 57, 32),
    (D_BOTH, "space", tz_noon_ns(D_BOTH, 12) + 1_000_000_000, 20.0, 57, 32),
]


def _sources(tmp_path: Path) -> dict[str, Path]:
    return {
        "timelens": make_timelens_db(
            tmp_path / "usage.db", sessions=TL_SESSIONS, key_usage=TL_KEY_USAGE
        ),
        "keytrace": make_keytrace_db(tmp_path / "keytrace.sqlite3", events=KT_EVENTS),
    }


def _file_digest(path: Path) -> tuple[str, float]:
    stat = path.stat()
    return (hashlib.sha256(path.read_bytes()).hexdigest(), stat.st_mtime_ns)


def _rows(db, sql: str, params: tuple = ()) -> list[tuple]:
    return [tuple(row) for row in db.connect().execute(sql, params).fetchall()]


# ── 完整导入：计数可核对 ────────────────────────────────────────────────


def test_full_import_counts_are_verifiable(database, tmp_path):
    sources = _sources(tmp_path)
    before = {name: _file_digest(path) for name, path in sources.items()}
    state: dict = {}
    LegacyImporter(database, tz=TZ).run(state, sources, tmp_path / "backup")

    # 会话：4 行（TimeLens 的每一段都是一行），但访问只有 2 次。
    assert _rows(database, "SELECT COUNT(*) FROM usage_session")[0][0] == 4
    assert _rows(database, "SELECT COUNT(*) FROM usage_session"
                         " WHERE end_reason <> 'heartbeat'")[0][0] == 2
    # 一次访问 = 开启段（visit_start == start）恰有一个。
    assert _rows(database, "SELECT COUNT(*) FROM usage_session"
                         " WHERE visit_start_ts_ns = start_ts_ns")[0][0] == 2
    # 心跳段带着递增的访问起点——最后一段的 visit 时长 = 整次访问（30 秒：
    # 10s 段 + 1s 隙 + 10s 段 + 1s 隙 + 8s 段）。
    assert _rows(
        database,
        "SELECT MAX((end_ts_ns - visit_start_ts_ns) / 1000000) FROM usage_session"
        " WHERE day_bucket = ?",
        (D_TL_SESSIONS,),
    )[0][0] == 30000

    # 键盘聚合：day 级逐格断言。
    key_day = {
        (day, key): (count, total, maximum)
        for day, key, count, total, maximum in _rows(
            database, "SELECT bucket, key_id, press_count, duration_total_ms,"
                      " duration_max_ms FROM agg_key_day"
        )
    }
    assert key_day[(D_TL_KEY, "space")] == (5, 0.0, 0.0)     # 无时长：如实为 0
    assert key_day[(D_TL_KEY, "key_a")] == (7, 0.0, 0.0)     # "A"×3 + Ctrl+A("\x01")×4
    assert key_day[(D_KT, "key_c")] == (3, 180.0, 70.0)
    assert key_day[(D_KT, "enter")] == (1, 100.0, 100.0)
    # 冲突日：TimeLens 的 Space×9 被跳过，只有 KeyTrace 的 space×2。
    assert key_day[(D_BOTH, "space")] == (2, 30.0, 20.0)
    assert (D_BOTH, "key_a") not in key_day

    # 总计与月/年派生。
    key_total = dict(
        (key, count) for key, count in _rows(
            database, "SELECT key_id, press_count FROM agg_key_total")
    )
    assert key_total == {"space": 7, "key_a": 7, "key_c": 3, "enter": 1}
    assert dict(
        (bucket, count) for bucket, count in _rows(
            database, "SELECT bucket, SUM(press_count) FROM agg_key_month"
                      " GROUP BY bucket")
    ) == {"2026-08": 16, "2026-09": 2}

    # 原始事件：KeyTrace 的 6 条，两张月表。
    assert _rows(database, "SELECT COUNT(*) FROM raw_key_events_2026_08")[0][0] == 4
    assert _rows(database, "SELECT COUNT(*) FROM raw_key_events_2026_09")[0][0] == 2
    # 导入行无归因：app_id = 0、confidence = 0。
    assert _rows(database, "SELECT COUNT(*) FROM raw_key_events_2026_08"
                         " WHERE app_id = 0 AND confidence = 0")[0][0] == 4

    # 未映射键与跳过日记录在案（09 文档 §2.3：不静默丢弃）。
    assert state["counts"]["unmapped_keys"] == {"Fn": 2}
    assert state["skipped_days"] == [D_BOTH]

    # capability 行（09 文档 §2.4 的表）。
    caps = {
        (day, backend, foreground, stable)
        for day, backend, foreground, stable in _rows(
            database,
            "SELECT day_bucket, keyboard_backend, foreground_available,"
            " key_position_stable FROM capture_capability",
        )
    }
    assert caps == {
        (D_TL_SESSIONS, "none", 1, 0),
        (D_TL_KEY, "pynput_legacy", 0, 0),
        (D_KT, "raw_input", 0, 1),
        (D_BOTH, "raw_input", 0, 1),
    }

    # 旧库文件字节级未变（判据 3）。
    assert {name: _file_digest(path) for name, path in sources.items()} == before

    # 备份快照存在（判据 4 的前半：data/backup/<ts>/）。
    backup = Path(state["backup_dir"])
    assert (backup / "usage.db").is_file()
    assert (backup / "keytrace.sqlite3").is_file()


def test_tl_key_usage_only_lands_in_aggregates_not_raw(database, tmp_path):
    """只导 TimeLens：没有任何原始事件表被创建（不伪造原始事件，03 文档 §7.3）。"""
    tl = make_timelens_db(
        tmp_path / "usage.db", sessions=[], key_usage=[(D_TL_KEY, 10, "Space", 5)]
    )
    state: dict = {}
    LegacyImporter(database, tz=TZ).run(state, {"timelens": tl, "keytrace": None},
                                        tmp_path / "backup")
    assert _rows(database, "SELECT SUM(press_count) FROM agg_key_day")[0][0] == 5
    assert database.table_names().isdisjoint(
        {"raw_key_events_2026_08"}
    )


def test_keytrace_only_imports_raw_and_recomputes_aggregates(database, tmp_path):
    kt = make_keytrace_db(tmp_path / "kt.sqlite3", events=KT_EVENTS[:4])
    state: dict = {}
    LegacyImporter(database, tz=TZ).run(state, {"timelens": None, "keytrace": kt},
                                        tmp_path / "backup")
    assert _rows(database, "SELECT COUNT(*) FROM raw_key_events_2026_08")[0][0] == 4
    # 聚合从原始事件重算，而不是复制旧库的聚合表（03 文档 §7.4）。
    assert _rows(database, "SELECT press_count, duration_total_ms, duration_max_ms"
                         " FROM agg_key_day WHERE key_id = 'key_c'") == [(3, 180.0, 70.0)]


# ── 断点续传 ─────────────────────────────────────────────────────────────


def test_interrupted_import_resumes_without_duplicates(database, tmp_path, monkeypatch):
    monkeypatch.setattr(m003, "SESSION_BATCH", 2)
    monkeypatch.setattr(m003, "KEY_USAGE_BATCH", 2)
    monkeypatch.setattr(m003, "RAW_BATCH", 2)
    sources = _sources(tmp_path)
    backup = tmp_path / "backup"

    calls = {"n": 0}

    def cancel_after_two_batches() -> bool:
        calls["n"] += 1
        return calls["n"] > 2

    state: dict = {}
    with pytest.raises(m003.ImportCancelled):
        LegacyImporter(database, tz=TZ).run(
            state, sources, backup, cancel_check=cancel_after_two_batches
        )
    partial_sessions = _rows(database, "SELECT COUNT(*) FROM usage_session")[0][0]
    assert 0 < partial_sessions < 4, "取消应当发生在中途"
    assert load_state(database)["cursors"]["tl_usage_id"] > 0

    # 续传：不重新开始，从中断点继续。
    LegacyImporter(database, tz=TZ).run(state, sources, backup)
    assert _rows(database, "SELECT COUNT(*) FROM usage_session")[0][0] == 4
    assert _rows(database, "SELECT COUNT(*) FROM raw_key_events_2026_08")[0][0] == 4
    assert _rows(database, "SELECT COUNT(*) FROM raw_key_events_2026_09")[0][0] == 2
    assert dict(
        (key, count) for key, count in _rows(
            database, "SELECT key_id, press_count FROM agg_key_total")
    ) == {"space": 7, "key_a": 7, "key_c": 3, "enter": 1}


# ── 撤销：对照库比对 ────────────────────────────────────────────────────

AGGREGATE_TABLES = (
    "agg_key_day", "agg_key_month", "agg_key_year", "agg_key_total",
    "agg_key_hour", "agg_key_app_day", "agg_app_key_total",
    "agg_app_day", "agg_app_month", "agg_app_year", "agg_app_total",
    "agg_app_hour", "agg_press_hour", "agg_press_minute",
)


def _dump_aggregates(db) -> dict[str, list[tuple]]:
    return {
        table: sorted(_rows(db, f"SELECT * FROM {table}"))
        for table in AGGREGATE_TABLES
    }


def test_undo_restores_the_pure_database_exactly(database, tmp_path):
    """撤销后全部聚合表与"从未导入"的纯库逐行相等（含重叠日的新采集保留）。"""
    import seeded

    seeded.seed(database)  # 新采集：2026-09-01 上有 code.exe 1200s + key_a×3（5 段会话）
    sources = _sources(tmp_path)
    state: dict = {}
    LegacyImporter(database, tz=TZ).run(state, sources, tmp_path / "backup")
    # 导入确实叠加了数据（否则下面的"恢复"没有意义）。
    assert _rows(database, "SELECT COUNT(*) FROM usage_session")[0][0] > 7

    LegacyImporter(database, tz=TZ).undo(state)

    # 对照库：同样的新采集、从未导入。
    from omnisight.storage.database import Database
    from omnisight.storage.migrations import migrate

    reference = Database(tmp_path / "reference.db")
    migrate(reference)
    seeded.seed(reference)

    assert _dump_aggregates(database) == _dump_aggregates(reference)
    # 导入的会话行没了，新采集的会话行一条不少（PLAN 里时长 > 0 的五段）。
    assert _rows(database, "SELECT COUNT(*) FROM usage_session")[0][0] == 5
    # 导入写的 capability 行删了（seeded 自己的行保留）。
    assert not _rows(database, "SELECT * FROM capture_capability"
                              " WHERE keyboard_backend IN ('pynput_legacy', 'none')")
    assert load_state(database)["status"] == "undone"
    reference.close()


def test_undo_preserves_unsupported_aggregates_when_store_raw_is_off(database, tmp_path):
    """store_raw 关闭期间的新采集没有原始行支撑——撤销的补差必须保住它们。

    这是补差公式存在的理由：纯"删除 + 重建"会把无支撑量一起抹掉。
    """
    import seeded

    seeded.seed(database, store_raw=False)
    sources = _sources(tmp_path)
    state: dict = {}
    # 导入器同样关闭原始留存：KeyTrace 明细只进聚合。
    LegacyImporter(database, tz=TZ, store_raw=False).run(
        state, sources, tmp_path / "backup"
    )
    assert database.table_names().isdisjoint({"raw_key_events_2026_08"})

    LegacyImporter(database, tz=TZ, store_raw=False).undo(state)

    from omnisight.storage.database import Database
    from omnisight.storage.migrations import migrate

    reference = Database(tmp_path / "reference.db")
    migrate(reference)
    seeded.seed(reference, store_raw=False)
    assert _dump_aggregates(database) == _dump_aggregates(reference)
    reference.close()


def test_undo_refuses_without_snapshot(database, tmp_path):
    """快照被删后撤销必须明确报错，而不是把导入量当无支撑量加回去。"""
    sources = _sources(tmp_path)
    state: dict = {}
    LegacyImporter(database, tz=TZ).run(state, sources, tmp_path / "backup")
    (Path(state["backup_dir"]) / "usage.db").unlink()
    with pytest.raises(m003.LegacyImportError):
        LegacyImporter(database, tz=TZ).undo(state)


# ── 快照的健壮性 ────────────────────────────────────────────────────────


def test_snapshot_handles_a_wal_library(tmp_path):
    """旧程序被硬杀时留下 -wal/-shm；快照必须把 WAL 内容并进去而不是丢掉。"""
    source = tmp_path / "wal.db"
    conn = sqlite3.connect(str(source))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE t (x INTEGER)")
    conn.execute("INSERT INTO t VALUES (42)")
    conn.commit()
    # 不 checkpoint、不正常关闭，留下 WAL。
    conn.close()

    target = tmp_path / "snapshot.db"
    m003.snapshot_legacy(source, target)
    check = sqlite3.connect(str(target))
    assert check.execute("SELECT SUM(x) FROM t").fetchone()[0] == 42
    check.close()
