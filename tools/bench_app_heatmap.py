"""应用键盘热力图的新旧算法对比基准（12 文档 M4 完成判据 1）。

**要回答的问题**：同一个问题——"这个应用的键盘热力图长什么样"——旧 KeyTrace 的算法
（向 TimeLens 取前台区间 → 区间求交 → 对每个区间在原始事件表上做时间窗扫描 → Python
累加）与合并后的算法（``agg_app_key_total`` 一次主键点查）差多少倍。

判据原文："应用键盘热图从 ``agg_app_key_total`` 点查，不回溯原始事件（对比旧 KeyTrace
的区间求交 + 全表扫描，量化提速倍数写进文档）"。

**对旧算法的模拟刻意偏向它**，这样测出的倍数是下界：

1. 不模拟 HTTP 往返——旧 KeyTrace 每次都要向 TimeLens 发请求取区间，这里只算本地 SQL；
2. 先把重叠区间合并成不重叠的列表再扫描——旧版按访问逐段查，不会更慢；
3. 扫描用 ``GROUP BY key_id`` 在 SQL 侧聚合——旧版把行读回 Python 逐行累加。

用法::

    python tools/seed.py --days 1096 --fresh
    python tools/bench_app_heatmap.py
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from omnisight.storage import schema  # noqa: E402
from omnisight.storage.database import Database  # noqa: E402

BENCH_DIR = ROOT / ".bench"

#: 新算法的重复次数。它本身是毫秒级，多测几次取中位数降噪。
NEW_RUNS = 9


def pick_app(conn) -> tuple[int, str]:
    """取按键最多的应用——它拥有最多的访问区间，对旧算法是最有利的受测者。"""
    row = conn.execute(
        "SELECT t.app_id, COALESCE(a.user_alias, a.display_name, a.process_name) AS name "
        "FROM agg_app_key_total t JOIN app a ON a.id = t.app_id "
        "GROUP BY t.app_id ORDER BY SUM(t.press_count) DESC LIMIT 1"
    ).fetchone()
    return int(row["app_id"]), str(row["name"])


def new_algorithm(conn, app_id: int) -> dict[str, int]:
    """合并后的算法：``KeyRepository.app_heatmap`` 的查询原样。"""
    rows = conn.execute(
        "SELECT key_id, press_count FROM agg_app_key_total WHERE app_id = ?",
        (app_id,),
    )
    return {row["key_id"]: int(row["press_count"]) for row in rows}


def legacy_algorithm(conn, app_id: int) -> tuple[dict[str, int], int]:
    """旧 KeyTrace 算法的等价重现（见模块文档的三处偏袒）。返回 ``(counts, 区间数)``。"""
    intervals = [
        (int(row["start_ts_ns"]), int(row["end_ts_ns"]))
        for row in conn.execute(
            "SELECT start_ts_ns, end_ts_ns FROM usage_session "
            "WHERE app_id = ? ORDER BY start_ts_ns",
            (app_id,),
        )
    ]
    merged: list[list[int]] = []
    for start, end in intervals:  # 重叠区间合并（对旧算法有利的一步）
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])

    counts: dict[str, int] = {}
    for start, end in merged:
        month = _month_of_ns(start)
        final_month = _month_of_ns(end)
        while True:  # 一个区间跨月时按月拆开（表是按月分的）
            table = schema.raw_table_name(month)
            month_end = _month_end_ns(month)
            window_end = min(end, month_end)
            if not _table_exists(conn, table):
                if month >= final_month:
                    break
                month = _next_month(month)
                continue
            for row in conn.execute(
                f"SELECT key_id, COUNT(*) AS n FROM {table} "
                "WHERE down_ts_ns >= ? AND down_ts_ns < ? GROUP BY key_id",
                (start, window_end),
            ):
                counts[row["key_id"]] = counts.get(row["key_id"], 0) + int(row["n"])
            if month >= final_month:
                break
            month = _next_month(month)
            # 跨月拆开后，后续月份的扫描从月初开始
            start = max(start, month_end)
    return counts, len(merged)


def _table_exists(conn, table: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
        ).fetchone()
        is not None
    )


def _month_of_ns(ts_ns: int) -> str:
    return datetime.fromtimestamp(ts_ns / 1_000_000_000, tz=UTC).strftime("%Y-%m")


def _month_end_ns(month: str) -> int:
    year, mon = (int(part) for part in month.split("-"))
    following = (
        datetime(year + 1, 1, 1, tzinfo=UTC)
        if mon == 12
        else datetime(year, mon + 1, 1, tzinfo=UTC)
    )
    return int(following.timestamp() * 1_000_000_000)


def _next_month(month: str) -> str:
    year, mon = (int(part) for part in month.split("-"))
    if mon == 12:
        return f"{year + 1}-01"
    return f"{year}-{mon + 1:02d}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="应用键盘热力图新旧算法对比")
    parser.add_argument("--db", type=Path, default=BENCH_DIR / "bench.db")
    args = parser.parse_args(argv)
    if not args.db.exists():
        print(f"找不到 {args.db}，先跑 tools/seed.py --days 1096 --fresh", file=sys.stderr)
        return 2
    db = Database(args.db)
    try:
        conn = db.connect()
        app_id, name = pick_app(conn)

        new_times: list[float] = []
        new_counts: dict[str, int] = {}
        for index in range(NEW_RUNS + 1):
            started = time.perf_counter()
            new_counts = new_algorithm(conn, app_id)
            if index:  # 第一次是预热（编译 SQL、页缓存），不进样本
                new_times.append((time.perf_counter() - started) * 1000)
        new_ms = sorted(new_times)[len(new_times) // 2]

        started = time.perf_counter()
        legacy_counts, interval_count = legacy_algorithm(conn, app_id)
        legacy_ms = (time.perf_counter() - started) * 1000

        same = new_counts == legacy_counts
        total = sum(new_counts.values())
        print(f"应用：{name}（app_id={app_id}，{total:,} 次按键，{interval_count:,} 个前台区间）")
        print(f"新算法（agg_app_key_total 点查）      ：{new_ms:10.1f} ms（{NEW_RUNS} 次取中位）")
        print(f"旧算法（区间合并 + 原始表时间窗扫描）  ：{legacy_ms:10.1f} ms")
        print(f"提速：{legacy_ms / max(new_ms, 0.001):.0f} 倍")
        print(f"两算法逐键计数一致：{'是' if same else '否'}"
              + ("" if same else f"（新 {len(new_counts)} 键 vs 旧 {len(legacy_counts)} 键）"))
        print("注：旧算法未计入它额外要付的 HTTP 往返（向 TimeLens 取区间）与 Python 逐行"
              "累加，实际差距更大。")
        return 0 if same else 1
    finally:
        db.close()


if __name__ == "__main__":  # pragma: no cover
    # 见 tools/_console.py：runner 上 stdout 是管道，按 locale 挑到 cp1252，
    # 一行中文输出就能让进程死在 UnicodeEncodeError 上。
    from _console import use_utf8_output

    use_utf8_output()
    raise SystemExit(main())
