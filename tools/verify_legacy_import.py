"""用 refer/data 下的**真实旧库**跑一遍完整导入 + 撤销（12 文档 M5 判据 1）。

refer/ 不进版本库，因此这不在 CI 里跑；M5 交付时人工执行一次，数字记进
PROGRESS。用法::

    python tools/verify_legacy_import.py

校验内容：计数与旧库可核对、旧库文件字节级未变、撤销后聚合回到导入前。
"""

from __future__ import annotations

import hashlib
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from legacy_dbs import TZ  # noqa: E402
from omnisight.storage.database import Database  # noqa: E402
from omnisight.storage.migrations import migrate  # noqa: E402
from omnisight.storage.migrations.m003_import_legacy import (  # noqa: E402
    LegacyImporter,
    connect_readonly,
    load_state,
    scan_keytrace,
    scan_timelens,
)

REFER = ROOT / "refer" / "data"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def aggregates(db: Database) -> dict[str, list]:
    tables = [
        "agg_key_day", "agg_key_total", "agg_key_hour",
        "agg_app_day", "agg_app_total", "agg_press_hour", "agg_press_minute",
    ]
    return {
        table: sorted(tuple(row) for row in db.connect().execute(f"SELECT * FROM {table}"))
        for table in tables
    }


def main() -> int:
    tl_path = REFER / "usage.db"
    kt_path = REFER / "keytrace.sqlite3"
    if not tl_path.exists() and not kt_path.exists():
        print("refer/data 下没有旧库，跳过")
        return 0

    # 旧库的先验统计（直接从旧库数出来，作为导入后核对的标准答案）。
    expected = {}
    if tl_path.exists():
        conn = connect_readonly(tl_path)
        scan = scan_timelens(conn)
        expected["sessions"] = conn.execute("SELECT COUNT(*) FROM app_usage").fetchone()[0]
        expected["key_presses"] = conn.execute(
            "SELECT COALESCE(SUM(press_count), 0) FROM key_usage"
        ).fetchone()[0]
        conn.close()
    if kt_path.exists():
        conn = connect_readonly(kt_path)
        scan = scan_keytrace(conn)
        expected["raw"] = scan["raw"]["rows"]
        expected["kt_days"] = set(scan["key_days"])
        conn.close()

    fingerprints = {
        path.name: digest(path)
        for path in (tl_path, kt_path)
        if path.exists()
    }

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        work = Path(tmp)
        db = Database(work / "omnisight.db")
        migrate(db)
        before = aggregates(db)

        state: dict = {}
        backup = work / "backup"
        LegacyImporter(db, tz=TZ).run(
            state,
            {"timelens": tl_path if tl_path.exists() else None,
             "keytrace": kt_path if kt_path.exists() else None},
            backup,
        )
        stored = load_state(db)
        conn = db.connect()

        counts = stored["counts"]
        print("── 导入结果 ──")
        if "sessions" in expected:
            actual = conn.execute("SELECT COUNT(*) FROM usage_session").fetchone()[0]
            print(f"会话行：导入 {counts.get('sessions_imported', 0)}"
                  f" / 旧库 {expected['sessions']}（心跳段与访问合并为行数不变）")
            assert actual == counts.get("sessions_imported", 0) + 0, "行数对不上"
        if "key_presses" in expected:
            skipped = set(stored.get("skipped_days", []))
            print(f"按键次数（TimeLens）：导入 {counts.get('key_presses', 0)}"
                  f" / 旧库 {expected['key_presses']}；冲突跳过 {len(skipped)} 天")
        if "raw" in expected:
            actual = sum(
                conn.execute(f"SELECT COUNT(*) FROM raw_key_events_{m}").fetchone()[0]
                for m in ("2026_08", "2026_09")
                if db.table_exists(f"raw_key_events_{m}")
            )
            print(f"按键明细（KeyTrace）：导入 {counts.get('raw_imported', 0)}"
                  f" / 旧库 {expected['raw']}（未映射键跳过"
                  f" {sum(counts.get('unmapped_keys', {}).values())} 次）")
            assert actual == counts.get("raw_imported", 0), "明细行数对不上"
        unmapped = counts.get("unmapped_keys", {})
        print(f"未映射键名：{unmapped or '无'}")
        print(f"备份快照：{sorted(p.name for p in backup.iterdir())}")

        after_import = aggregates(db)
        assert after_import != before, "导入没有写入任何数据？"

        # 旧库字节级未变。
        for name, expected_hash in fingerprints.items():
            assert digest(REFER / name) == expected_hash, f"{name} 被修改了！"
        print("旧库文件 sha256 校验：未改变 ✓")

        # 撤销 → 聚合回到导入前。
        LegacyImporter(db, tz=TZ).undo(stored)
        after_undo = aggregates(db)
        for table in before:
            if after_undo[table] != before[table]:
                print(f"撤销后 {table} 与导入前不一致：")
                print("  导入前:", before[table][:3], "…")
                print("  撤销后:", after_undo[table][:3], "…")
                return 1
        print("撤销后聚合表 == 导入前 ✓")
        db.close()
    print("\n全部校验通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
