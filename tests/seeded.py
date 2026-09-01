"""契约测试用的**确定性**数据集。

与 ``tools/seed.py`` 分工明确：那个造"三年的量"给基准用，随机；这个造"一小把精确知道
答案的事实"给契约测试用，可以断言具体数字。契约测试断言不了具体数字，就只能断言"字段
存在"，而那种测试在聚合算错时照样全绿（11 文档 §4.1）。

全部数据都经过 ``StorageWriter``——不许手写 ``INSERT INTO agg_*``。聚合表是查询的唯一
来源，用手写数据填它等于把被测对象换成了测试自己的假设。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from omnisight.adapters.ports import AppIdentity
from omnisight.capture.models import KeyEvent, UsageSession
from omnisight.capture.queue import EventQueue
from omnisight.storage import capability as capability_table
from omnisight.storage.database import Database
from omnisight.storage.repositories.apps import AppRegistry
from omnisight.storage.writer import StorageWriter

TZ = ZoneInfo("Asia/Shanghai")
#: 契约测试的"此刻"。周三，因此 ``week`` / ``month`` / ``day`` 三种周期的内容互不相同——
#: 挑周一会让 ``week`` 恰好等于 ``day``，于是"周期解析错了"这类缺陷测不出来。
NOW = datetime(2026, 9, 2, 22, 15, 3, tzinfo=TZ)
TODAY = NOW.date()

#: 播下一个绝不该出现在任何响应里的标题。断言内容比断言"没有 window_title 字段"更强：
#: 字段可以改名，内容不会。
SECRET_TITLE = "季度并购方案-绝密.xlsx — Excel"

#: 只有 ``include_titles=true`` **且** ``privacy.record_window_titles`` 为真时才可能出现。
TITLE_DAY = "2026-09-02"
#: 前台探测不可用的那一天：查它必须 200 + ``coverage.gaps``，不是 4xx，也不是一片 0。
BLIND_DAY = "2026-08-29"


@dataclass(frozen=True, slots=True)
class Expected:
    """一个周期的预期数值。测试直接对着它断言。"""

    seconds: float
    presses: int
    #: 归到未知前台（``app_id = 0``）的按键。它们不进应用排行，但必须计入总数。
    unattributed: int = 0
    apps: tuple[str, ...] = ()


#: 各周期的预期。手算出来写在这里，而不是让测试从库里再查一遍——那样测的是"两次查询
#: 结果一致"，而不是"结果对不对"。
EXPECTED: dict[str, Expected] = {
    "day": Expected(
        seconds=2400, presses=7, unattributed=2,
        apps=("Visual Studio Code", "Google Chrome"),
    ),
    "week": Expected(seconds=4500, presses=15, unattributed=2),
    "month": Expected(seconds=3600, presses=10, unattributed=2),
    "year": Expected(seconds=4500, presses=22, unattributed=9),
    "total": Expected(seconds=6300, presses=27, unattributed=9),
}

APP_KEYS = ("code.exe", "chrome.exe", "explorer.exe")
DISPLAY = {
    "code.exe": "Visual Studio Code",
    "chrome.exe": "Google Chrome",
    "explorer.exe": "文件资源管理器",
}


@dataclass
class Seeded:
    """播种结果：测试需要的 ``app_id`` 与预期值。"""

    app_ids: dict[str, int] = field(default_factory=dict)
    expected: dict[str, Expected] = field(default_factory=lambda: dict(EXPECTED))

    @property
    def code(self) -> int:
        return self.app_ids["code.exe"]

    @property
    def chrome(self) -> int:
        return self.app_ids["chrome.exe"]

    @property
    def explorer(self) -> int:
        return self.app_ids["explorer.exe"]


def _at(day: str, hour: int, minute: int = 0) -> int:
    moment = datetime.combine(date.fromisoformat(day), datetime.min.time(), tzinfo=TZ)
    return int((moment + timedelta(hours=hour, minutes=minute)).timestamp() * 1_000_000_000)


#: ``(day, hour, minute, app, 时长秒, [(key_id, 次数), …], 是否带标题)``。
#: 一行就是一次访问。``app`` 为 ``None`` 表示前台未知（``app_id = 0``）。
PLAN: tuple[tuple[str, int, int, str | None, int, tuple[tuple[str, int], ...], bool], ...] = (
    # 今天：两个应用 + 两次归不到应用的按键。
    ("2026-09-02", 10, 0, "code.exe", 1800,
     (("key_a", 2), ("control_left", 1), ("space", 1)), True),
    ("2026-09-02", 11, 0, "chrome.exe", 600, (("key_b", 1),), False),
    ("2026-09-02", 12, 0, None, 0, (("key_x", 2),), False),
    # 昨天：同一周、同一月。
    ("2026-09-01", 9, 0, "code.exe", 1200, (("key_a", 3),), False),
    # 本周之内但上个月——用来区分 week 与 month。
    ("2026-08-31", 14, 0, "chrome.exe", 900, (("key_c", 5),), False),
    # 前台探测不可用的一天：有键盘数据，没有应用数据。
    (BLIND_DAY, 15, 0, None, 0, (("key_d", 7),), False),
    # 去年：只有 total 才看得到。
    ("2025-12-15", 20, 0, "chrome.exe", 1800, (("key_c", 5),), False),
)


def seed(db: Database, *, store_raw: bool = True) -> Seeded:
    """把 :data:`PLAN` 写进库。返回 :class:`Seeded`。"""
    queue = EventQueue()
    registry = AppRegistry(db, "windows")
    writer = StorageWriter(
        db, queue, tz=TZ, store_raw=store_raw, registry=registry,
        batch_max_wait_seconds=0.0, checkpoint_interval_seconds=0.0,
    )
    result = Seeded()
    for app_key in APP_KEYS:
        result.app_ids[app_key] = registry.resolve(
            AppIdentity(
                app_key=app_key, identity_kind="process", display_name=DISPLAY[app_key],
                process_name=app_key, exe_path=rf"C:\Apps\{app_key}",
            )
        )

    days = {row[0] for row in PLAN}
    for day in sorted(days):
        with db.transaction() as conn:
            capability_table.upsert(
                conn,
                day_bucket=day,
                platform_id="windows",
                keyboard_backend="raw_input",
                foreground_available=day != BLIND_DAY,
                titles_recorded=day == TITLE_DAY,
                key_position_stable=True,
                now=datetime.combine(date.fromisoformat(day), datetime.min.time(), tzinfo=TZ),
            )

    for day, hour, minute, app_key, seconds, keys, titled in PLAN:
        app_id = result.app_ids[app_key] if app_key else 0
        start = _at(day, hour, minute)
        offset = 0
        for key_id, count in keys:
            for _ in range(count):
                down = start + offset * 1_000_000_000
                offset += 1
                queue.put(
                    KeyEvent(
                        key_id=key_id, down_ts_ns=down, up_ts_ns=down + 80_000_000,
                        duration_ms=80.0, app_id=app_id, confidence="high",
                    )
                )
        if seconds:
            queue.put(
                UsageSession(
                    app_id=app_id,
                    start_ts_ns=start,
                    end_ts_ns=start + seconds * 1_000_000_000,
                    duration_ms=seconds * 1000,
                    window_title=SECRET_TITLE if titled else "",
                    end_reason="switch",
                    visit_start_ts_ns=start,
                )
            )
    while queue.depth:
        writer.flush_once()
    return result


__all__ = [
    "BLIND_DAY",
    "EXPECTED",
    "NOW",
    "PLAN",
    "SECRET_TITLE",
    "TITLE_DAY",
    "TODAY",
    "TZ",
    "Expected",
    "Seeded",
    "seed",
]
