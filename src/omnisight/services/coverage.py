"""``coverage``：这个周期里**有多少天具备哪种采集能力**（05 文档 §1.4）。

它是"0"与"测不到"的判别依据，两者在 UI 上必须长得不一样——把"测不到"画成"没有"是
最容易让用户误判自己行为的一类错误（03 文档 §2.8）。

数据来自 ``capture_capability``：写入线程每批 upsert 当天一行，主键含各能力位，所以
同一天内换过后端会留下多行（"上午 Raw Input、下午 pynput"）。

**三条判定规则，每条都有反例支撑：**

1. **只有明确的否定证据才产生 ``gaps``。** 某天完全没有 ``capture_capability`` 行，
   意味着那天程序没运行——我们对那天一无所知，不能宣称"该环境不支持应用归因"。
   这类天不计入 ``foreground_days``，前端从 ``total_days - foreground_days`` 就能看出
   差额，不需要我们编一条 gap。
2. **``titles`` 不产生 gap。** 窗口标题默认关闭（08 文档 §2.1），是隐私选择而不是能力
   缺失。为它每天报一条 gap 会让 ``gaps`` 永远非空，从而彻底失去信噪比——而 05 文档
   §7 明确要求"``degraded`` 为空是一切正常的唯一标志"，``gaps`` 同理。
3. **相邻同因的天合并成一段。** 用户看到的应该是"8月28日–8月30日 无应用归因"，而不是
   三条一模一样的记录。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from sqlite3 import Connection

#: 缺失能力 → (前端文案, 原因取自哪一列)。取值与 ``capture_capability`` 的能力位
#: 一一对应（05 文档 §1.4）。
_MESSAGES: dict[str, str] = {
    "foreground": "该环境不支持应用归因，键盘统计仍然正常",
    "key_position": "该时段左右修饰键与小键盘无法区分",
    "keyboard": "该时段没有可用的键盘采集后端",
}

_SELECT = """
SELECT day_bucket, platform_id, keyboard_backend,
       MAX(foreground_available) AS foreground_available,
       MAX(key_position_stable)  AS key_position_stable,
       MAX(titles_recorded)      AS titles_recorded
FROM capture_capability
WHERE day_bucket BETWEEN ? AND ?
GROUP BY day_bucket, platform_id, keyboard_backend
ORDER BY day_bucket
"""


@dataclass(frozen=True, slots=True)
class DayCapability:
    day: str
    platform_id: str
    keyboard_backend: str
    foreground: bool
    key_position_stable: bool
    titles_recorded: bool


def load(conn: Connection, start_day: str, end_day: str) -> list[DayCapability]:
    rows = conn.execute(_SELECT, (start_day, end_day)).fetchall()
    return [
        DayCapability(
            day=row["day_bucket"],
            platform_id=row["platform_id"],
            keyboard_backend=row["keyboard_backend"],
            foreground=bool(row["foreground_available"]),
            key_position_stable=bool(row["key_position_stable"]),
            titles_recorded=bool(row["titles_recorded"]),
        )
        for row in rows
    ]


def _merge_runs(items: list[tuple[str, str, str]]) -> list[dict[str, str]]:
    """``[(day, missing, reason)]`` → 合并相邻同因的段。"""
    gaps: list[dict[str, str]] = []
    for day, missing, reason in sorted(items):
        previous = gaps[-1] if gaps else None
        if (
            previous is not None
            and previous["missing"] == missing
            and previous["reason"] == reason
            and date.fromisoformat(previous["to"]) + timedelta(days=1) == date.fromisoformat(day)
        ):
            previous["to"] = day
            continue
        gaps.append(
            {
                "from": day,
                "to": day,
                "missing": missing,
                "reason": reason,
                "message": _MESSAGES.get(missing, "该时段的采集能力与当前不同"),
            }
        )
    return gaps


def summarize(
    conn: Connection, start_day: str, end_day: str, total_days: int
) -> dict[str, object]:
    """周期的 ``coverage`` 段。空库返回全 0 与空 ``gaps``，不报错。"""
    rows = load(conn, start_day, end_day)
    foreground_days: set[str] = set()
    keyboard_days: set[str] = set()
    stable_days: set[str] = set()
    title_days: set[str] = set()
    seen_days: set[str] = set()
    negatives: list[tuple[str, str, str]] = []

    for row in rows:
        seen_days.add(row.day)
        if row.foreground:
            foreground_days.add(row.day)
        else:
            # 原因用平台 id：Wayland 会话拿不到活动窗口，而这正是用户要看到的解释。
            negatives.append((row.day, "foreground", row.platform_id))
        if row.keyboard_backend != "none":
            keyboard_days.add(row.day)
        else:
            negatives.append((row.day, "keyboard", row.platform_id))
        if row.key_position_stable:
            stable_days.add(row.day)
        else:
            negatives.append((row.day, "key_position", row.keyboard_backend))
        if row.titles_recorded:
            title_days.add(row.day)

    # 同一天既有正面也有负面证据（当天换过后端）时不报 gap：那天的数据部分可用，
    # 报"整天不支持"是错的。前端看到的是 foreground_days 少了一天。
    negatives = [
        item
        for item in negatives
        if not (
            (item[1] == "foreground" and item[0] in foreground_days)
            or (item[1] == "keyboard" and item[0] in keyboard_days)
            or (item[1] == "key_position" and item[0] in stable_days)
        )
    ]
    return {
        "total_days": total_days,
        "recorded_days": len(seen_days),
        "foreground_days": len(foreground_days),
        "keyboard_days": len(keyboard_days),
        "key_position_days": len(stable_days),
        "title_days": len(title_days),
        "gaps": _merge_runs(negatives),
    }


def empty(total_days: int) -> dict[str, object]:
    """没有数据库可查时的形状（例如状态接口在采集未装配时）。"""
    return {
        "total_days": total_days,
        "recorded_days": 0,
        "foreground_days": 0,
        "keyboard_days": 0,
        "key_position_days": 0,
        "title_days": 0,
        "gaps": [],
    }


__all__ = ["DayCapability", "empty", "load", "summarize"]
