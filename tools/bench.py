"""接口延迟基准：M2 的验收门槛是"三年数据上 P95 < 150ms"（12 文档 §2）。

**冷缓存才是要测的东西。** ``QueryCache`` 按 ``data_version`` 分代，用户一边打字一边看
页面时每来一批落盘就换一代，所以真实交互里绝大多数请求都是冷的。重复请同一个 URL 测出
的是 ``dict`` 查找的速度（<1ms），拿它当验收结论等于没测。因此默认在每次采样前
``bump_data_version()``，并额外报一列热缓存数字做对照。

用法::

    python tools/seed.py --days 1096 --fresh
    python tools/bench.py --iterations 30
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from omnisight.adapters.ports import Capabilities  # noqa: E402
from omnisight.core.config import default_config  # noqa: E402
from omnisight.presentation.web import AppContext, create_app  # noqa: E402
from omnisight.services import Services  # noqa: E402
from omnisight.storage.database import Database  # noqa: E402
from omnisight.storage.migrations import TARGET_VERSION  # noqa: E402

#: 与 ``tools/seed.py`` 共用的默认落点（不能放 build/，那里会被打包脚本清掉）。
BENCH_DIR = ROOT / ".bench"

TOKEN = "bench-token"

#: M2 验收明确点名的三个端点，其余的一起测但不单独设门槛。
GATED = ("overview", "keyboard/heatmap", "insights/app-keyboard")
BUDGET_MS = 150.0

PROBES: tuple[tuple[str, str], ...] = (
    ("overview", "/api/v1/overview?range={range}"),
    ("usage/period", "/api/v1/usage/period?range={range}&limit=50"),
    ("usage/timeline", "/api/v1/usage/timeline?range={range}"),
    ("usage/sessions", "/api/v1/usage/sessions?range={range}&limit=200"),
    ("keyboard/heatmap", "/api/v1/keyboard/heatmap?range={range}"),
    ("keyboard/timeline", "/api/v1/keyboard/timeline?view=days,months,years&range={range}"),
    # 唯一允许碰原始事件的查询路径：应用维度的小时回溯（12 文档 §2 的例外）。
    ("keyboard/timeline(app,hours)",
     "/api/v1/keyboard/timeline?view=hours&app_id=1&range={range}"),
    ("keyboard/ergonomics", "/api/v1/keyboard/ergonomics?range={range}"),
    ("keyboard/keys/space", "/api/v1/keyboard/keys/space?range={range}"),
    ("insights/app-keyboard", "/api/v1/insights/app-keyboard?range={range}"),
    ("insights/rhythm", "/api/v1/insights/rhythm?range={range}"),
    ("apps", "/api/v1/apps?range={range}&limit=50"),
    ("apps/1", "/api/v1/apps/1?range={range}"),
)
#: 与周期无关的端点：只在 ``day`` 那一轮测一次，重复测五遍只是浪费时间。
FIXED_PROBES: tuple[tuple[str, str], ...] = (
    ("status", "/api/v1/status"),
    ("keyboard/layout", "/api/v1/keyboard/layout"),
    ("settings", "/api/v1/settings"),
    ("apps/running", "/api/v1/apps/running"),
    ("export(csv)", "/api/v1/export?scope=keyboard&range=month&format=csv"),
)
RANGES = ("day", "week", "month", "year", "total")


@dataclass
class Sample:
    name: str
    range_: str
    p50: float
    p95: float
    worst: float
    warm_p95: float
    status: int
    raw_hits: int

    @property
    def gated(self) -> bool:
        return self.name in GATED

    @property
    def over_budget(self) -> bool:
        return self.gated and self.p95 > BUDGET_MS


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = min(round(fraction * (len(ordered) - 1)), len(ordered) - 1)
    return ordered[index]


def _build_client(db: Database, tz: str):
    config = default_config()
    capabilities = Capabilities(
        platform_id="windows", tier=1, os_version="10.0.26100",
        keyboard=True, keyboard_backend="raw_input", keyboard_durations=True,
        key_position_stable=True, foreground=True, window_titles=True,
        idle=True, icons=False, autostart=True, tray=True,
    )
    context = AppContext(
        config=config, database=db, capabilities=capabilities, token=TOKEN,
        started_at=datetime.now(ZoneInfo(tz)).isoformat(timespec="seconds"),
        data_dir=BENCH_DIR, schema_version=TARGET_VERSION,
    )
    context.services = Services.build(
        database=db, config=config, capabilities=capabilities,
        config_path=BENCH_DIR / "bench-config.json",
    )
    app = create_app(context)
    app.config.update(TESTING=True)
    client = app.test_client()
    client.environ_base["HTTP_X_OMNISIGHT_TOKEN"] = TOKEN
    client.environ_base["HTTP_SEC_FETCH_SITE"] = "same-origin"
    return client, context


def _raw_probe(db: Database) -> list[str]:
    """收集本次请求执行过的、命中原始事件表的 SQL。

    ``raw_key_events_*`` 只允许两处访问（单键详情、应用小时热力回溯），别的端点碰到它
    就是设计事故——一年的原始事件是千万级，扫一次就没有 P95 可谈了（12 文档 §2）。
    """
    seen: list[str] = []
    conn = db.connect()
    conn.set_trace_callback(lambda sql: seen.append(sql) if "raw_key_events" in sql else None)
    return seen


def measure(
    client, db: Database, path: str, iterations: int
) -> tuple[list[float], float, int, int]:
    cold: list[float] = []
    status = 0
    for _ in range(3):  # 预热：首次请求要建 AppLens、编译 SQL、装载 layout
        status = client.get(path).status_code
    seen = _raw_probe(db)
    for _ in range(iterations):
        db.bump_data_version()
        # **必须在计时外 checkpoint**：每次 bump 都往 WAL 追加一次提交，几百次之后
        # WAL 大到让每个读请求都要先搜一遍 WAL 索引，测出来的是基准自己造的噪声。
        # 生产里写线程每 300 秒 checkpoint 一次，这里对齐它。
        db.checkpoint("TRUNCATE")
        started = time.perf_counter()
        response = client.get(path)
        # 必须把 body 取出来：``/export`` 是流式响应，只看 status_code 等于没测。
        status, _ = response.status_code, len(response.get_data())
        cold.append((time.perf_counter() - started) * 1000)
    raw_hits = len(seen)
    db.connect().set_trace_callback(None)
    warm: list[float] = []
    for _ in range(iterations):
        started = time.perf_counter()
        client.get(path).get_data()
        warm.append((time.perf_counter() - started) * 1000)
    return cold, _percentile(warm, 0.95), status, raw_hits


def run(db: Database, *, iterations: int, tz: str, ranges: tuple[str, ...]) -> list[Sample]:
    client, _context = _build_client(db, tz)
    samples: list[Sample] = []
    plan = [(name, template, range_) for name, template in PROBES for range_ in ranges]
    plan += [(name, path, "-") for name, path in FIXED_PROBES]
    for name, template, range_ in plan:
        path = template.format(range=range_)
        cold, warm_p95, status, raw_hits = measure(client, db, path, iterations)
        samples.append(
            Sample(
                name=name, range_=range_, p50=_percentile(cold, 0.5),
                p95=_percentile(cold, 0.95), worst=max(cold), warm_p95=warm_p95,
                status=status, raw_hits=raw_hits,
            )
        )
    return samples


def report(samples: list[Sample]) -> int:
    width = max(len(sample.name) for sample in samples)
    print(f"{'endpoint':<{width}}  {'range':<6} {'p50':>8} {'p95':>8} {'max':>8} "
          f"{'warm':>8} {'raw':>4} {'code':>5}")
    print("-" * (width + 54))
    for sample in samples:
        flag = "  ← 超预算" if sample.over_budget else ""
        print(
            f"{sample.name:<{width}}  {sample.range_:<6} {sample.p50:>8.1f} "
            f"{sample.p95:>8.1f} {sample.worst:>8.1f} {sample.warm_p95:>8.2f} "
            f"{sample.raw_hits:>4} {sample.status:>5}{flag}"
        )
    gated = [sample for sample in samples if sample.gated]
    breached = [sample for sample in samples if sample.over_budget]
    errors = [sample for sample in samples if sample.status != 200]
    print()
    if gated:
        worst = max(sample.p95 for sample in gated)
        print(f"门槛端点最差 P95：{worst:.1f}ms（预算 {BUDGET_MS:.0f}ms）")
    print(f"全部端点最差 P95：{max(sample.p95 for sample in samples):.1f}ms")
    raw_users = sorted({sample.name for sample in samples if sample.raw_hits})
    print(f"触碰 raw_key_events 的端点：{raw_users or '无'}")
    if errors:
        print(f"非 200 响应：{[(s.name, s.range_, s.status) for s in errors]}")
        return 1
    if breached:
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OmniSight 接口延迟基准")
    parser.add_argument("--db", type=Path, default=BENCH_DIR / "bench.db")
    parser.add_argument("--iterations", type=int, default=30)
    parser.add_argument("--tz", default="Asia/Shanghai")
    parser.add_argument("--ranges", default=",".join(RANGES))
    args = parser.parse_args(argv)
    if not args.db.exists():
        print(f"找不到 {args.db}，先跑 tools/seed.py", file=sys.stderr)
        return 2
    db = Database(args.db)
    try:
        samples = run(
            db, iterations=args.iterations, tz=args.tz,
            ranges=tuple(part for part in args.ranges.split(",") if part),
        )
    finally:
        db.close()
    return report(samples)


if __name__ == "__main__":  # pragma: no cover
    # 见 tools/_console.py：runner 上 stdout 是管道，按 locale 挑到 cp1252，
    # 一行中文输出就能让进程死在 UnicodeEncodeError 上。
    from _console import use_utf8_output

    use_utf8_output()
    raise SystemExit(main())
