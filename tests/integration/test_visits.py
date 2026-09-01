"""访问 vs 会话段：schema v2 的核心语义（m002 迁移的头号理由）。

**心跳落盘每 10 秒把一次使用切成一段**（04 文档 §2.3）。04 文档原文说"代价是一天会产生
较多短会话行——查询侧不受影响"，这句话不成立：

* ``session_count`` 数的是**段数**而不是"用了几次"——在一个应用里连续工作 3 小时会被
  报成 1080 次使用；
* ``MAX(usage_session.duration_ms)`` 恒等于心跳间隔，于是"最长一次使用"永远是 10 秒；
* ``/insights/rhythm`` 的 ``switch_count``（注意力碎片化）差两个数量级。

修法是 ``end_reason`` + ``visit_start_ts_ns``：一次访问在库里就是 ``end_reason <>
'heartbeat'`` 的那一行，它自带完整跨度。这个文件盯住"心跳切段之后各个数字仍然对"。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from omnisight.adapters.ports import AppIdentity
from omnisight.capture.models import UsageSession
from omnisight.capture.queue import EventQueue
from omnisight.storage.repositories.apps import AppRegistry
from omnisight.storage.repositories.usage import UsageRepository
from omnisight.storage.writer import StorageWriter

TZ = ZoneInfo("Asia/Shanghai")
START = datetime(2026, 9, 2, 10, 0, tzinfo=TZ)
HEARTBEAT = 10  # 秒；与 ``capture.session_flush_seconds`` 的默认值一致


def _ns(moment: datetime) -> int:
    return int(moment.timestamp() * 1_000_000_000)


def _visit(app_id: int, start: datetime, seconds: int, *, heartbeat: int = 0) -> list[UsageSession]:
    """一次访问 → 若干会话段。``heartbeat=0`` 表示一段到底（访问短于心跳间隔）。"""
    start_ns = _ns(start)
    end_ns = start_ns + seconds * 1_000_000_000
    edges = [start_ns]
    if heartbeat:
        step = heartbeat * 1_000_000_000
        edges.extend(range(start_ns + step, end_ns, step))
    edges.append(end_ns)
    segments = []
    for index in range(len(edges) - 1):
        low, high = edges[index], edges[index + 1]
        segments.append(
            UsageSession(
                app_id=app_id,
                start_ts_ns=low,
                end_ts_ns=high,
                duration_ms=(high - low) // 1_000_000,
                end_reason="heartbeat" if index < len(edges) - 2 else "switch",
                visit_start_ts_ns=start_ns,
            )
        )
    return segments


@pytest.fixture
def writer(database):
    queue = EventQueue()
    registry = AppRegistry(database, "windows")
    storage = StorageWriter(
        database, queue, tz=TZ, registry=registry,
        batch_max_wait_seconds=0.0, checkpoint_interval_seconds=0.0,
    )
    app_id = registry.resolve(
        AppIdentity(
            app_key="code.exe", identity_kind="process",
            display_name="Code", process_name="code.exe",
        )
    )

    def run(sessions):
        for session in sessions:
            queue.put(session)
        while queue.depth:
            storage.flush_once()

    return run, app_id, UsageRepository(database)


def test_a_heartbeat_split_visit_is_counted_once(writer):
    """30 分钟的访问被切成 180 段，``session_count`` 仍然是 1。"""
    run, app_id, repo = writer
    segments = _visit(app_id, START, 1800, heartbeat=HEARTBEAT)
    assert len(segments) == 180
    run(segments)

    rows = repo.app_durations("2026-09-02", "2026-09-02")
    assert len(rows) == 1
    assert rows[0]["session_count"] == 1
    assert rows[0]["duration_ms"] == 1_800_000


def test_the_longest_visit_is_the_whole_visit_not_the_heartbeat_interval(writer):
    """``MAX(duration_ms)`` 会给出 10 秒。``longest_visit_ms`` 必须给出 1800 秒。"""
    run, app_id, repo = writer
    run(_visit(app_id, START, 1800, heartbeat=HEARTBEAT))
    assert repo.app_durations("2026-09-02", "2026-09-02")[0]["longest_visit_ms"] == 1_800_000


def test_only_the_visit_row_is_returned_as_a_session(writer):
    """一次访问 = 一行（``end_reason <> 'heartbeat'``），它自带完整跨度。"""
    run, app_id, repo = writer
    run(_visit(app_id, START, 1800, heartbeat=HEARTBEAT))
    visits = repo.sessions("2026-09-02", "2026-09-02", visits_only=True)
    assert len(visits) == 1
    # 两个字段刻意都在：``duration_ms`` 是这一**段**（10 秒），``visit_duration_ms`` 是整次
    # **访问**（1800 秒）。接口给用户的是后者，前者留给排障。
    assert visits[0]["duration_ms"] == 10_000
    assert visits[0]["visit_duration_ms"] == 1_800_000
    assert repo.session_total("2026-09-02", "2026-09-02", visits_only=True) == 1
    # 段粒度仍然查得到——排查采集问题时需要它。
    assert repo.session_total("2026-09-02", "2026-09-02", visits_only=False) == 180


def test_switch_count_counts_visits_not_segments(writer):
    """注意力碎片化：三次访问就是三次，不是 540 次。"""
    run, app_id, repo = writer
    for offset in (0, 40, 80):
        run(_visit(app_id, START + timedelta(minutes=offset), 600, heartbeat=HEARTBEAT))
    assert repo.switch_count("2026-09-02", "2026-09-02") == 3


def test_a_visit_shorter_than_one_heartbeat_is_still_one_visit(writer):
    """访问短于心跳间隔时只有一段，且它既开启访问又结束访问。"""
    run, app_id, repo = writer
    segments = _visit(app_id, START, 5)
    assert len(segments) == 1
    assert segments[0].starts_visit is True
    run(segments)
    assert repo.app_durations("2026-09-02", "2026-09-02")[0]["session_count"] == 1


def test_duration_is_conserved_regardless_of_how_it_was_split(writer, database):
    """切法不影响总时长。这条保证"改心跳间隔"不会改变历史统计的口径。"""
    run, app_id, repo = writer
    run(_visit(app_id, START, 900, heartbeat=HEARTBEAT))
    run(_visit(app_id, START + timedelta(hours=2), 900))
    total = repo.day_total_ms("2026-09-02")
    assert total == 1_800_000
    hourly = sum(row["duration_ms"] for row in repo.hourly("2026-09-02"))
    assert hourly == total


def test_a_visit_across_midnight_is_clipped_per_day(writer):
    """跨零点的访问在两边各记自己那一半。

    不裁剪的话第二天会报出一个比当天总时长还长的"最长一次访问"（60 分钟 > 30 分钟），
    而 ``longest_visit_ms <= duration_ms`` 是这一行上唯一能机械检查的不变式。整次访问的
    真实跨度并没有丢——见 :func:`test_the_full_span_of_a_midnight_visit_is_still_available`。
    """
    run, app_id, repo = writer
    run(_visit(app_id, datetime(2026, 9, 2, 23, 30, tzinfo=TZ), 3600, heartbeat=HEARTBEAT))
    first = repo.app_durations("2026-09-02", "2026-09-02")[0]
    second = repo.app_durations("2026-09-03", "2026-09-03")[0]
    assert first["duration_ms"] == 1_800_000
    assert second["duration_ms"] == 1_800_000
    assert first["session_count"] == 1
    assert second["session_count"] == 0, "跨日访问两边都 +1 会让平均会话时长失真"
    assert first["longest_visit_ms"] == 1_800_000
    assert second["longest_visit_ms"] == 1_800_000


def test_the_full_span_of_a_midnight_visit_is_still_available(writer):
    """"专注时段"用的是会话行本身，因此跨零点的一小时仍然是完整的一小时。"""
    run, app_id, repo = writer
    run(_visit(app_id, datetime(2026, 9, 2, 23, 30, tzinfo=TZ), 3600, heartbeat=HEARTBEAT))
    blocks = repo.longest_visits("2026-09-02", "2026-09-03", limit=5)
    assert [block["duration_ms"] for block in blocks] == [3_600_000]


def test_longest_visit_never_exceeds_that_days_total(writer):
    """机械不变式：任何一行的"最长一次访问"都不可能超过那一行的总时长。"""
    run, app_id, repo = writer
    run(_visit(app_id, datetime(2026, 9, 2, 22, 0, tzinfo=TZ), 7200, heartbeat=HEARTBEAT))
    run(_visit(app_id, datetime(2026, 9, 3, 9, 0, tzinfo=TZ), 600, heartbeat=HEARTBEAT))
    for day in ("2026-09-02", "2026-09-03"):
        for row in repo.app_durations(day, day):
            assert row["longest_visit_ms"] <= row["duration_ms"], day


def test_visit_semantics_have_a_model_level_definition():
    """口径写在模型上而不是散在查询里——否则"什么算一次访问"会在各处慢慢分叉。"""
    start = _ns(START)
    first = UsageSession(
        app_id=1, start_ts_ns=start, end_ts_ns=start + 10 ** 10,
        duration_ms=10_000, end_reason="heartbeat", visit_start_ts_ns=start,
    )
    later = UsageSession(
        app_id=1, start_ts_ns=start + 10 ** 10, end_ts_ns=start + 2 * 10 ** 10,
        duration_ms=10_000, end_reason="switch", visit_start_ts_ns=start,
    )
    assert first.starts_visit is True
    assert later.starts_visit is False
    assert later.visit_duration_ms == 20_000
