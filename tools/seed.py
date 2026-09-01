"""合成数据生成器：造出"三年的重度使用"，供性能基准与手工验收使用（11 文档 §5）。

**它只通过生产写入路径造数据**——``EventQueue`` → ``StorageWriter``。绝不手写
``INSERT INTO agg_*``：那样造出的库会掩盖聚合维护本身的 bug，而基准跑在一个与真实
形态不同的库上，测出来的 P95 也没有意义。

两处刻意的简化，写在这里而不是藏在代码里：

1. **默认不模拟心跳落盘。** 真实运行中一次 3 小时的访问会被 10 秒一次的心跳切成
   1080 段（04 文档 §2.3），一次访问只有 ``end_reason <> 'heartbeat'`` 的那一段。
   聚合结果与"一段到底"完全等价（时长求和相同、``session_count`` 只数访问、
   ``longest_visit_ms`` 取 MAX 收敛到整次跨度），因此默认每次访问只落一行。
   要压 ``usage_session`` 的行数时用 ``--heartbeat-seconds 10`` 打开。
2. **不模拟"人"。** 键位分布是加权随机而不是真实文本，所以热力图形状可信、
   相邻键的相关性不可信。基准关心的是行数与索引，不是分布形状。

用法::

    python tools/seed.py --days 1096 --fresh                # 三年（约 10 分钟）
    python tools/seed.py --days 30 --gap-days 3 --no-raw    # 一个月，含采集空档
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from omnisight.adapters.ports import AppIdentity  # noqa: E402
from omnisight.capture.keymap import KEY_IDS  # noqa: E402
from omnisight.capture.models import KeyEvent, UsageSession  # noqa: E402
from omnisight.capture.queue import EventQueue  # noqa: E402
from omnisight.storage import capability as capability_table  # noqa: E402
from omnisight.storage.database import Database  # noqa: E402
from omnisight.storage.migrations import migrate  # noqa: E402
from omnisight.storage.repositories.apps import AppRegistry  # noqa: E402
from omnisight.storage.writer import StorageWriter  # noqa: E402

#: 基准库的默认落点。**不能放 build/**：``tools/build.py`` 默认 ``rmtree`` 它，
#: 于是播了十分钟的三年数据会被下一次打包静默删掉（踩过）。
BENCH_DIR = ROOT / ".bench"

#: 播种用的批量远大于生产值：生产要的是"1 秒内可见"，播种要的是吞吐。
SEED_BATCH = 20_000


@dataclass(frozen=True, slots=True)
class AppProfile:
    """一个假想应用。``weight`` 决定被切到的概率，``kpm`` 决定它有多"打字"。"""

    process: str
    display: str
    weight: float
    kpm: float
    #: 单次访问时长范围（秒）。IDE 一坐就是半小时，聊天软件是几十秒切进切出。
    visit_seconds: tuple[int, int]


APPS: tuple[AppProfile, ...] = (
    AppProfile("code.exe", "Visual Studio Code", 26, 210, (300, 3600)),
    AppProfile("chrome.exe", "Google Chrome", 22, 45, (120, 1800)),
    AppProfile("windowsterminal.exe", "Windows Terminal", 12, 160, (60, 900)),
    AppProfile("wechat.exe", "微信", 9, 70, (30, 300)),
    AppProfile("excel.exe", "Microsoft Excel", 7, 90, (180, 1500)),
    AppProfile("winword.exe", "Microsoft Word", 5, 130, (300, 2400)),
    AppProfile("pycharm64.exe", "PyCharm", 5, 190, (600, 3600)),
    AppProfile("slack.exe", "Slack", 4, 60, (30, 420)),
    AppProfile("explorer.exe", "文件资源管理器", 4, 8, (10, 120)),
    AppProfile("obsidian.exe", "Obsidian", 3, 150, (180, 1800)),
    AppProfile("steam.exe", "Steam", 2, 10, (60, 900)),
    AppProfile("spotify.exe", "Spotify", 1, 6, (30, 600)),
)

#: 手工加权的高频键。其余键统一给一个小权重，保证热力图里"冷键"也不是纯 0——
#: 全 0 的键会让 ``scale.p95`` 与配色分档的验收失去意义。
HOT_KEYS: dict[str, float] = {
    "space": 170, "backspace": 95, "enter": 60, "shift_left": 55, "period": 22,
    "comma": 18, "control_left": 34, "tab": 20, "escape": 12, "alt_left": 10,
    "arrow_down": 16, "arrow_up": 14, "arrow_left": 12, "arrow_right": 12,
    "key_e": 100, "key_t": 72, "key_a": 68, "key_o": 64, "key_i": 62, "key_n": 60,
    "key_s": 58, "key_h": 52, "key_r": 50, "key_d": 36, "key_l": 34, "key_u": 30,
    "key_c": 28, "key_m": 26, "key_f": 24, "key_g": 22, "key_y": 20, "key_p": 20,
    "key_w": 18, "key_b": 16, "key_v": 12, "key_k": 10, "key_x": 7, "key_j": 6,
    "key_q": 5, "key_z": 4,
}
COLD_KEY_WEIGHT = 0.6

#: ``kpm`` 是"手在动的时候"的速度。人不会整段访问都在打字——读代码、看页面、开会都占着
#: 前台却不产生按键。乘上这个占空比之后，重度用户约 12000 次/天，与 KeyTrace 线上
#: 观测量级一致；不乘的话一天能造出 5 万次，热力图与 KPM 都会失真到没有验收价值。
TYPING_DUTY = 0.14


def _key_population() -> tuple[list[str], list[float]]:
    """全部键位 + 权重。冷键也给非零权重，见 :data:`COLD_KEY_WEIGHT`。"""
    ids = sorted(KEY_IDS)
    return ids, [HOT_KEYS.get(key, COLD_KEY_WEIGHT) for key in ids]


#: 每天的活动窗口（起点小时, 终点小时, 出现概率）。工作日/周末共用，靠概率区分强度。
WINDOWS: tuple[tuple[float, float, float], ...] = (
    (9.0, 12.5, 0.95),
    (13.5, 18.5, 0.95),
    (20.0, 23.2, 0.6),
)


@dataclass
class SeedReport:
    days: int
    presses: int
    visits: int
    seconds: float
    db_bytes: int

    def render(self) -> str:
        rate = self.presses / self.seconds if self.seconds else 0
        return (
            f"{self.days} 天 / {self.presses:,} 次按键 / {self.visits:,} 次访问，"
            f"耗时 {self.seconds:.1f}s（{rate:,.0f} 事件/秒），"
            f"库大小 {self.db_bytes / 1_048_576:.1f} MiB"
        )


def seed(
    db: Database,
    *,
    days: int,
    end: date,
    tz: ZoneInfo,
    rng: random.Random,
    store_raw: bool = True,
    gap_days: int = 0,
    heartbeat_seconds: float = 0.0,
    intensity: float = 1.0,
    titles: bool = False,
    progress: bool = False,
) -> SeedReport:
    """把 ``days`` 天的合成数据写进 ``db``。返回统计供基准脚本打印。

    ``gap_days`` 天完全没有数据**且没有能力快照**——这正是 coverage 的"我们对那天
    一无所知"分支（不产生 gap）。另有约 4% 的天只有键盘没有前台，用来产出真正的
    ``coverage.gaps``（05 文档 §1.4）。
    """
    queue = EventQueue(maxsize=SEED_BATCH * 2)
    registry = AppRegistry(db, "windows")
    writer = StorageWriter(
        db, queue, tz=tz, store_raw=store_raw,
        registry=registry, batch_max_size=SEED_BATCH, batch_max_wait_seconds=0.0,
        checkpoint_interval_seconds=0.0,
    )
    app_ids = {
        profile.process: registry.resolve(
            AppIdentity(
                app_key=profile.process, identity_kind="process",
                display_name=profile.display, process_name=profile.process,
                exe_path=rf"C:\Program Files\{profile.display}\{profile.process}",
            )
        )
        for profile in APPS
    }
    keys, weights = _key_population()
    weight_total = sum(profile.weight for profile in APPS)

    skipped = set(rng.sample(range(days), min(gap_days, days))) if gap_days else set()
    started = time.perf_counter()
    presses = visits = 0
    for offset in range(days):
        day = end - timedelta(days=days - 1 - offset)
        if offset in skipped:
            continue
        foreground = rng.random() > 0.04
        with db.transaction() as conn:
            capability_table.upsert(
                conn,
                day_bucket=day.isoformat(),
                platform_id="windows",
                keyboard_backend="raw_input",
                foreground_available=foreground,
                titles_recorded=titles,
                key_position_stable=True,
                now=datetime.combine(day, datetime.min.time(), tzinfo=tz),
            )
        day_presses, day_visits = _seed_day(
            day, tz=tz, rng=rng, queue=queue, writer=writer, app_ids=app_ids,
            keys=keys, weights=weights, weight_total=weight_total,
            foreground=foreground, heartbeat_seconds=heartbeat_seconds,
            intensity=intensity, titles=titles,
        )
        presses += day_presses
        visits += day_visits
        if progress and (offset + 1) % 100 == 0:
            print(f"  … {offset + 1}/{days} 天", flush=True)
    while queue.depth:
        writer.flush_once()
    db.checkpoint("TRUNCATE")
    return SeedReport(
        days=days - len(skipped), presses=presses, visits=visits,
        seconds=time.perf_counter() - started,
        db_bytes=db.path.stat().st_size if db.path.exists() else 0,
    )


def _seed_day(
    day: date,
    *,
    tz: ZoneInfo,
    rng: random.Random,
    queue: EventQueue,
    writer: StorageWriter,
    app_ids: dict[str, int],
    keys: list[str],
    weights: list[float],
    weight_total: float,
    foreground: bool,
    heartbeat_seconds: float,
    intensity: float,
    titles: bool,
) -> tuple[int, int]:
    presses = visits = 0
    weekend = day.weekday() >= 5
    for start_hour, end_hour, chance in WINDOWS:
        if rng.random() > (chance * (0.5 if weekend else 1.0)):
            continue
        cursor = _at(day, start_hour + rng.uniform(0, 0.4), tz)
        window_end = _at(day, end_hour - rng.uniform(0, 0.5), tz)
        while cursor < window_end:
            profile = _pick_app(rng, weight_total)
            app_id = app_ids[profile.process] if foreground else 0
            low, high = profile.visit_seconds
            span = rng.uniform(low, high) * (0.6 if weekend else 1.0)
            visit_end = min(cursor + timedelta(seconds=span), window_end)
            if visit_end <= cursor:
                break
            presses += _emit_keys(
                queue=queue, writer=writer, rng=rng, keys=keys, weights=weights,
                app_id=app_id, start=cursor, end=visit_end,
                kpm=profile.kpm * intensity,
            )
            visits += _emit_visit(
                queue=queue, writer=writer, app_id=app_id, start=cursor, end=visit_end,
                heartbeat_seconds=heartbeat_seconds,
                title=f"{profile.display} — 文档 {rng.randint(1, 40)}" if titles else "",
            )
            # 切窗之间留一点空隙：连续访问首尾相接会让"切换次数"与真实差得太远。
            cursor = visit_end + timedelta(seconds=rng.uniform(0.5, 20))
    return presses, visits


def _pick_app(rng: random.Random, weight_total: float) -> AppProfile:
    mark = rng.uniform(0, weight_total)
    upto = 0.0
    for profile in APPS:
        upto += profile.weight
        if mark <= upto:
            return profile
    return APPS[0]


def _emit_keys(
    *,
    queue: EventQueue,
    writer: StorageWriter,
    rng: random.Random,
    keys: list[str],
    weights: list[float],
    app_id: int,
    start: datetime,
    end: datetime,
    kpm: float,
) -> int:
    """在 ``[start, end)`` 内按 ``kpm`` 撒按键。返回条数。"""
    seconds = (end - start).total_seconds()
    count = int(seconds / 60 * kpm * TYPING_DUTY * rng.uniform(0.6, 1.4))
    if count <= 0:
        return 0
    base_ns = int(start.timestamp() * 1_000_000_000)
    span_ns = max(int(seconds * 1_000_000_000), 1)
    picks = rng.choices(keys, weights=weights, k=count)
    offsets = sorted(rng.randrange(span_ns) for _ in range(count))
    for key_id, offset in zip(picks, offsets, strict=True):
        hold = rng.uniform(35, 140)
        down = base_ns + offset
        queue.put(
            KeyEvent(
                key_id=key_id,
                down_ts_ns=down,
                up_ts_ns=down + int(hold * 1_000_000),
                duration_ms=hold,
                app_id=app_id,
                confidence="high",
            )
        )
    _drain_if_full(queue, writer)
    return count


def _emit_visit(
    *,
    queue: EventQueue,
    writer: StorageWriter,
    app_id: int,
    start: datetime,
    end: datetime,
    heartbeat_seconds: float,
    title: str,
) -> int:
    """一次访问。``heartbeat_seconds > 0`` 时按真实心跳切段（首段开启访问）。"""
    start_ns = int(start.timestamp() * 1_000_000_000)
    end_ns = int(end.timestamp() * 1_000_000_000)
    if end_ns <= start_ns:
        return 0
    edges = [start_ns]
    if heartbeat_seconds > 0:
        step = int(heartbeat_seconds * 1_000_000_000)
        edges.extend(range(start_ns + step, end_ns, step))
    edges.append(end_ns)
    for index in range(len(edges) - 1):
        segment_start, segment_end = edges[index], edges[index + 1]
        last = index == len(edges) - 2
        queue.put(
            UsageSession(
                app_id=app_id,
                start_ts_ns=segment_start,
                end_ts_ns=segment_end,
                duration_ms=(segment_end - segment_start) // 1_000_000,
                window_title=title if last else "",
                end_reason="switch" if last else "heartbeat",
                visit_start_ts_ns=start_ns,
            )
        )
    _drain_if_full(queue, writer)
    return 1


def _drain_if_full(queue: EventQueue, writer: StorageWriter) -> None:
    while queue.depth >= SEED_BATCH:
        writer.flush_once()


def _at(day: date, hour: float, tz: ZoneInfo) -> datetime:
    whole = int(hour)
    return datetime(day.year, day.month, day.day, min(whole, 23), tzinfo=tz) + timedelta(
        minutes=(hour - whole) * 60
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OmniSight 合成数据生成器")
    parser.add_argument("--db", type=Path, default=BENCH_DIR / "bench.db")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--end", default="", help="最后一天（YYYY-MM-DD），默认今天")
    parser.add_argument("--tz", default="Asia/Shanghai")
    parser.add_argument("--seed", type=int, default=20260901, help="随机种子（可复现）")
    parser.add_argument("--gap-days", type=int, default=0, help="完全没有数据的天数")
    parser.add_argument("--heartbeat-seconds", type=float, default=0.0)
    parser.add_argument("--intensity", type=float, default=1.0, help="按键密度倍率")
    parser.add_argument("--titles", action="store_true", help="同时播种窗口标题")
    parser.add_argument("--no-raw", action="store_true", help="不留存原始按键事件")
    parser.add_argument("--fresh", action="store_true", help="先删掉已存在的库")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    tz = ZoneInfo(args.tz)
    end = date.fromisoformat(args.end) if args.end else datetime.now(tz).date()
    if args.fresh:
        for suffix in ("", "-wal", "-shm"):
            candidate = args.db.with_name(args.db.name + suffix)
            candidate.unlink(missing_ok=True)
    args.db.parent.mkdir(parents=True, exist_ok=True)
    db = Database(args.db)
    try:
        migrate(db)
        report = seed(
            db,
            days=args.days,
            end=end,
            tz=tz,
            rng=random.Random(args.seed),
            store_raw=not args.no_raw,
            gap_days=args.gap_days,
            heartbeat_seconds=args.heartbeat_seconds,
            intensity=args.intensity,
            titles=args.titles,
            progress=args.days >= 200,
        )
    finally:
        db.close()
    print(f"已写入 {args.db}：{report.render()}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
