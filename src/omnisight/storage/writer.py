"""单写线程：批量落盘 + 增量维护全部聚合表（03 文档 §4、02 文档 §3.1）。

**它是全库唯一的写者**（``AppRegistry`` 发现新应用时的那一行除外）。这条约束换来两件事：
聚合表与原始表永远在同一个事务里更新，因此不可能出现"聚合多算了但原始事件没写进去"；
以及采集线程完全不接触 SQLite，热路径上没有任何可能阻塞几十毫秒的操作。

**先在内存里 rollup，再落盘**是这里最关键的优化。KeyTrace 现状是每个按键执行 5 条 SQL，
一批 500 键就是 2500 条。先在 ``dict`` 里合并——同一天同一键的 200 次按下变成 1 条
upsert——实际 SQL 数量通常降到几十条。

**跨小时/跨日会话在写入时切片**。查询"某日总时长"必须走 ``agg_app_day``（切分正确），
而不是 ``SUM(usage_session.duration_ms) WHERE day_bucket = ?``（把跨日会话全算给起始日）。
这是 03 文档 §3.3 点明的易错点，也是本文件把切片逻辑放在写入侧、只做一次的理由。
``session_count`` 只在**起始**桶 +1，否则一段跨日会话会被数成两段。
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, tzinfo
from sqlite3 import Connection

from ..capture.models import KeyEvent, UsageSession
from ..capture.queue import Event, EventQueue
from ..core.clock import Clock, SystemClock
from . import capability as capability_table
from .database import Database
from .partitions import Partitions
from .repositories.apps import AppRegistry
from .schema import UNKNOWN_APP_ID

logger = logging.getLogger(__name__)

BATCH_MAX_SIZE = 500
#: 03 文档 §4.1 写 2 秒、04 文档 §5.2 写 1 秒。取 1 秒：01 文档 §4 的"写入延迟 ≤ 2s"
#: 是外沿要求，1 秒稳稳在内，且让"刚敲的键计数涨了"更快可见。
BATCH_MAX_WAIT_SECONDS = 1.0
#: 同一批连续失败这么多次后放弃它，避免一条毒药记录让写线程永久空转。
MAX_BATCH_RETRIES = 5
HOUR_NS = 3_600_000_000_000

_AGG_KEY_BUCKET_UPSERT = """
INSERT INTO agg_key_{grain} (bucket, key_id, press_count, duration_total_ms, duration_max_ms)
VALUES (?, ?, ?, ?, ?)
ON CONFLICT(bucket, key_id) DO UPDATE SET
    press_count       = agg_key_{grain}.press_count + excluded.press_count,
    duration_total_ms = agg_key_{grain}.duration_total_ms + excluded.duration_total_ms,
    duration_max_ms   = MAX(agg_key_{grain}.duration_max_ms, excluded.duration_max_ms)
"""

AGG_KEY_TOTAL_UPSERT = """
INSERT INTO agg_key_total (key_id, press_count, duration_total_ms, duration_max_ms)
VALUES (?, ?, ?, ?)
ON CONFLICT(key_id) DO UPDATE SET
    press_count       = agg_key_total.press_count + excluded.press_count,
    duration_total_ms = agg_key_total.duration_total_ms + excluded.duration_total_ms,
    duration_max_ms   = MAX(agg_key_total.duration_max_ms, excluded.duration_max_ms)
"""

AGG_KEY_HOUR_UPSERT = """
INSERT INTO agg_key_hour (day_bucket, hour, key_id, press_count, duration_total_ms)
VALUES (?, ?, ?, ?, ?)
ON CONFLICT(day_bucket, hour, key_id) DO UPDATE SET
    press_count       = agg_key_hour.press_count + excluded.press_count,
    duration_total_ms = agg_key_hour.duration_total_ms + excluded.duration_total_ms
"""

AGG_KEY_APP_DAY_UPSERT = """
INSERT INTO agg_key_app_day (
    day_bucket, app_id, key_id, press_count, duration_total_ms, duration_max_ms
) VALUES (?, ?, ?, ?, ?, ?)
ON CONFLICT(day_bucket, app_id, key_id) DO UPDATE SET
    press_count       = agg_key_app_day.press_count + excluded.press_count,
    duration_total_ms = agg_key_app_day.duration_total_ms + excluded.duration_total_ms,
    duration_max_ms   = MAX(agg_key_app_day.duration_max_ms, excluded.duration_max_ms)
"""

AGG_APP_KEY_TOTAL_UPSERT = """
INSERT INTO agg_app_key_total (app_id, key_id, press_count, duration_total_ms, duration_max_ms)
VALUES (?, ?, ?, ?, ?)
ON CONFLICT(app_id, key_id) DO UPDATE SET
    press_count       = agg_app_key_total.press_count + excluded.press_count,
    duration_total_ms = agg_app_key_total.duration_total_ms + excluded.duration_total_ms,
    duration_max_ms   = MAX(agg_app_key_total.duration_max_ms, excluded.duration_max_ms)
"""

_AGG_APP_BUCKET_UPSERT = """
INSERT INTO agg_app_{grain} ({bucket}, app_id, duration_ms, session_count)
VALUES (?, ?, ?, ?)
ON CONFLICT({bucket}, app_id) DO UPDATE SET
    duration_ms   = agg_app_{grain}.duration_ms + excluded.duration_ms,
    session_count = agg_app_{grain}.session_count + excluded.session_count
"""

AGG_APP_TOTAL_UPSERT = """
INSERT INTO agg_app_total (app_id, duration_ms, session_count, last_used_ts_ns)
VALUES (?, ?, ?, ?)
ON CONFLICT(app_id) DO UPDATE SET
    duration_ms     = agg_app_total.duration_ms + excluded.duration_ms,
    session_count   = agg_app_total.session_count + excluded.session_count,
    last_used_ts_ns = MAX(agg_app_total.last_used_ts_ns, excluded.last_used_ts_ns)
"""

AGG_APP_HOUR_UPSERT = """
INSERT INTO agg_app_hour (day_bucket, hour, app_id, duration_ms)
VALUES (?, ?, ?, ?)
ON CONFLICT(day_bucket, hour, app_id) DO UPDATE SET
    duration_ms = agg_app_hour.duration_ms + excluded.duration_ms
"""

USAGE_SESSION_INSERT = """
INSERT INTO usage_session (
    app_id, window_title, start_ts_ns, end_ts_ns, duration_ms, day_bucket, idle_trimmed
) VALUES (?, ?, ?, ?, ?, ?, ?)
"""

HEALTH_STAT_UPSERT = """
INSERT INTO health_stat (day_bucket, dropped_events, write_errors, capture_downtime_ms)
VALUES (?, ?, ?, 0)
ON CONFLICT(day_bucket) DO UPDATE SET
    dropped_events = health_stat.dropped_events + excluded.dropped_events,
    write_errors   = health_stat.write_errors + excluded.write_errors
"""

AGG_KEY_DAY_UPSERT = _AGG_KEY_BUCKET_UPSERT.format(grain="day")
AGG_KEY_MONTH_UPSERT = _AGG_KEY_BUCKET_UPSERT.format(grain="month")
AGG_KEY_YEAR_UPSERT = _AGG_KEY_BUCKET_UPSERT.format(grain="year")
AGG_APP_DAY_UPSERT = _AGG_APP_BUCKET_UPSERT.format(grain="day", bucket="day_bucket")
AGG_APP_MONTH_UPSERT = _AGG_APP_BUCKET_UPSERT.format(grain="month", bucket="month_bucket")
AGG_APP_YEAR_UPSERT = _AGG_APP_BUCKET_UPSERT.format(grain="year", bucket="year_bucket")


def day_bucket(ts_ns: int, tz: tzinfo | None) -> str:
    return datetime.fromtimestamp(ts_ns / 1_000_000_000, tz=tz).strftime("%Y-%m-%d")


def hour_of(ts_ns: int, tz: tzinfo | None) -> int:
    return datetime.fromtimestamp(ts_ns / 1_000_000_000, tz=tz).hour


def split_by_hour(
    start_ts_ns: int, end_ts_ns: int, tz: tzinfo | None
) -> list[tuple[str, int, int]]:
    """把 ``[start, end)`` 切成 ``(day_bucket, hour, duration_ms)`` 片段。

    每片不跨小时、不跨日，因此 ``agg_app_hour`` 与 ``agg_app_day`` 都能直接累加，
    查询期不需要任何 ``strftime``。

    **夏令时**：每片额外以一小时为上限。跳变日有 23 或 25 小时——回拨那天的 01 点会
    出现两次，两次都累加到同一个 ``(day, 1)`` 桶里，这是对的（那天的 1 点确实过了两遍）；
    前拨那天缺失的 02 点则自然一片都没有。时长总量在两种情况下都守恒，这比"每天固定
    24 格"重要得多（03 文档 §3.3）。
    """
    if end_ts_ns <= start_ts_ns:
        return []
    slices: list[tuple[str, int, int]] = []
    cursor = start_ts_ns
    while cursor < end_ts_ns:
        moment = datetime.fromtimestamp(cursor / 1_000_000_000, tz=tz)
        boundary = moment.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        next_ns = int(boundary.timestamp() * 1_000_000_000)
        if next_ns <= cursor:  # pragma: no cover - 异常时区的保险
            next_ns = cursor + HOUR_NS
        stop = min(next_ns, cursor + HOUR_NS, end_ts_ns)
        slices.append([moment.strftime("%Y-%m-%d"), moment.hour, (stop - cursor) // 1_000_000])
        cursor = stop
    # 每片各自整除会累积出几毫秒的差额，让"日之和 != 总计"。把余数交给最后一片，
    # 各级聚合之间就精确一致（一致性测试会盯住这一点）。
    total_ms = (end_ts_ns - start_ts_ns) // 1_000_000
    slices[-1][2] += total_ms - sum(item[2] for item in slices)
    return [(day, hour, duration) for day, hour, duration in slices]


@dataclass(slots=True)
class WriterStats:
    batches: int = 0
    key_events: int = 0
    sessions: int = 0
    write_errors: int = 0
    abandoned_batches: int = 0
    last_flush_at: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "batches": self.batches,
            "key_events": self.key_events,
            "sessions": self.sessions,
            "write_errors": self.write_errors,
            "abandoned_batches": self.abandoned_batches,
            "last_flush_at": self.last_flush_at,
        }


@dataclass(slots=True)
class _Rollup:
    """一批事件在内存里合并后的结果。键是主键元组，值是累加量。"""

    raw_by_month: dict[str, list[tuple]] = field(default_factory=dict)
    key_day: dict[tuple[str, str], list[float]] = field(default_factory=dict)
    key_month: dict[tuple[str, str], list[float]] = field(default_factory=dict)
    key_year: dict[tuple[str, str], list[float]] = field(default_factory=dict)
    key_total: dict[str, list[float]] = field(default_factory=dict)
    key_hour: dict[tuple[str, int, str], list[float]] = field(default_factory=dict)
    key_app_day: dict[tuple[str, int, str], list[float]] = field(default_factory=dict)
    app_key_total: dict[tuple[int, str], list[float]] = field(default_factory=dict)
    sessions: list[tuple] = field(default_factory=list)
    app_day: dict[tuple[str, int], list[int]] = field(default_factory=dict)
    app_month: dict[tuple[str, int], list[int]] = field(default_factory=dict)
    app_year: dict[tuple[str, int], list[int]] = field(default_factory=dict)
    app_total: dict[int, list[int]] = field(default_factory=dict)
    app_hour: dict[tuple[str, int, int], int] = field(default_factory=dict)
    touched_apps: set[int] = field(default_factory=set)
    key_count: int = 0
    session_count: int = 0

    @property
    def empty(self) -> bool:
        return self.key_count == 0 and self.session_count == 0


def _accumulate(target: dict, key, count: float, total: float, maximum: float) -> None:
    slot = target.get(key)
    if slot is None:
        target[key] = [count, total, maximum]
        return
    slot[0] += count
    slot[1] += total
    slot[2] = max(slot[2], maximum)


def _accumulate_pair(target: dict, key, count: float, total: float) -> None:
    slot = target.get(key)
    if slot is None:
        target[key] = [count, total]
        return
    slot[0] += count
    slot[1] += total


class StorageWriter:
    """把 :class:`EventQueue` 里的事实批量落盘，并同事务维护全部聚合。"""

    def __init__(
        self,
        db: Database,
        queue: EventQueue,
        *,
        tz: tzinfo | None = None,
        store_raw: bool = True,
        registry: AppRegistry | None = None,
        capability_provider: Callable[[], dict] | None = None,
        clock: Clock | None = None,
        checkpoint_interval_seconds: float = 300.0,
        batch_max_size: int = BATCH_MAX_SIZE,
        batch_max_wait_seconds: float = BATCH_MAX_WAIT_SECONDS,
    ) -> None:
        self._db = db
        self._queue = queue
        self._tz = tz
        self._store_raw = store_raw
        self._registry = registry
        self._capability_provider = capability_provider
        #: 只用于「现在几点」（last_seen_at、health_stat 与 capture_capability 的日期桶），
        #: 与事件自带的时间戳无关。注入它是为了让"某天的数据必须有对应的能力快照"这类
        #: 断言能在虚拟时间下成立（11 文档 §2）。
        self._clock = clock or SystemClock(tz)
        self._checkpoint_interval = checkpoint_interval_seconds
        self._batch_max_size = batch_max_size
        self._batch_max_wait = batch_max_wait_seconds
        self._partitions = Partitions()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._last_checkpoint_mono = time.monotonic()
        self._retries = 0
        #: 已从队列取出但尚未成功写进 health_stat 的丢弃数。写失败时必须留着，
        #: 否则重试成功后这一笔就永远不见了——而「丢事件必须可见」是硬要求。
        self._pending_dropped = 0
        self.stats = WriterStats()

    def set_capability_provider(self, provider: Callable[[], dict] | None) -> None:
        """设置能力快照来源。

        单独开一个 setter 而不是只在构造时传：写线程要先于采集启动（否则采集一开始就
        往一个没人消费的队列里堆），而**有效能力**只有在采集启动之后才知道
        （02 文档 §5.1 的能力语义表）。
        """
        self._capability_provider = provider

    # ── 生命周期 ────────────────────────────────────────────────────────
    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="storage-writer", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        """停止并 drain。剩余事件在超时后会丢，届时**明确记 warning 而不是静默丢弃**。"""
        self._stop.set()
        self._queue.wake()
        thread, self._thread = self._thread, None
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=timeout)
        remaining = self.drain(deadline_seconds=timeout)
        if remaining:
            logger.warning("停机时仍有 %s 条事件未能落盘", remaining)

    def snapshot(self) -> dict[str, object]:
        return {
            "running": self.running,
            "queue_depth": self._queue.depth,
            "dropped_events": self._queue.dropped,
            **self.stats.as_dict(),
        }

    # ── 主循环 ──────────────────────────────────────────────────────────
    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.flush_once()
                self._maybe_checkpoint()
            except Exception:
                # 写线程绝不允许死掉：它死了以后所有采集都变成纯内存丢弃。
                logger.exception("写入线程异常，继续运行")
                self._stop.wait(1.0)
        # 退出前尽力清空，与 stop() 的 drain 是两条互补的路径（正常退出 / 被 join 前）。
        self.drain(deadline_seconds=self._batch_max_wait)

    def flush_once(self) -> int:
        """取一批并写入，返回写入条数。**公开是为了可测**：测试不必等线程调度。"""
        batch = self._queue.drain(self._batch_max_size, self._batch_max_wait)
        if not batch:
            self._flush_counters_only()
            return 0
        return self._write_batch(batch)

    def drain(self, *, deadline_seconds: float = 5.0) -> int:
        """把队列清空，返回**未能**写入的条数。"""
        deadline = time.monotonic() + deadline_seconds
        while True:
            batch = self._queue.drain(self._batch_max_size, 0.0)
            if not batch:
                self._flush_counters_only()
                return 0
            if time.monotonic() > deadline:
                self._queue.put_back(batch)
                return self._queue.depth
            self._write_batch(batch)

    def _maybe_checkpoint(self) -> None:
        """周期性 WAL checkpoint（03 文档 §6.3）。

        由写线程顺手做，而不是另起一个维护线程：它已经持有写连接、每秒醒一次，而独立
        的维护连接还得与写线程互斥。归档与 ``incremental_vacuum`` 那些真正耗时的维护
        排在 M7，届时再拆出线程。
        """
        if self._checkpoint_interval <= 0:
            return
        now = time.monotonic()
        if now - self._last_checkpoint_mono < self._checkpoint_interval:
            return
        self._last_checkpoint_mono = now
        try:
            self._db.checkpoint("PASSIVE")
        except Exception:  # pragma: no cover - checkpoint 失败不影响正确性
            logger.debug("WAL checkpoint 失败", exc_info=True)

    # ── 写入 ────────────────────────────────────────────────────────────
    def _write_batch(self, batch: list[Event]) -> int:
        rollup = self._build_rollup(batch)
        now = self._clock.now()
        self._pending_dropped += self._queue.take_dropped()
        dropped = self._pending_dropped
        try:
            self._ensure_partitions(rollup)
            with self._db.transaction() as conn:
                self._persist(conn, rollup, now, dropped=dropped, write_errors=0)
        except Exception:
            self.stats.write_errors += 1
            self._retries += 1
            if self._retries >= MAX_BATCH_RETRIES:
                self.stats.abandoned_batches += 1
                self._retries = 0
                logger.exception(
                    "同一批事件连续写入失败 %s 次，放弃该批（%s 条）",
                    MAX_BATCH_RETRIES,
                    len(batch),
                )
                self._record_failure(dropped=dropped, now=now)
                return 0
            logger.exception("批量写入失败，将重试（第 %s 次）", self._retries)
            self._queue.put_back(batch)
            self._stop.wait(min(0.5 * self._retries, 2.0))
            return 0

        self._retries = 0
        self._pending_dropped = 0
        self.stats.batches += 1
        self.stats.key_events += rollup.key_count
        self.stats.sessions += rollup.session_count
        self.stats.last_flush_at = now.isoformat(timespec="seconds")
        return rollup.key_count + rollup.session_count

    def _flush_counters_only(self) -> None:
        """空闲时也要把丢弃计数落进 ``health_stat``——否则丢弃发生在最后一批之后就丢了。"""
        self._pending_dropped += self._queue.take_dropped()
        if not self._pending_dropped:
            return
        now = self._clock.now()
        try:
            with self._db.transaction() as conn:
                conn.execute(
                    HEALTH_STAT_UPSERT, (day_bucket_of(now), self._pending_dropped, 0)
                )
            self._pending_dropped = 0
        except Exception:  # pragma: no cover
            logger.debug("写入 health_stat 失败", exc_info=True)

    def _record_failure(self, *, dropped: int, now: datetime) -> None:
        try:
            with self._db.transaction() as conn:
                conn.execute(HEALTH_STAT_UPSERT, (day_bucket_of(now), dropped, 1))
            self._pending_dropped = 0
        except Exception:  # pragma: no cover - 连 health_stat 都写不进去只能记日志
            logger.error("无法记录写入失败计数")

    def _ensure_partitions(self, rollup: _Rollup) -> None:
        """月表的 DDL 走**独立事务**先提交，不与数据事务共命运。

        它必须在数据事务之外：数据事务失败会回滚，把刚建的表一起撤掉，而
        :class:`Partitions` 的缓存已经记下「建过了」——之后每一批都报
        ``no such table`` 直到进程重启。建一张空表本身不是数据写入，提前提交没有
        一致性代价（崩溃最多留下一张空表）。
        """
        if not rollup.raw_by_month:
            return
        pending = [
            month for month in rollup.raw_by_month if not self._partitions.knows(month)
        ]
        if not pending:
            return
        try:
            with self._db.transaction() as conn:
                for month in pending:
                    self._partitions.ensure(conn, month)
        except Exception:
            self._partitions.reset()
            raise

    def _persist(
        self,
        conn: Connection,
        rollup: _Rollup,
        now: datetime,
        *,
        dropped: int,
        write_errors: int,
    ) -> None:
        """一个事务内写完原始事件与全部聚合。要么全进，要么全不进。"""
        if self._store_raw:
            for month, rows in rollup.raw_by_month.items():
                table = self._partitions.ensure(conn, month)
                conn.executemany(Partitions.insert_sql(table), rows)

        _executemany(conn, AGG_KEY_DAY_UPSERT, _rows(rollup.key_day))
        _executemany(conn, AGG_KEY_MONTH_UPSERT, _rows(rollup.key_month))
        _executemany(conn, AGG_KEY_YEAR_UPSERT, _rows(rollup.key_year))
        _executemany(
            conn,
            AGG_KEY_TOTAL_UPSERT,
            [(key_id, *values) for key_id, values in rollup.key_total.items()],
        )
        _executemany(
            conn,
            AGG_KEY_HOUR_UPSERT,
            [(day, hour, key_id, values[0], values[1])
             for (day, hour, key_id), values in rollup.key_hour.items()],
        )
        _executemany(
            conn,
            AGG_KEY_APP_DAY_UPSERT,
            [(day, app_id, key_id, *values)
             for (day, app_id, key_id), values in rollup.key_app_day.items()],
        )
        _executemany(
            conn,
            AGG_APP_KEY_TOTAL_UPSERT,
            [(app_id, key_id, *values)
             for (app_id, key_id), values in rollup.app_key_total.items()],
        )

        _executemany(conn, USAGE_SESSION_INSERT, rollup.sessions)
        _executemany(conn, AGG_APP_DAY_UPSERT, _rows(rollup.app_day))
        _executemany(conn, AGG_APP_MONTH_UPSERT, _rows(rollup.app_month))
        _executemany(conn, AGG_APP_YEAR_UPSERT, _rows(rollup.app_year))
        _executemany(
            conn,
            AGG_APP_TOTAL_UPSERT,
            [(app_id, *values) for app_id, values in rollup.app_total.items()],
        )
        _executemany(
            conn,
            AGG_APP_HOUR_UPSERT,
            [(day, hour, app_id, duration)
             for (day, hour, app_id), duration in rollup.app_hour.items()],
        )

        if self._registry is not None and rollup.touched_apps:
            AppRegistry.touch(conn, rollup.touched_apps, now)

        if dropped or write_errors:
            conn.execute(HEALTH_STAT_UPSERT, (day_bucket_of(now), dropped, write_errors))

        self._upsert_capability(conn, now)
        if not rollup.empty:
            # data_version 让前端能"值没变就跳过重绘"（05 文档 §1.4），取代固定 1 秒
            # 轮询全量重绘。每批 +1 足够做变更检测。
            conn.execute(
                "INSERT INTO meta (key, value) VALUES ('data_version', '1') "
                "ON CONFLICT(key) DO UPDATE SET "
                "value = CAST(CAST(meta.value AS INTEGER) + 1 AS TEXT)"
            )

    def _upsert_capability(self, conn: Connection, now: datetime) -> None:
        if self._capability_provider is None:
            return
        try:
            snapshot = self._capability_provider()
        except Exception:  # pragma: no cover
            logger.debug("读取能力快照失败", exc_info=True)
            return
        capability_table.upsert(conn, day_bucket=day_bucket_of(now), now=now, **snapshot)

    # ── 内存 rollup ─────────────────────────────────────────────────────
    def _build_rollup(self, batch: list[Event]) -> _Rollup:
        rollup = _Rollup()
        tz = self._tz
        for event in batch:
            if isinstance(event, KeyEvent):
                self._fold_key_event(rollup, event, tz)
            elif isinstance(event, UsageSession):
                self._fold_session(rollup, event, tz)
        return rollup

    def _fold_key_event(self, rollup: _Rollup, event: KeyEvent, tz: tzinfo | None) -> None:
        moment = datetime.fromtimestamp(event.down_ts_ns / 1_000_000_000, tz=tz)
        day = moment.strftime("%Y-%m-%d")
        month = day[:7]
        year = day[:4]
        hour = moment.hour
        duration = event.duration_ms
        key_id = event.key_id
        app_id = event.app_id

        rollup.key_count += 1
        if self._store_raw:
            rollup.raw_by_month.setdefault(month, []).append(
                (
                    key_id,
                    app_id,
                    event.down_ts_ns,
                    event.up_ts_ns,
                    duration,
                    event.native_code,
                    event.native_code2,
                    event.hid_usage,
                    event.confidence_code,
                )
            )
        _accumulate(rollup.key_day, (day, key_id), 1, duration, duration)
        _accumulate(rollup.key_month, (month, key_id), 1, duration, duration)
        _accumulate(rollup.key_year, (year, key_id), 1, duration, duration)
        _accumulate(rollup.key_total, key_id, 1, duration, duration)
        _accumulate_pair(rollup.key_hour, (day, hour, key_id), 1, duration)
        # ★ 应用 × 键：合并的核心产出。哨兵 app_id = 0 也要写——键盘总量必须守恒。
        _accumulate(rollup.key_app_day, (day, app_id, key_id), 1, duration, duration)
        _accumulate(rollup.app_key_total, (app_id, key_id), 1, duration, duration)
        if app_id != UNKNOWN_APP_ID:
            rollup.touched_apps.add(app_id)

    def _fold_session(self, rollup: _Rollup, session: UsageSession, tz: tzinfo | None) -> None:
        if not session.valid:
            return
        slices = split_by_hour(session.start_ts_ns, session.end_ts_ns, tz)
        if not slices:
            return
        start_day = slices[0][0]
        app_id = session.app_id

        rollup.session_count += 1
        rollup.sessions.append(
            (
                app_id,
                session.window_title,
                session.start_ts_ns,
                session.end_ts_ns,
                session.duration_ms,
                start_day,
                int(session.idle_trimmed),
            )
        )

        per_day: dict[str, int] = {}
        for day, hour, duration_ms in slices:
            key = (day, hour, app_id)
            rollup.app_hour[key] = rollup.app_hour.get(key, 0) + duration_ms
            per_day[day] = per_day.get(day, 0) + duration_ms

        total_ms = sum(per_day.values())
        for day, duration_ms in per_day.items():
            # session_count 只在**起始**桶 +1：跨日会话的时长要分摊到两天，但它仍然只是
            # 一段会话，两边都 +1 会让"平均会话时长"这类指标失真。
            is_start = day == start_day
            _accumulate_pair(rollup.app_day, (day, app_id), duration_ms, 0)
            rollup.app_day[(day, app_id)][1] += 1 if is_start else 0
            _accumulate_pair(rollup.app_month, (day[:7], app_id), duration_ms, 0)
            rollup.app_month[(day[:7], app_id)][1] += 1 if is_start else 0
            _accumulate_pair(rollup.app_year, (day[:4], app_id), duration_ms, 0)
            rollup.app_year[(day[:4], app_id)][1] += 1 if is_start else 0

        slot = rollup.app_total.get(app_id)
        if slot is None:
            rollup.app_total[app_id] = [total_ms, 1, session.end_ts_ns]
        else:
            slot[0] += total_ms
            slot[1] += 1
            slot[2] = max(slot[2], session.end_ts_ns)
        if app_id != UNKNOWN_APP_ID:
            rollup.touched_apps.add(app_id)


def day_bucket_of(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%d")


def _rows(mapping: dict) -> list[tuple]:
    """``{(a, b): [x, y]}`` → ``[(a, b, x, y)]``，供 ``executemany`` 直接吃。"""
    return [(*key, *values) for key, values in mapping.items()]


def _executemany(conn: Connection, sql: str, rows: list[tuple]) -> None:
    if rows:
        conn.executemany(sql, rows)


__all__ = [
    "BATCH_MAX_SIZE",
    "BATCH_MAX_WAIT_SECONDS",
    "StorageWriter",
    "WriterStats",
    "day_bucket",
    "day_bucket_of",
    "hour_of",
    "split_by_hour",
]
