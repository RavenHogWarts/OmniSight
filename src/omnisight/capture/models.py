"""采集层向存储层投递的不可变事实（02 文档 §4）。

这些对象是采集线程与写入线程之间的**唯一**接口。它们刻意满足三条：

* **不可变**（``frozen=True``）：跨线程传递，任何一侧都不该能改动对方看到的值。
* **不含任何平台语义**：``native_code`` 只是一个诊断用的整数，采集层不解释它。
* **不含窗口标题以外的任何文本**：按键事件里没有字符、没有顺序信息（08 文档 §2）。

``slots=True`` 不只是省内存：每个按键会生成一个 ``KeyEvent``，重度用户一天 6 万个。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ..adapters.ports import UNKNOWN_APP_ID

Confidence = Literal["high", "boundary", "unknown"]

#: 落盘时 ``confidence`` 的整数编码（03 文档 §2.5 的 ``confidence`` 列）。
CONFIDENCE_CODES: dict[str, int] = {"unknown": 0, "boundary": 1, "high": 2}
CONFIDENCE_NAMES: dict[int, str] = {value: key for key, value in CONFIDENCE_CODES.items()}


@dataclass(frozen=True, slots=True)
class Attribution:
    """一次按键归因的结果（04 文档 §4.3）。

    ``app_id = 0`` 表示未知前台——空闲、锁屏、系统外壳、被用户排除的应用。
    **用哨兵 0 而不是 None**：聚合表把 ``app_id`` 放进主键，而 ``WITHOUT ROWID``
    表的主键列隐含 ``NOT NULL``，两处用不同表示会让"未知"这一类对不上账
    （见 03 文档 §2.5 与 PROGRESS 里的偏离 3）。
    """

    app_id: int = UNKNOWN_APP_ID
    confidence: Confidence = "unknown"

    @property
    def known(self) -> bool:
        return self.app_id != UNKNOWN_APP_ID

    @property
    def confidence_code(self) -> int:
        return CONFIDENCE_CODES[self.confidence]


@dataclass(frozen=True, slots=True)
class KeyEvent:
    """一次完整的按下—抬起。写入线程据此填 ``raw_key_events_YYYY_MM`` 与各聚合表。"""

    key_id: str
    down_ts_ns: int
    up_ts_ns: int
    duration_ms: float
    app_id: int = UNKNOWN_APP_ID
    confidence: Confidence = "unknown"
    hid_usage: int | None = None
    native_code: int | None = None
    native_code2: int | None = None
    #: 时长被卡键防护截断过（04 文档 §3.4）。截断值仍参与聚合，但可被审计。
    clamped: bool = False

    @property
    def confidence_code(self) -> int:
        return CONFIDENCE_CODES[self.confidence]


@dataclass(frozen=True, slots=True)
class UsageSession:
    """一段前台应用会话。``app_id`` 在前台线程上就已解析（02 文档 §4.2）。"""

    app_id: int
    start_ts_ns: int
    end_ts_ns: int
    duration_ms: int
    window_title: str = ""
    #: 因空闲被截断：结束时刻是"最后一次输入 + 阈值"，不是发现空闲的时刻。
    idle_trimmed: bool = False

    @property
    def valid(self) -> bool:
        return self.end_ts_ns > self.start_ts_ns


__all__ = [
    "CONFIDENCE_CODES",
    "CONFIDENCE_NAMES",
    "Attribution",
    "Confidence",
    "KeyEvent",
    "UsageSession",
]
