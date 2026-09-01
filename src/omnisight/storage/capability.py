"""``capture_capability`` 的写入（03 文档 §2.8）。

这张表回答的是"**这天的数据是在什么条件下采到的**"。它与 ``health_stat``
（采集有没有出错）是两件事，缺一不可：前者解释"为什么没有应用维度"，
后者解释"为什么那天数据偏少"。

首期 Windows 上各能力位几乎恒定，看起来是白写；但同一个数据库跨环境使用
（便携目录拷到另一台机器、Raw Input 失败那几天退到兜底后端）在首期就会发生，
届时没有这张表，图表形态的突变将无从解释。
"""

from __future__ import annotations

from datetime import datetime
from sqlite3 import Connection

UPSERT = """
INSERT INTO capture_capability (
    day_bucket, platform_id, keyboard_backend,
    foreground_available, titles_recorded, key_position_stable,
    first_seen_at, last_seen_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(day_bucket, platform_id, keyboard_backend,
            foreground_available, key_position_stable)
DO UPDATE SET
    last_seen_at    = excluded.last_seen_at,
    titles_recorded = MAX(capture_capability.titles_recorded, excluded.titles_recorded)
"""


def upsert(
    conn: Connection,
    *,
    day_bucket: str,
    platform_id: str,
    keyboard_backend: str,
    foreground_available: bool,
    titles_recorded: bool,
    key_position_stable: bool,
    now: datetime,
) -> None:
    """记录（或刷新）当天这一组能力位。

    ``titles_recorded`` 取历史最大值而非覆盖：用户当天中途打开过标题记录，这一天
    的数据里就确实含标题，之后再关掉也不能把这个事实抹掉。其余能力位在主键里，
    因此切换后端会新增一行，如实反映"上午一种、下午另一种"。
    """
    conn.execute(
        UPSERT,
        (
            day_bucket,
            platform_id,
            keyboard_backend,
            int(foreground_available),
            int(titles_recorded),
            int(key_position_stable),
            now.isoformat(timespec="seconds"),
            now.isoformat(timespec="seconds"),
        ),
    )


def day_bucket(moment: datetime) -> str:
    """本地日期桶。写入时算好，查询期绝不用 ``strftime``（03 文档 §2.3）。"""
    return moment.strftime("%Y-%m-%d")
