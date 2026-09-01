"""端到端纵切：按键 → 归因 → 队列 → 写线程 → 聚合表 → 仓储查询。

这是 12 文档 §1.1 那条纵切的自动化版本，验证 §1.2 的三个假设中可自动验证的两条
（第一个假设"Raw Input 收全按键"只能真人实测，见 PROGRESS 的待人工验收）。

替身只有两个：键盘后端与前台探测。**从 ``KeyboardCapture`` 往后全部是生产代码**，
包括真实的 SQLite 文件、真实的写线程、真实的聚合 upsert。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from fakes import FakeClock, FakeForegroundSource, FakeIdleSource, FakeKeyboardSource
from omnisight.adapters.ports import AppIdentity
from omnisight.capture.coordinator import CaptureCoordinator
from omnisight.capture.foreground import ForegroundMonitor
from omnisight.capture.keyboard import KeyboardCapture
from omnisight.capture.queue import EventQueue
from omnisight.storage.repositories.apps import AppRegistry
from omnisight.storage.repositories.keys import KeyRepository
from omnisight.storage.repositories.usage import UsageRepository
from omnisight.storage.writer import StorageWriter

TZ = ZoneInfo("Asia/Shanghai")
START = datetime(2026, 8, 31, 9, 0, tzinfo=UTC)
POLL_SECONDS = 1.0


class Pipeline:
    """把 lifecycle 的装配在测试里重演一遍，但用可控的钟与假后端。"""

    def __init__(self, database, *, paused: bool = False, excluded=frozenset()) -> None:
        self.clock = FakeClock(START)
        self.queue = EventQueue()
        self.coordinator = CaptureCoordinator(
            boundary_window_seconds=POLL_SECONDS, monotonic=self.clock.monotonic
        )
        self.registry = AppRegistry(database, "windows")
        self.writer = StorageWriter(
            database,
            self.queue,
            tz=TZ,
            registry=self.registry,
            clock=self.clock,
            checkpoint_interval_seconds=0,
        )
        self.foreground_source = FakeForegroundSource()
        self.idle_source = FakeIdleSource()
        self.monitor = ForegroundMonitor(
            self.foreground_source,
            self.coordinator,
            self.queue,
            self._resolve,
            idle_source=self.idle_source,
            poll_seconds=POLL_SECONDS,
            idle_threshold_seconds=1800.0,
            session_flush_seconds=10.0,
            excluded=excluded,
            clock=self.clock,
            paused=paused,
        )
        self.keyboard_source = FakeKeyboardSource(self.clock)
        self.keyboard = KeyboardCapture(
            self.keyboard_source, self.coordinator, self.queue,
            realtime_stream=False, paused=paused,
        )
        self.keyboard.start()
        self.database = database

    def _resolve(self, identity: AppIdentity) -> int:
        return self.registry.resolve(identity, now=self.clock.now())

    # ── 驱动 ────────────────────────────────────────────────────────────
    def focus(self, app_key: str) -> int:
        """切到某个应用并让轮询发现它——脚本化测试里"等轮询追上"是显式的一步。"""
        self.foreground_source.switch_to(app_key)
        self.clock.advance(seconds=POLL_SECONDS)
        self.monitor.tick()
        return self.registry.resolve(
            AppIdentity(app_key=app_key, identity_kind="process",
                        display_name=app_key, process_name=app_key)
        )

    def type_continuously(self, key_id: str, *, seconds: float,
                          interval_ms: float = 40.0) -> int:
        """连续输入。返回按键次数。

        期间**不驱动 tick()**：真实世界里轮询线程与输入是并行的，而一次 tick 恰好落在
        哪两次按键之间对断言不该有影响。
        """
        count = int(seconds * 1000 / interval_ms)
        for _ in range(count):
            self.keyboard_source.tap(key_id, hold_ms=min(interval_ms / 2, 90))
            self.clock.advance(ms=interval_ms / 2)
        return count

    def flush(self) -> None:
        while self.queue.depth:
            self.writer.flush_once()

    def stop(self) -> None:
        self.keyboard.stop()
        self.monitor.stop()
        self.flush()


def test_a_single_keypress_becomes_a_queryable_attributed_fact(database):
    """12 文档 §1.1 的纵切，一条用例：按一次 A 键，查得到"Code.exe 按了 1 次 A"。"""
    pipeline = Pipeline(database)
    app_id = pipeline.focus("code.exe")
    pipeline.clock.advance(seconds=2)  # 越过边界窗口
    pipeline.keyboard_source.tap("key_a", hold_ms=95)
    pipeline.stop()

    heatmap = KeyRepository(database).app_heatmap(app_id)
    assert heatmap["key_a"]["press_count"] == 1
    assert heatmap["key_a"]["duration_total_ms"] == 95

    apps = KeyRepository(database).apps_for_key("key_a")
    assert [(row["app_id"], row["press_count"]) for row in apps] == [(app_id, 1)]

    names = pipeline.registry.display_names()
    assert names[app_id] == "code.exe"


#: 每个应用只敲一个专属键，于是 ``(app_id, key_id)`` 这一对就是**逐事件**的归因真值，
#: 不需要另存一份时间线去比对。
KEY_BY_APP = {"code.exe": "key_c", "chrome.exe": "key_h", "term.exe": "key_t"}


def test_attribution_accuracy_across_app_switches(database):
    """M1 判据：``confidence='high'`` 的事件归因正确率 100%，``boundary`` 占比 < 2%。

    ``boundary`` 的占比不是代码属性，而是**使用节奏**的函数：连续输入时它约等于
    ``轮询间隔 ÷ 切换间隔``。这里模拟每分钟切一次应用、25 键/秒连续输入，上界是
    1 / 60 ≈ 1.7%。判据里的 2% 因此隐含了"用户不会每几秒就切一次应用"这个假设——
    把它写在这里，好过让日后某次失败显得莫名其妙。切换频繁的用户对应 12 文档的 R3，
    那里已登记了用事件钩子替代轮询的二期方案。
    """
    pipeline = Pipeline(database)
    app_ids: dict[int, str] = {}
    for visit in range(9):
        app_key = list(KEY_BY_APP)[visit % 3]
        app_id = pipeline.focus(app_key)
        app_ids[app_id] = app_key
        # 连续输入一分钟，不做任何"等窗口过去"的取巧。
        pipeline.type_continuously(KEY_BY_APP[app_key], seconds=60, interval_ms=40)
    pipeline.stop()

    conn = database.connect()
    rows = list(
        conn.execute(
            "SELECT app_id, key_id, confidence, COUNT(*) FROM raw_key_events_2026_08"
            " GROUP BY app_id, key_id, confidence"
        )
    )
    total = sum(row[3] for row in rows)
    assert total == 9 * 1500

    # 逐事件正确性：每一对 (app_id, key_id) 都必须是那个应用的专属键——high 与
    # boundary 都不许出现错配。
    for app_id, key_id, _confidence, _count in rows:
        assert app_id in app_ids, f"出现了未知的 app_id {app_id}"
        assert key_id == KEY_BY_APP[app_ids[app_id]], "归因错配"

    by_confidence: dict[int, int] = {}
    for _app_id, _key_id, confidence, count in rows:
        by_confidence[confidence] = by_confidence.get(confidence, 0) + count

    assert by_confidence.get(0, 0) == 0, "脚本全程都有前台应用，不该有 unknown"
    boundary_share = by_confidence.get(1, 0) / total
    assert boundary_share < 0.02, f"boundary 占比 {boundary_share:.2%}"
    assert by_confidence[2] / total > 0.97, "high 占比应 > 97%（04 文档 §4.3）"


def test_keys_typed_before_the_poll_notices_a_switch_go_to_the_previous_app(database):
    """轮询的固有盲区，写成测试是为了让它的**大小**可见，而不是留在文档里当一句话。

    真实切换与轮询发现之间最多有一个轮询间隔。这段时间里的按键会被归给**上一个**
    应用，且因为上一个应用早已"稳定超过一个轮询周期"，它们被标成 ``high``——也就是说
    ``boundary`` 标的是切换**之后**（归因其实正确）的那一段，而真正有风险的是切换
    **之前**的那一段。

    误差上界是"切换次数 × 一个轮询间隔内的按键数"，与 04 文档 §4.3 给出的"最多 1s
    内的按键可能归错"一致；判据要求的 100% 正确率成立于脚本化场景（切换后等轮询追上
    再输入），而不是这个盲区场景。已记入 PROGRESS 的已知限制并挂到 R3。
    """
    pipeline = Pipeline(database)
    code_id = pipeline.focus("code.exe")
    pipeline.type_continuously("key_c", seconds=5, interval_ms=100)

    # 用户切到了 chrome，但轮询还没跑：这半秒的按键会被记到 code.exe 名下。
    pipeline.foreground_source.switch_to("chrome.exe")
    pipeline.type_continuously("key_h", seconds=0.5, interval_ms=100)
    chrome_id = pipeline.focus("chrome.exe")
    pipeline.type_continuously("key_h", seconds=5, interval_ms=100)
    pipeline.stop()

    conn = database.connect()
    misattributed = conn.execute(
        "SELECT COUNT(*) FROM raw_key_events_2026_08 WHERE key_id = 'key_h' AND app_id = ?",
        (code_id,),
    ).fetchone()[0]
    assert misattributed == 5, "盲区应正好覆盖切换后、轮询前的那几次按键"
    assert misattributed <= 0.5 / POLL_SECONDS * 10 + 10  # 上界：一个轮询间隔的按键量

    # 而且它们被标成了 high——这正是需要写进已知限制的那件事。
    confidences = {
        row[0]
        for row in conn.execute(
            "SELECT confidence FROM raw_key_events_2026_08"
            " WHERE key_id = 'key_h' AND app_id = ?",
            (code_id,),
        )
    }
    assert confidences == {2}
    assert conn.execute(
        "SELECT COUNT(*) FROM raw_key_events_2026_08 WHERE key_id = 'key_h' AND app_id = ?",
        (chrome_id,),
    ).fetchone()[0] == 50


def test_writer_keeps_up_with_a_burst_far_faster_than_human_typing(database):
    """M1 判据（压力测试）：零丢弃，队列深度稳定不增长。

    判据原文是"20 键/秒持续 10 分钟"。这里换成**同样的事件总量以最快速度灌进去**：
    真实等待 10 分钟会让集成测试从 20 秒变成 10 分钟（11 文档 §1 的预算），而全速灌入
    对队列与写线程是更严苛的条件——20 键/秒对单写线程本来就是极小的负载，真正要证明
    的是"突发不丢"。10 分钟真实运行留作人工验收项。
    """
    pipeline = Pipeline(database)
    app_id = pipeline.focus("code.exe")
    pipeline.writer.start()

    depths: list[int] = []
    total = 20 * 60 * 10  # 20 键/秒 × 10 分钟
    for index in range(total):
        pipeline.keyboard_source.tap("key_e", hold_ms=20)
        pipeline.clock.advance(ms=30)
        if index % 500 == 0:
            depths.append(pipeline.queue.depth)

    pipeline.writer.stop(timeout=20.0)
    pipeline.keyboard.stop()
    pipeline.monitor.stop()

    conn = database.connect()
    assert pipeline.queue.dropped == 0, "零丢弃是判据"
    assert conn.execute(
        "SELECT SUM(press_count) FROM agg_key_total"
    ).fetchone()[0] == total
    assert conn.execute(
        "SELECT COUNT(*) FROM raw_key_events_2026_08"
    ).fetchone()[0] == total
    assert KeyRepository(database).app_heatmap(app_id)["key_e"]["press_count"] == total
    # 深度可以起伏（写线程是批量的），但不许单调上升到接近上限。
    assert max(depths) < 50_000, f"队列深度峰值 {max(depths)}"


def test_paused_capture_writes_nothing_at_all(database):
    """暂停开关必须是真的：按键之后库里零行（11 文档 §4.5）。"""
    pipeline = Pipeline(database, paused=True)
    pipeline.foreground_source.switch_to("code.exe")
    for _ in range(20):
        pipeline.monitor.tick()
        pipeline.clock.advance(seconds=1)
    pipeline.keyboard_source.tap("key_a")
    pipeline.stop()

    conn = database.connect()
    for table in ("agg_key_total", "agg_key_day", "usage_session", "agg_app_day"):
        assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    assert UsageRepository(database).data_range() == (None, None)


def test_idle_period_is_excluded_from_screen_time_end_to_end(database):
    """挂机 35 分钟回来：空闲期不计入时长，恢复输入后开新会话（M1 判据）。"""
    pipeline = Pipeline(database)
    app_id = pipeline.focus("code.exe")
    for _ in range(10):
        pipeline.clock.advance(seconds=1)
        pipeline.monitor.tick()

    # 走开 35 分钟（阈值 30 分钟）。
    pipeline.clock.advance(seconds=35 * 60)
    pipeline.idle_source.idle = 35 * 60
    pipeline.monitor.tick()

    # 回来继续用 20 秒。
    pipeline.idle_source.idle = 0.0
    pipeline.clock.advance(seconds=1)
    pipeline.monitor.tick()
    for _ in range(20):
        pipeline.clock.advance(seconds=1)
        pipeline.monitor.tick()
    pipeline.stop()

    conn = database.connect()
    total_ms = conn.execute("SELECT SUM(duration_ms) FROM agg_app_total").fetchone()[0]
    # 会话总量 = 空闲前的活跃时段（含被截断回的 30 分钟阈值内部分）+ 回来后的 20 秒。
    # 关键断言是"远小于 35 分钟 + 30 秒"，即挂机时间没有被整段计入。
    assert total_ms < 32 * 60 * 1000
    assert conn.execute(
        "SELECT COUNT(*) FROM usage_session WHERE idle_trimmed = 1"
    ).fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM usage_session").fetchone()[0] >= 2
    assert UsageRepository(database).day_ranking("2026-08-31")[0]["app_id"] == app_id


def test_excluded_app_contributes_keys_to_the_sentinel_and_no_session(database):
    """键盘总量守恒：被排除应用的按键归 app_id = 0，而不是消失。"""
    pipeline = Pipeline(database, excluded=frozenset({"secret.exe"}))
    pipeline.foreground_source.switch_to("secret.exe")
    pipeline.clock.advance(seconds=1)
    pipeline.monitor.tick()
    for _ in range(30):
        pipeline.keyboard_source.tap("key_p", hold_ms=40)
        pipeline.clock.advance(ms=60)
    pipeline.clock.advance(seconds=10)
    pipeline.monitor.tick()
    pipeline.stop()

    conn = database.connect()
    assert conn.execute("SELECT COUNT(*) FROM usage_session").fetchone()[0] == 0
    assert KeyRepository(database).press_total() == 30
    assert conn.execute(
        "SELECT press_count FROM agg_app_key_total WHERE app_id = 0 AND key_id = 'key_p'"
    ).fetchone()[0] == 30
    # 被排除的应用连维表都不该进——否则应用列表里会出现用户明确不想看到的名字。
    assert conn.execute(
        "SELECT COUNT(*) FROM app WHERE app_key = 'secret.exe'"
    ).fetchone()[0] == 0


def test_shutdown_order_keeps_the_last_session_and_the_last_keys(database):
    """先停键盘 → 再停前台（它会产出最后一条会话）→ 最后 drain 写线程。

    反过来做会丢掉最后一段会话，而"刚退出前那一会儿"恰是用户最容易注意到的部分。
    """
    pipeline = Pipeline(database)
    app_id = pipeline.focus("code.exe")
    pipeline.writer.start()
    for _ in range(5):
        pipeline.clock.advance(seconds=1)
        pipeline.monitor.tick()
    pipeline.keyboard_source.tap("key_z", hold_ms=70)

    pipeline.keyboard.stop()
    pipeline.monitor.stop()
    pipeline.writer.stop(timeout=10.0)

    conn = database.connect()
    assert conn.execute("SELECT COUNT(*) FROM usage_session").fetchone()[0] == 1
    assert conn.execute(
        "SELECT press_count FROM agg_key_app_day WHERE app_id = ? AND key_id = 'key_z'",
        (app_id,),
    ).fetchone()[0] == 1
    assert pipeline.queue.depth == 0


def test_wall_clock_time_is_used_for_bucketing_and_monotonic_for_durations(database):
    """两个钟各管一头：改系统时间不许改变已测出的时长，但日期桶只能靠墙钟。"""
    pipeline = Pipeline(database)
    pipeline.focus("code.exe")
    pipeline.clock.advance(seconds=2)

    pipeline.keyboard_source.emit("key_a", pressed=True)
    pipeline.clock.advance_monotonic(ms=150)
    pipeline.clock.set_wall_clock(forward_by=timedelta(days=1))
    pipeline.keyboard_source.emit("key_a", pressed=False)
    pipeline.stop()

    row = database.connect().execute(
        "SELECT bucket, duration_total_ms FROM agg_key_day WHERE key_id = 'key_a'"
    ).fetchone()
    # 分桶用**按下**时刻的墙钟：按下发生在改时间之前。
    assert row["bucket"] == "2026-08-31"
    assert row["duration_total_ms"] == 150


def test_a_days_data_can_be_explained_by_its_capability_row(database):
    """03 文档 §2.8 的意义：任何一天的数据都要能回答"这是在什么条件下采到的"。"""
    pipeline = Pipeline(database)
    pipeline.writer.set_capability_provider(
        lambda: {
            "platform_id": "windows",
            "keyboard_backend": "fake",
            "foreground_available": True,
            "titles_recorded": False,
            "key_position_stable": True,
        }
    )
    pipeline.focus("code.exe")
    pipeline.clock.advance(seconds=2)
    pipeline.keyboard_source.tap("key_a")
    pipeline.stop()

    conn = database.connect()
    days = {row[0] for row in conn.execute("SELECT DISTINCT bucket FROM agg_key_day")}
    recorded = {row[0] for row in conn.execute("SELECT day_bucket FROM capture_capability")}
    assert days <= recorded, f"这些天没有能力快照：{days - recorded}"


def test_capture_never_touches_sqlite_on_the_key_hot_path(database):
    """热路径上一次事务就可能阻塞几十毫秒，重则丢事件、轻则让整机输入卡顿。

    这里用 sqlite3 自己的 trace 回调数一数按键期间执行了几条 SQL 来固定这条约束——它比一句注释
    更难腐化。前台轮询（1 秒一次的冷路径）允许写库，因此断言只覆盖按键区间。
    """
    pipeline = Pipeline(database)
    pipeline.focus("code.exe")
    pipeline.clock.advance(seconds=2)

    executed: list[str] = []
    connection = database.connect()
    connection.set_trace_callback(executed.append)
    try:
        for _ in range(200):
            pipeline.keyboard_source.tap("key_a", hold_ms=20)
            pipeline.clock.advance(ms=30)
    finally:
        connection.set_trace_callback(None)

    assert executed == [], f"按键热路径执行了 SQL：{executed[:3]}"
    assert pipeline.queue.depth == 200
    pipeline.stop()
