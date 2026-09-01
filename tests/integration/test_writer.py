"""写入 → 聚合 → 查询闭环（11 文档 §4.1、§4.2；M1 完成判据里的两条）。

**最重要的一组测试。** ``recompute_from_raw_events`` 是只在测试里存在的慢速参考
实现：直接从 ``raw_key_events_*`` 重算，与增量维护的聚合表逐格比对。有了它，"聚合
算错了"这类无声故障就能被机械地抓住——而这正是 KeyTrace 那套分层聚合最需要、现在
完全没有的保障。

判据里的两条在这里落地：
* 按键计数对照：10 000 次已知按键，落库计数误差 = 0；
* 聚合一致性：``agg_key_day`` 求和 == 原始事件计数，``agg_app_key_total`` 求和 ==
  各日 ``agg_key_app_day`` 求和。
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from sqlite3 import Connection
from zoneinfo import ZoneInfo

import pytest

from omnisight.adapters.ports import AppIdentity
from omnisight.capture.models import KeyEvent, UsageSession
from omnisight.capture.queue import EventQueue
from omnisight.storage.partitions import Partitions, raw_table
from omnisight.storage.repositories.apps import AppRegistry
from omnisight.storage.repositories.keys import KeyRepository
from omnisight.storage.repositories.usage import UsageRepository
from omnisight.storage.writer import StorageWriter

TZ = ZoneInfo("Asia/Shanghai")
DAY_ONE = datetime(2026, 8, 30, 9, 0, tzinfo=TZ)
KEY_POOL = ("key_a", "key_e", "key_s", "space", "enter", "shift_left", "backspace")


def _writer(database, **kwargs) -> tuple[StorageWriter, EventQueue, AppRegistry]:
    queue = EventQueue()
    registry = AppRegistry(database, "windows")
    writer = StorageWriter(database, queue, tz=TZ, registry=registry, **kwargs)
    return writer, queue, registry


def _app(registry: AppRegistry, name: str) -> int:
    return registry.resolve(
        AppIdentity(
            app_key=name.lower(),
            identity_kind="process",
            display_name=name,
            process_name=name,
        )
    )


def _key_event(moment: datetime, key_id: str, app_id: int, *, duration_ms: float = 90.0,
               confidence: str = "high") -> KeyEvent:
    down = int(moment.timestamp() * 1_000_000_000)
    return KeyEvent(
        key_id=key_id,
        down_ts_ns=down,
        up_ts_ns=down + int(duration_ms * 1_000_000),
        duration_ms=duration_ms,
        app_id=app_id,
        confidence=confidence,
    )


def _drain(writer: StorageWriter, queue: EventQueue) -> None:
    """把队列里的一切写完。``flush_once`` 每次最多取一批，因此循环到空。"""
    while queue.depth:
        writer.flush_once()


# ── 参考实现（只在测试里存在，慢但显然正确）───────────────────────────────
def recompute_from_raw_events(conn: Connection, tz=TZ) -> dict:
    """从原始事件表重算全部键相关聚合。

    刻意用 Python 而不是 SQL 的 ``strftime``：如果参考实现和被测实现共用同一套
    日期函数，两者会一起错，测试就变成了同义反复。
    """
    per_day: dict[tuple[str, str], list[float]] = {}
    per_day_app: dict[tuple[str, int, str], list[float]] = {}
    per_app: dict[tuple[int, str], list[float]] = {}
    per_hour: dict[tuple[str, int, str], list[float]] = {}
    total = 0

    for month in Partitions.existing_months(conn):
        table = raw_table(month)
        rows = conn.execute(
            f"SELECT key_id, app_id, down_ts_ns, duration_ms FROM {table}"
        )
        for key_id, app_id, down_ts_ns, duration_ms in rows:
            moment = datetime.fromtimestamp(down_ts_ns / 1_000_000_000, tz=tz)
            day = moment.strftime("%Y-%m-%d")
            total += 1
            for target, bucket in (
                (per_day, (day, key_id)),
                (per_day_app, (day, app_id, key_id)),
                (per_app, (app_id, key_id)),
                (per_hour, (day, moment.hour, key_id)),
            ):
                slot = target.setdefault(bucket, [0, 0.0, 0.0])
                slot[0] += 1
                slot[1] += duration_ms
                slot[2] = max(slot[2], duration_ms)
    return {
        "total": total,
        "per_day": per_day,
        "per_day_app": per_day_app,
        "per_app": per_app,
        "per_hour": per_hour,
    }


def generate_key_events(registry: AppRegistry, *, days: int, per_day: int,
                        apps: list[str], seed: int = 20260901) -> list[KeyEvent]:
    """合成一段可复现的按键流，跨日、跨小时、跨月。"""
    rng = random.Random(seed)
    app_ids = [_app(registry, name) for name in apps]
    events: list[KeyEvent] = []
    for day in range(days):
        base = DAY_ONE + timedelta(days=day)
        for index in range(per_day):
            moment = base + timedelta(seconds=index * 3, milliseconds=rng.randrange(1000))
            events.append(
                _key_event(
                    moment,
                    rng.choice(KEY_POOL),
                    rng.choice(app_ids),
                    duration_ms=float(rng.randrange(20, 400)),
                    confidence=rng.choice(("high", "high", "high", "boundary")),
                )
            )
    return events
# PLACEHOLDER


# ── 判据：按键计数对照 ─────────────────────────────────────────────────────
def test_ten_thousand_known_key_presses_land_with_zero_error(database):
    """M1 判据：脚本发送 10 000 次已知按键，落库计数误差 = 0。

    这里替代真实键盘的部分只有"事件从哪来"；从入队到聚合的全部代码路径都是生产代码。
    """
    writer, queue, registry = _writer(database)
    app_id = _app(registry, "code.exe")
    expected: dict[str, int] = {}
    for index in range(10_000):
        key_id = KEY_POOL[index % len(KEY_POOL)]
        expected[key_id] = expected.get(key_id, 0) + 1
        queue.put(_key_event(DAY_ONE + timedelta(milliseconds=index * 137), key_id, app_id))
    _drain(writer, queue)

    conn = database.connect()
    assert conn.execute("SELECT SUM(press_count) FROM agg_key_total").fetchone()[0] == 10_000
    assert KeyRepository(database).press_total() == 10_000
    actual = {
        row[0]: row[1]
        for row in conn.execute("SELECT key_id, press_count FROM agg_key_total")
    }
    assert actual == expected
    assert queue.dropped == 0


# ── 判据：聚合一致性 ──────────────────────────────────────────────────────
def test_aggregates_match_raw_recomputation(database):
    """预聚合表必须与从原始事件直算的结果**逐格**相等。"""
    writer, queue, registry = _writer(database)
    events = generate_key_events(registry, days=3, per_day=2000, apps=["code.exe", "chrome.exe"])
    for event in events:
        queue.put(event)
    _drain(writer, queue)

    conn = database.connect()
    reference = recompute_from_raw_events(conn)
    assert reference["total"] == len(events)

    from_agg = {
        (row[0], row[1]): [row[2], row[3], row[4]]
        for row in conn.execute(
            "SELECT bucket, key_id, press_count, duration_total_ms, duration_max_ms "
            "FROM agg_key_day"
        )
    }
    assert from_agg == pytest.approx(reference["per_day"])

    per_day_app = {
        (row[0], row[1], row[2]): [row[3], row[4], row[5]]
        for row in conn.execute(
            "SELECT day_bucket, app_id, key_id, press_count, duration_total_ms,"
            " duration_max_ms FROM agg_key_app_day"
        )
    }
    assert per_day_app == pytest.approx(reference["per_day_app"])

    per_app = {
        (row[0], row[1]): [row[2], row[3], row[4]]
        for row in conn.execute(
            "SELECT app_id, key_id, press_count, duration_total_ms, duration_max_ms "
            "FROM agg_app_key_total"
        )
    }
    assert per_app == pytest.approx(reference["per_app"])

    per_hour = {
        (row[0], row[1], row[2]): [row[3], row[4]]
        for row in conn.execute(
            "SELECT day_bucket, hour, key_id, press_count, duration_total_ms FROM agg_key_hour"
        )
    }
    assert per_hour == pytest.approx(
        {key: value[:2] for key, value in reference["per_hour"].items()}
    )


def test_every_key_aggregate_level_sums_to_the_same_total(database):
    """日 → 月 → 年 → 总计 → 小时 → 应用×键，七张表必须给出同一个总数。

    它们由同一个事务里的七条 upsert 维护；不相等就意味着聚合漂移（R6），而这类问题
    不主动核对就永远不会被发现。
    """
    writer, queue, registry = _writer(database)
    for event in generate_key_events(
        registry, days=5, per_day=800, apps=["code.exe", "chrome.exe", "term.exe"]
    ):
        queue.put(event)
    _drain(writer, queue)

    conn = database.connect()
    totals = {
        table: conn.execute(f"SELECT SUM(press_count) FROM {table}").fetchone()[0]
        for table in (
            "agg_key_day",
            "agg_key_month",
            "agg_key_year",
            "agg_key_total",
            "agg_key_hour",
            "agg_key_app_day",
            "agg_app_key_total",
        )
    }
    assert len(set(totals.values())) == 1, totals
    assert totals["agg_key_day"] == 4000

    durations = {
        table: conn.execute(f"SELECT SUM(duration_total_ms) FROM {table}").fetchone()[0]
        for table in (
            "agg_key_day",
            "agg_key_month",
            "agg_key_year",
            "agg_key_total",
            "agg_key_hour",
            "agg_key_app_day",
            "agg_app_key_total",
        )
    }
    assert len(set(durations.values())) == 1, durations


# ── 会话侧的聚合 ──────────────────────────────────────────────────────────
def _session(start: datetime, minutes: float, app_id: int, **kwargs) -> UsageSession:
    start_ns = int(start.timestamp() * 1_000_000_000)
    end_ns = start_ns + int(minutes * 60 * 1_000_000_000)
    return UsageSession(
        app_id=app_id,
        start_ts_ns=start_ns,
        end_ts_ns=end_ns,
        duration_ms=(end_ns - start_ns) // 1_000_000,
        **kwargs,
    )


def test_session_durations_agree_across_every_aggregate_level(database):
    """``usage_session`` → ``agg_app_{day,month,year,total,hour}`` 必须处处等量。"""
    writer, queue, registry = _writer(database)
    app_id = _app(registry, "code.exe")
    other = _app(registry, "chrome.exe")
    queue.put(_session(DAY_ONE, 35, app_id))
    queue.put(_session(DAY_ONE + timedelta(hours=2), 12.5, other))
    queue.put(_session(DAY_ONE + timedelta(days=1), 90, app_id))
    _drain(writer, queue)

    conn = database.connect()
    expected = conn.execute("SELECT SUM(duration_ms) FROM usage_session").fetchone()[0]
    for table in ("agg_app_day", "agg_app_month", "agg_app_year", "agg_app_total",
                  "agg_app_hour"):
        actual = conn.execute(f"SELECT SUM(duration_ms) FROM {table}").fetchone()[0]
        assert actual == expected, f"{table} 与 usage_session 不一致"
    assert UsageRepository(database).day_total_ms("2026-08-30") == (35 + 12.5) * 60 * 1000


def test_a_session_crossing_midnight_is_split_but_counted_once(database):
    """时长分摊到两天，``session_count`` 只在起始桶 +1。

    两边都 +1 会让"平均会话时长"这类指标失真——它是 03 文档 §3.3 明确点出的易错点。
    """
    writer, queue, registry = _writer(database)
    app_id = _app(registry, "code.exe")
    start = datetime(2026, 8, 31, 23, 40, tzinfo=TZ)
    queue.put(_session(start, 40, app_id))  # 23:40 → 00:20
    _drain(writer, queue)

    conn = database.connect()
    rows = {
        row[0]: (row[1], row[2])
        for row in conn.execute(
            "SELECT day_bucket, duration_ms, session_count FROM agg_app_day ORDER BY day_bucket"
        )
    }
    assert rows == {"2026-08-31": (20 * 60 * 1000, 1), "2026-09-01": (20 * 60 * 1000, 0)}
    assert conn.execute("SELECT session_count FROM agg_app_total").fetchone()[0] == 1
    # 原始会话行的 day_bucket 是**起始**日，这样"最近的会话"列表不会错位。
    assert conn.execute("SELECT day_bucket FROM usage_session").fetchone()[0] == "2026-08-31"


def test_a_session_crossing_a_month_lands_in_both_month_buckets(database):
    writer, queue, registry = _writer(database)
    app_id = _app(registry, "code.exe")
    queue.put(_session(datetime(2026, 8, 31, 23, 30, tzinfo=TZ), 60, app_id))
    _drain(writer, queue)

    conn = database.connect()
    months = {
        row[0]: row[1]
        for row in conn.execute("SELECT month_bucket, duration_ms FROM agg_app_month")
    }
    assert months == {"2026-08": 30 * 60 * 1000, "2026-09": 30 * 60 * 1000}


def test_idle_trimmed_flag_survives_to_the_row(database):
    """这一位让"这段时长是被空闲截断过的"可审计，不然截断逻辑改错了也看不出来。"""
    writer, queue, registry = _writer(database)
    app_id = _app(registry, "code.exe")
    queue.put(_session(DAY_ONE, 10, app_id, idle_trimmed=True))
    _drain(writer, queue)
    assert database.connect().execute(
        "SELECT idle_trimmed FROM usage_session"
    ).fetchone()[0] == 1


def test_zero_length_sessions_are_ignored(database):
    writer, queue, registry = _writer(database)
    app_id = _app(registry, "code.exe")
    start_ns = int(DAY_ONE.timestamp() * 1_000_000_000)
    queue.put(UsageSession(app_id=app_id, start_ts_ns=start_ns, end_ts_ns=start_ns,
                           duration_ms=0))
    _drain(writer, queue)
    assert database.connect().execute("SELECT COUNT(*) FROM usage_session").fetchone()[0] == 0


def test_unknown_app_sessions_and_keys_are_kept_under_the_sentinel(database):
    """哨兵行必须能承载数据：否则"未知"这一类会在聚合里凭空消失。"""
    writer, queue, _registry = _writer(database)
    queue.put(_key_event(DAY_ONE, "key_a", 0, confidence="unknown"))
    queue.put(_session(DAY_ONE, 5, 0))
    _drain(writer, queue)

    conn = database.connect()
    assert conn.execute(
        "SELECT press_count FROM agg_app_key_total WHERE app_id = 0"
    ).fetchone()[0] == 1
    assert conn.execute("SELECT duration_ms FROM agg_app_total WHERE app_id = 0").fetchone()[0]


# ── 原子性、重启、可观测性（11 文档 §4.2）─────────────────────────────────
def test_writer_batch_is_atomic_on_failure(database, monkeypatch):
    """一批写到一半失败必须**不留**任何部分聚合行。

    否则一次磁盘抖动就能让 ``agg_key_day`` 多算而 ``raw_key_events`` 没写进去，
    而这个偏差此后永远无法自愈——聚合表是累加的。
    """
    writer, queue, registry = _writer(database)
    app_id = _app(registry, "code.exe")
    for index in range(50):
        queue.put(_key_event(DAY_ONE + timedelta(seconds=index), "key_a", app_id))

    original = StorageWriter._persist
    calls = {"n": 0}

    def explode(self, conn, rollup, now, **kwargs):
        calls["n"] += 1
        original(self, conn, rollup, now, **kwargs)  # 先真的写一部分
        raise RuntimeError("模拟落盘中途失败")

    monkeypatch.setattr(StorageWriter, "_persist", explode)
    writer.flush_once()

    conn = database.connect()
    assert calls["n"] == 1
    assert conn.execute("SELECT COUNT(*) FROM agg_key_day").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM agg_key_app_day").fetchone()[0] == 0
    assert writer.stats.write_errors == 1
    # 整批放回队首等待重试，不丢。
    assert queue.depth == 50

    monkeypatch.setattr(StorageWriter, "_persist", original)
    _drain(writer, queue)
    assert conn.execute("SELECT SUM(press_count) FROM agg_key_day").fetchone()[0] == 50


def test_a_poison_batch_is_abandoned_instead_of_spinning_forever(database, monkeypatch):
    """无限重试会让写线程永久空转，队列里后面的事件全部饿死。"""
    writer, queue, registry = _writer(database)
    app_id = _app(registry, "code.exe")
    queue.put(_key_event(DAY_ONE, "key_a", app_id))

    def always_fail(self, conn, rollup, now, **kwargs):
        raise RuntimeError("毒药批次")

    monkeypatch.setattr(StorageWriter, "_persist", always_fail)
    for _ in range(6):
        writer.flush_once()

    assert writer.stats.abandoned_batches == 1
    assert database.connect().execute(
        "SELECT write_errors FROM health_stat"
    ).fetchone()[0] >= 1


def test_partition_cache_is_not_poisoned_by_a_rolled_back_data_transaction(
    database, monkeypatch
):
    """月表 DDL 走独立事务先提交——这是真实踩过的一个坑。

    如果建表发生在数据事务里，事务回滚会把表一起撤掉，而进程内缓存已经记下"建过了"，
    之后**每一批**都报 ``no such table`` 直到重启。断言：一次失败之后，重试能成功。
    """
    writer, queue, registry = _writer(database)
    app_id = _app(registry, "code.exe")
    queue.put(_key_event(DAY_ONE, "key_a", app_id))

    original = StorageWriter._persist
    monkeypatch.setattr(
        StorageWriter,
        "_persist",
        lambda self, conn, rollup, now, **kwargs: (_ for _ in ()).throw(RuntimeError("失败")),
    )
    writer.flush_once()
    assert queue.depth == 1

    monkeypatch.setattr(StorageWriter, "_persist", original)
    _drain(writer, queue)
    assert database.connect().execute(
        "SELECT SUM(press_count) FROM agg_key_day"
    ).fetchone()[0] == 1


def test_restart_does_not_double_count(database, tmp_path):
    """队列是内存的、drain 完就没了——重开数据库不该让任何计数翻倍。"""
    writer, queue, registry = _writer(database)
    app_id = _app(registry, "code.exe")
    for index in range(100):
        queue.put(_key_event(DAY_ONE + timedelta(seconds=index), "key_a", app_id))
    _drain(writer, queue)
    before = database.connect().execute(
        "SELECT SUM(press_count) FROM agg_key_total"
    ).fetchone()[0]

    # 第二个 writer 实例（模拟重启），队列已空，不该再写入任何东西。
    writer2, _queue2, _ = _writer(database)
    writer2.flush_once()
    after = database.connect().execute(
        "SELECT SUM(press_count) FROM agg_key_total"
    ).fetchone()[0]
    assert before == after == 100


def test_dropped_events_are_recorded_in_health_stat(database):
    """丢弃必须可见：静默丢弃会让用户在不知情的情况下拿到错误统计。"""
    queue = EventQueue(maxsize=5)
    registry = AppRegistry(database, "windows")
    writer = StorageWriter(database, queue, tz=TZ, registry=registry)
    app_id = _app(registry, "code.exe")
    for index in range(20):
        queue.put(_key_event(DAY_ONE + timedelta(seconds=index), "key_a", app_id))
    assert queue.dropped == 15
    _drain(writer, queue)

    dropped = database.connect().execute(
        "SELECT SUM(dropped_events) FROM health_stat"
    ).fetchone()[0]
    assert dropped == 15


def test_drops_after_the_last_batch_still_reach_health_stat(database):
    """丢弃发生在最后一批之后时，不落盘就永远丢了这个事实。"""
    queue = EventQueue(maxsize=1)
    writer = StorageWriter(database, queue, tz=TZ)
    for _ in range(4):
        queue.put(_key_event(DAY_ONE, "key_a", 0))
    queue.drain_all()  # 事件被别处取走，只剩计数
    writer.flush_once()

    assert database.connect().execute(
        "SELECT SUM(dropped_events) FROM health_stat"
    ).fetchone()[0] == 3


# ── 分表、配置开关与旁路数据 ───────────────────────────────────────────────
def test_events_are_partitioned_by_local_month(database):
    writer, queue, registry = _writer(database)
    app_id = _app(registry, "code.exe")
    queue.put(_key_event(datetime(2026, 8, 31, 23, 59, tzinfo=TZ), "key_a", app_id))
    queue.put(_key_event(datetime(2026, 9, 1, 0, 1, tzinfo=TZ), "key_a", app_id))
    _drain(writer, queue)

    conn = database.connect()
    assert Partitions.existing_months(conn) == ["2026-08", "2026-09"]
    for month, expected in (("2026-08", 1), ("2026-09", 1)):
        table = raw_table(month)
        assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == expected


def test_store_raw_false_keeps_aggregates_but_writes_no_raw_events(database):
    """关掉原始事件记录后热力图仍要可用——只有依赖原始事件的洞察项不可用（06 文档）。"""
    writer, queue, registry = _writer(database, store_raw=False)
    app_id = _app(registry, "code.exe")
    for index in range(20):
        queue.put(_key_event(DAY_ONE + timedelta(seconds=index), "key_a", app_id))
    _drain(writer, queue)

    conn = database.connect()
    assert Partitions.existing_months(conn) == []
    assert conn.execute("SELECT SUM(press_count) FROM agg_key_total").fetchone()[0] == 20
    assert KeyRepository(database).app_heatmap(app_id)["key_a"]["press_count"] == 20


def test_capability_snapshot_is_refreshed_on_every_batch(database):
    """写线程与生命周期写的是**同一行**，取值也来自同一个函数。

    两处各算一遍必然漂移，而这张表的全部价值就在于它能解释历史数据——写错了比不写更糟
    （03 文档 §2.8）。
    """
    writer, queue, registry = _writer(database)
    writer.set_capability_provider(
        lambda: {
            "platform_id": "windows",
            "keyboard_backend": "raw_input",
            "foreground_available": True,
            "titles_recorded": False,
            "key_position_stable": True,
        }
    )
    queue.put(_key_event(DAY_ONE, "key_a", _app(registry, "code.exe")))
    _drain(writer, queue)

    row = database.connect().execute(
        "SELECT platform_id, keyboard_backend, key_position_stable FROM capture_capability"
    ).fetchone()
    assert row["keyboard_backend"] == "raw_input"
    assert row["key_position_stable"] == 1


def test_a_failing_capability_provider_does_not_lose_the_batch(database):
    """能力快照是旁路信息，它取不到不该让真实数据落不了盘。"""
    writer, queue, registry = _writer(database)

    def boom() -> dict:
        raise RuntimeError("provider 坏了")

    writer.set_capability_provider(boom)
    queue.put(_key_event(DAY_ONE, "key_a", _app(registry, "code.exe")))
    _drain(writer, queue)
    assert database.connect().execute(
        "SELECT SUM(press_count) FROM agg_key_total"
    ).fetchone()[0] == 1


def test_data_version_increases_so_the_frontend_can_skip_redraws(database):
    """让前端"值没变就跳过重绘"（05 文档 §1.4），取代固定 1 秒轮询全量重绘。"""
    writer, queue, registry = _writer(database)
    app_id = _app(registry, "code.exe")
    assert int(database.meta_get("data_version", "0")) == 0

    queue.put(_key_event(DAY_ONE, "key_a", app_id))
    _drain(writer, queue)
    first = int(database.meta_get("data_version", "0"))
    assert first >= 1

    queue.put(_key_event(DAY_ONE + timedelta(seconds=1), "key_a", app_id))
    _drain(writer, queue)
    assert int(database.meta_get("data_version", "0")) > first


def test_an_empty_batch_does_not_bump_data_version(database):
    writer, _queue, _registry = _writer(database)
    writer.flush_once()
    assert int(database.meta_get("data_version", "0") or 0) == 0


def test_touched_apps_get_their_last_seen_refreshed(database):
    writer, queue, registry = _writer(database)
    app_id = _app(registry, "code.exe")
    conn = database.connect()
    before = conn.execute("SELECT last_seen_at FROM app WHERE id = ?", (app_id,)).fetchone()[0]

    later = DAY_ONE + timedelta(days=2)
    queue.put(_key_event(later, "key_a", app_id))
    _drain(writer, queue)
    after = conn.execute("SELECT last_seen_at FROM app WHERE id = ?", (app_id,)).fetchone()[0]
    assert after >= before


def test_the_sentinel_app_is_never_touched(database):
    """哨兵行不是一个真实应用，给它刷 ``last_seen_at`` 会让"最近使用"列表出现"未知"。"""
    writer, queue, _registry = _writer(database)
    conn = database.connect()
    before = conn.execute("SELECT last_seen_at FROM app WHERE id = 0").fetchone()[0]
    queue.put(_key_event(DAY_ONE, "key_a", 0))
    _drain(writer, queue)
    assert conn.execute("SELECT last_seen_at FROM app WHERE id = 0").fetchone()[0] == before


def test_writer_thread_drains_everything_on_stop(database):
    """停机时必须 drain，否则最后一批（最多 1 秒的事件）会丢。"""
    writer, queue, registry = _writer(database)
    app_id = _app(registry, "code.exe")
    writer.start()
    for index in range(300):
        queue.put(_key_event(DAY_ONE + timedelta(seconds=index), "key_e", app_id))
    writer.stop(timeout=5.0)

    assert queue.depth == 0
    assert database.connect().execute(
        "SELECT SUM(press_count) FROM agg_key_total"
    ).fetchone()[0] == 300
    assert writer.running is False


def test_snapshot_exposes_queue_depth_and_drops(database):
    writer, queue, _registry = _writer(database)
    queue.put(_key_event(DAY_ONE, "key_a", 0))
    snapshot = writer.snapshot()
    assert snapshot["queue_depth"] == 1
    assert snapshot["dropped_events"] == 0
    assert snapshot["batches"] == 0
