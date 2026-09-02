"""M5 · 旧数据导入（schema v3，03 文档 §7、09 文档）。

导入是**用户触发的操作**而不是启动迁移：``up()`` 只推进版本号（schema 3 =
"本程序带导入器"），全部逻辑在 :class:`LegacyImporter`，由 ``services/legacy.py``
在后台线程里驱动、导入向导触发。放在 migrations 下是 03 文档 §7 的既定归属。

三条铁律（09 文档 §1）：

* **旧库只读**——先做快照，一切读取走快照，源文件字节不变；
* **不伪造**——TimeLens 按键没有时长/归因就让那些维度空着，绝不生成假事件、
  绝不用平均值填充（宁可让历史时段的时长指标为空）；
* **可续传、可撤销**——游标与数据同事务推进，中断后从断点继续不产生重复；
  撤销按天重算，与导入重叠的新采集数据保留。

撤销采用"**删除 + 按天重建 + 补差**"。纯减法做不了：聚合里的
``MAX(duration_max_ms)`` 不可逆。重建的完整公式是

    加回量 = 撤销前 − 重建后 − key_usage 贡献 − KeyTrace 导入贡献

后两项从导入时的**备份快照**重算（快照永不改变，重算即当年增量）。这四项之差
恰好是"无原始行支撑的其他量"——例如 ``store_raw`` 关闭期间的新采集——它们不
属于导入，必须保留。聚合是增量的，加回量恒非负。``duration_max`` 一类 MAX 列
不参与补差：重建值来自剩余原始行，已是精确值。
"""

from __future__ import annotations

import json
import logging
import shutil
import sqlite3
from collections.abc import Callable
from datetime import datetime, timedelta, tzinfo
from pathlib import Path
from typing import Any

from ...adapters.ports import AppIdentity
from ...capture.keymap import KEYS as _ALL_KEYS
from ...capture.models import KeyEvent, UsageSession
from ...capture.queue import EventQueue
from ...core.clock import SystemClock
from .. import capability as capability_table
from ..database import Database
from ..partitions import Partitions, raw_table
from ..repositories.apps import AppRegistry
from ..writer import (
    AGG_KEY_DAY_UPSERT,
    AGG_KEY_HOUR_UPSERT,
    AGG_KEY_MONTH_UPSERT,
    AGG_KEY_TOTAL_UPSERT,
    AGG_KEY_YEAR_UPSERT,
    AGG_PRESS_HOUR_UPSERT,
    StorageWriter,
    day_bucket,
)

logger = logging.getLogger(__name__)

#: 已知的 ``key_id`` 全集。旧 KeyTrace 的 ``key_id`` 与新库同一命名空间，但仍要
#: 校验——两个项目的键位表可能因版本差异不同步，未知的键**跳过并计数**而不是
#: 让一条 ``INSERT`` 毁掉整批。
KNOWN_KEY_IDS: frozenset[str] = frozenset(key.id for key in _ALL_KEYS)

#: TimeLens ``key_usage.key_name``（显示名）→ 新库 ``key_id``。
#: 来源是 TimeLens ``monitor._SPECIAL_KEYS`` 与 ``KeyCode`` 分支的完整反推，
#: 包括 ``Ctrl+字母`` 在 pynput 里表现为控制字符的情形（Ctrl+C → ``"\\x03"``）。
KEY_NAME_MAP: dict[str, str] = {
    # ── pynput 特殊键（TimeLens _SPECIAL_KEYS 的显示名）──────────────────
    "Space": "space",
    "Enter": "enter",  # 歧义：无法区分主键盘与小键盘 Enter
    "Tab": "tab",
    "Backspace": "backspace",
    "Del": "delete",
    "Ins": "insert",
    "Home": "home",
    "End": "end",
    "PgUp": "page_up",
    "PgDn": "page_down",
    "Esc": "esc",
    "Caps Lock": "caps_lock",
    "ShiftLeft": "shift_left",
    "ShiftRight": "shift_right",
    "CtrlLeft": "control_left",
    "CtrlRight": "control_right",
    "Alt": "alt_left",  # 歧义：旧版把左右 Alt 记成同一个名字，全部归左
    "Win": "win_left",  # 歧义：同上
    "Menu": "menu",
    "Up": "arrow_up",
    "Down": "arrow_down",
    "Left": "arrow_left",
    "Right": "arrow_right",
    "PrtSc": "print_screen",
    "ScrLk": "scroll_lock",
    "Pause": "pause",
    "Num": "num_lock",
    # ── 小键盘（KeyCode.vk 96–111）──────────────────────────────────────
    **{f"Num{digit}": f"numpad_{digit}" for digit in range(10)},
    "Num*": "numpad_multiply",
    "Num+": "numpad_add",
    "Num-": "numpad_subtract",
    "Num.": "numpad_decimal",
    "Num/": "numpad_divide",
    # ── 功能键（Key.f1..f24 → "F1".."F24"）──────────────────────────────
    **{f"F{number}": f"f{number}" for number in range(1, 25)},
    # ── 字母与数字（KeyCode.char，字母已大写）───────────────────────────
    **{chr(code): f"key_{chr(code).lower()}" for code in range(ord("A"), ord("Z") + 1)},
    **{chr(code): f"digit{chr(code)}" for code in range(ord("0"), ord("9") + 1)},
    # ── 符号字符 ─────────────────────────────────────────────────────────
    "`": "grave",
    "-": "minus",
    "=": "equal",
    "[": "bracket_left",
    "]": "bracket_right",
    "\\": "backslash",
    ";": "semicolon",
    "'": "quote",
    ",": "comma",
    ".": "period",
    "/": "slash",
}

#: 显示名层面的歧义键：旧数据无法区分的物理键。报告与向导步骤 2 要展示。
AMBIGUOUS_DISPLAY_NAMES: tuple[str, ...] = ("Alt", "Win", "Enter")

#: ``Ctrl+字母`` 的 ``KeyCode.char`` 是控制字符。物理键就是那个字母键，Ctrl
#: 修饰键自身由 CtrlLeft/CtrlRight 单独计数，因此映射到字母键不是编造。
_CONTROL_CHAR_MAP: dict[str, str] = {
    chr(code): f"key_{chr(96 + code)}" for code in range(1, 27)
}

#: TimeLens 心跳落盘的周期上界（``ACTIVE_FLUSH_INTERVAL`` 10s + 轮询 1s + 容差）。
#: 同一应用相邻两行间隙不超过它时视为同一次访问的延续段（``end_reason='heartbeat'``）。
#: 这是对 TimeLens **确定性** flush 周期的重建，不是猜测——它丢失了访问边界，
#: 但时间戳足以把边界找回来（对照 M2 偏离 41：那边是"无法事后推断"，
#: 这里信息完整）。
HEARTBEAT_GAP_SECONDS = 15.0
HEARTBEAT_GAP_NS = int(HEARTBEAT_GAP_SECONDS * 1_000_000_000)

SESSION_BATCH = 500
KEY_USAGE_BATCH = 2000
RAW_BATCH = 2000

STATE_KEY = "legacy_import"

#: 阶段顺序。``state.phase`` 是**下一个待执行**的阶段。
PHASES: tuple[str, ...] = ("tl_sessions", "tl_keys", "kt_raw", "finalize")

TIMELENS_TABLES = frozenset({"app_usage", "key_usage"})
KEYTRACE_TABLES = frozenset({"agg_key_day", "agg_key_total"})


class LegacyImportError(RuntimeError):
    """导入/撤销无法继续。消息面向用户（向导直接展示）。"""


class ImportCancelled(Exception):
    """用户暂停。游标已保存，再次运行即续传。"""


def up(conn: sqlite3.Connection) -> None:
    """版本锚点：schema 3 = 本程序带导入器。导入由用户触发，启动时不做任何事。"""


def map_key_name(name: str) -> str | None:
    """TimeLens 显示名 → ``key_id``。映射不了返回 None（调用方计入 unmapped）。"""
    mapped = KEY_NAME_MAP.get(name)
    if mapped is not None:
        return mapped
    return _CONTROL_CHAR_MAP.get(name)


# ── 快照与只读连接 ───────────────────────────────────────────────────────


def connect_readonly(path: Path) -> sqlite3.Connection:
    """以只读打开（快照或用户指定的旧库）。"""
    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def snapshot_legacy(path: Path, target: Path) -> Path:
    """把旧库复制到 ``target``。**源文件绝不写入**（判据：导入后字节级未变）。

    首选 SQLite 在线 backup API（源以 ``mode=ro`` 打开，WAL 内容会被正确并入）；
    只读打开失败时（残留 ``-shm`` 需要恢复等）退化为复制三件套再从副本
    checkpoint——复制同样不修改源文件。
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        source = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
        try:
            destination = sqlite3.connect(str(target))
            try:
                with destination:
                    source.backup(destination)
            finally:
                destination.close()
        finally:
            source.close()
        return target
    except sqlite3.Error:
        logger.warning("旧库只读备份失败，改为文件复制：%s", path, exc_info=True)
    for suffix in ("", "-wal", "-shm"):
        source_file = Path(str(path) + suffix)
        if source_file.exists():
            shutil.copy2(source_file, str(target) + suffix)
    conn = sqlite3.connect(str(target))
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.commit()
    finally:
        conn.close()
    # 截断后的 -wal/-shm 是空壳，删掉让备份目录只留干净的主文件。
    for suffix in ("-wal", "-shm"):
        Path(str(target) + suffix).unlink(missing_ok=True)
    return target


# ── 探测与扫描（向导步骤 1/2 的数据来源）─────────────────────────────────


def classify_legacy_database(path: Path) -> str | None:
    """按**内容**判断旧库类型，文件名只是线索。返回 ``timelens`` / ``keytrace`` / None。"""
    if not path.is_file():
        return None
    try:
        conn = connect_readonly(path)
        try:
            names = frozenset(
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            )
        finally:
            conn.close()
    except sqlite3.Error:
        return None
    if names >= TIMELENS_TABLES:
        return "timelens"
    if KEYTRACE_TABLES & names and "app_usage" not in names:
        return "keytrace"
    return None


def detect_legacy(exe_dir: Path) -> list[dict[str, Any]]:
    """默认搜索路径里的旧库（03 文档 §7.1）：``<exe 同级>/data/`` 下两个已知文件名。"""
    found: list[dict[str, Any]] = []
    data = exe_dir / "data"
    for filename in ("usage.db", "keytrace.sqlite3"):
        candidate = data / filename
        kind = classify_legacy_database(candidate)
        if kind is None:
            continue
        stat = candidate.stat()
        found.append(
            {
                "path": str(candidate),
                "kind": kind,
                "size_bytes": stat.st_size,
                "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(
                    timespec="seconds"
                ),
            }
        )
    return found


def scan_timelens(conn: sqlite3.Connection) -> dict[str, Any]:
    """TimeLens 旧库统计。只读，供预览与损失说明。"""
    sessions = conn.execute(
        "SELECT COUNT(*), MIN(date), MAX(date) FROM app_usage"
    ).fetchone()
    has_titles = conn.execute(
        "SELECT EXISTS(SELECT 1 FROM app_usage WHERE window_title <> '' LIMIT 1)"
    ).fetchone()[0]
    key_rows = conn.execute(
        "SELECT COUNT(*), COUNT(DISTINCT date), MIN(date), MAX(date),"
        " COALESCE(SUM(press_count), 0) FROM key_usage"
    ).fetchone()
    key_names = frozenset(
        row[0] for row in conn.execute("SELECT DISTINCT key_name FROM key_usage")
    )
    return {
        "sessions": {
            "rows": sessions[0],
            "date_min": sessions[1],
            "date_max": sessions[2],
            "has_titles": bool(has_titles),
        },
        "key_usage": {
            "rows": key_rows[0],
            "days": key_rows[1],
            "date_min": key_rows[2],
            "date_max": key_rows[3],
            "presses": key_rows[4],
            "unmapped_names": sorted(
                name for name in key_names if map_key_name(name) is None
            ),
            "ambiguous_names": sorted(
                name
                for name in AMBIGUOUS_DISPLAY_NAMES
                if name in key_names and name in KEY_NAME_MAP
            ),
        },
    }


def scan_keytrace(conn: sqlite3.Connection) -> dict[str, Any]:
    """KeyTrace 旧库统计 + 它覆盖的按键日期集合（冲突判定的权威方）。"""
    months = [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name LIKE 'raw_key_events_%' ORDER BY name"
        )
    ]
    total = 0
    first_ns: int | None = None
    last_ns: int | None = None
    for table in months:
        row = conn.execute(
            f"SELECT COUNT(*), MIN(down_ts_ns), MAX(down_ts_ns) FROM {table}"
        ).fetchone()
        total += row[0] or 0
        if row[1] is not None:
            first_ns = row[1] if first_ns is None else min(first_ns, row[1])
        if row[2] is not None:
            last_ns = row[2] if last_ns is None else max(last_ns, row[2])
    days = [
        row[0]
        for row in conn.execute("SELECT DISTINCT bucket FROM agg_key_day ORDER BY bucket")
    ]
    return {
        "raw": {
            "tables": len(months),
            "rows": total,
            "ts_min_ns": first_ns,
            "ts_max_ns": last_ns,
        },
        "key_days": days,
    }


# ── 状态（meta.legacy_import）────────────────────────────────────────────


def load_state(db: Database) -> dict[str, Any] | None:
    raw = db.meta_get(STATE_KEY)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        logger.exception("legacy_import 状态损坏，忽略")
        return None


def _save_state(db: Database, conn: sqlite3.Connection, state: dict[str, Any]) -> None:
    state["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    db.meta_set(STATE_KEY, json.dumps(state, ensure_ascii=False), conn=conn)


def _merge_id_ranges(ranges: list[list[int]], new_ids: list[int]) -> None:
    """把一批新分配的行 id 并进连续段列表（就地）。

    撤销按段删除导入行。批内 id 连续，批与批之间可能被写线程的新采集行
    挤开——那正是要记成两段而不是一个区间的原因。
    """
    for row_id in new_ids:
        if ranges and ranges[-1][1] + 1 == row_id:
            ranges[-1][1] = row_id
        else:
            ranges.append([row_id, row_id])


def _collect_new_ids(conn: sqlite3.Connection, table: str, pre_max: int) -> list[int]:
    """同一事务内 INSERT 之后取回本批写入的行 id。

    进程内写锁 + ``BEGIN IMMEDIATE`` 保证这个事务里不会混进写线程的行：
    它的插入发生在别的事务，对本事务的 SELECT 不可见。
    """
    return [
        row[0] for row in conn.execute(f"SELECT id FROM {table} WHERE id > ?", (pre_max,))
    ]


def _ranges_where(column: str, ranges: list[list[int]]) -> tuple[str, list[int]]:
    """段列表 → ``(SQL 片段, 参数)``。空段列表返回恒假条件。"""
    if not ranges:
        return ("1 = 0", [])
    clauses: list[str] = []
    params: list[int] = []
    for low, high in ranges:
        clauses.append(f"{column} BETWEEN ? AND ?")
        params.extend((low, high))
    return (" OR ".join(clauses), params)


def _ts_ns(text: str) -> int:
    """TimeLens 的 ``isoformat()`` 字符串 → 纳秒。naive 视为本地时间（03 文档 §7.2）。"""
    moment = datetime.fromisoformat(text)
    if moment.tzinfo is None:
        moment = moment.astimezone()
    return int(moment.timestamp() * 1_000_000_000)


def _day_bounds_ns(day: str, tz: tzinfo | None) -> tuple[int, int]:
    """本地日 → ``[当日零点, 次日零点)`` 的纪元纳秒。"""
    start = datetime.fromisoformat(day)
    start = start.replace(tzinfo=tz) if tz else start.astimezone()
    start_ns = int(start.timestamp() * 1_000_000_000)
    return (start_ns, start_ns + 86_400 * 1_000_000_000)


# ── 导入器 ───────────────────────────────────────────────────────────────


class LegacyImporter:
    """把旧 TimeLens / KeyTrace 快照导入新库。可重复调用 :meth:`run` 续传。

    聚合维护完全复用 :class:`StorageWriter` 的 rollup：导入行与实时采集走
    **同一套**分桶、切片与 upsert，口径不可能分叉——这是合并项目里最不该
    出现第二份实现的地方。
    """

    def __init__(
        self,
        db: Database,
        *,
        tz: tzinfo | None = None,
        store_raw: bool = True,
        platform_id: str = "windows",
    ) -> None:
        self._db = db
        self._tz = tz
        self._platform_id = platform_id
        self._registry = AppRegistry(db, platform_id)
        # 不 start()：只要它的 rollup/persist，不要它的线程。队列永远不会有事件。
        self._writer = StorageWriter(db, EventQueue(), tz=tz, store_raw=store_raw)
        self._partitions = Partitions()
        self._clock = SystemClock(tz)

    # ── 主入口 ──────────────────────────────────────────────────────────

    def run(
        self,
        state: dict[str, Any],
        sources: dict[str, Path | None],
        backup_dir: Path,
        *,
        cancel_check: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        """执行（或续传）导入。``state`` 就地更新并随每批事务持久化。

        ``sources``: ``{"timelens": Path | None, "keytrace": Path | None}``。
        用户暂停（``cancel_check`` 返回真）时抛 :class:`ImportCancelled`，
        此前游标已随最后一批提交，再次 ``run`` 即续传。
        """
        if state.get("status") == "done":
            return state
        self._init_state(state, sources, backup_dir)
        with self._db.transaction() as conn:
            _save_state(self._db, conn, state)

        cancel = cancel_check or (lambda: False)
        snapshots = self._make_snapshots(state, sources, backup_dir)

        tl_conn = (
            connect_readonly(snapshots["timelens"])
            if snapshots.get("timelens")
            else None
        )
        kt_conn = (
            connect_readonly(snapshots["keytrace"])
            if snapshots.get("keytrace")
            else None
        )
        try:
            kt_days: set[str] = set()
            if kt_conn is not None:
                kt_days = set(scan_keytrace(kt_conn)["key_days"])
                state["kt_days"] = sorted(kt_days)

            if tl_conn is not None:
                if state["phase"] == "tl_sessions":
                    self._run_timelens_sessions(state, tl_conn, cancel)
                    self._complete_phase(state, "tl_keys")
                if state["phase"] == "tl_keys":
                    self._run_timelens_keys(state, tl_conn, kt_days, cancel)
                    self._complete_phase(state, "kt_raw")
            elif state["phase"] in ("tl_sessions", "tl_keys"):
                # 没有 TimeLens 数据源：跳过它的两个阶段。
                self._complete_phase(state, "kt_raw")

            if kt_conn is not None:
                if state["phase"] == "kt_raw":
                    self._run_keytrace_raw(state, kt_conn, cancel)
                    self._complete_phase(state, "finalize")
            elif state["phase"] == "kt_raw":
                self._complete_phase(state, "finalize")

            if state["phase"] == "finalize":
                state["status"] = "done"
                state["finished_at"] = datetime.now().astimezone().isoformat(
                    timespec="seconds"
                )
                with self._db.transaction() as conn:
                    _save_state(self._db, conn, state)
        finally:
            if tl_conn is not None:
                tl_conn.close()
            if kt_conn is not None:
                kt_conn.close()
        return state

    def _init_state(
        self, state: dict[str, Any], sources: dict[str, Path | None], backup_dir: Path
    ) -> None:
        state["status"] = "importing"
        state.setdefault(
            "started_at", datetime.now().astimezone().isoformat(timespec="seconds")
        )
        state.setdefault(
            "sources",
            {name: (str(path) if path else None) for name, path in sources.items()},
        )
        state.setdefault("phase", PHASES[0])
        state.setdefault(
            "cursors",
            {
                "tl_usage_id": 0,
                "tl_last_row": None,
                "tl_key_row": None,
                "kt_table": None,
                "kt_id": 0,
            },
        )
        state.setdefault("bounds", {"session_ids": [], "raw_ids": {}})
        state.setdefault("capability_rows", [])
        state.setdefault("counts", {})
        state.setdefault("skipped_days", [])
        state.setdefault("days", {"sessions": [], "key_usage": [], "raw": []})
        state["backup_dir"] = str(backup_dir)

    def _make_snapshots(
        self, state: dict[str, Any], sources: dict[str, Path | None], backup_dir: Path
    ) -> dict[str, Path]:
        """快照幂等：已存在且源文件未变（大小 + mtime）时跳过。"""
        recorded = state.setdefault("snapshots", {})
        result: dict[str, Path] = {}
        for name, path in sources.items():
            if path is None:
                continue
            stat = path.stat()
            fingerprint = f"{stat.st_size}:{int(stat.st_mtime)}"
            target = backup_dir / (
                "usage.db" if name == "timelens" else "keytrace.sqlite3"
            )
            if not target.exists() or recorded.get(name) != fingerprint:
                snapshot_legacy(path, target)
                recorded[name] = fingerprint
            result[name] = target
        return result

    def _complete_phase(self, state: dict[str, Any], next_phase: str) -> None:
        state["phase"] = next_phase
        with self._db.transaction() as conn:
            _save_state(self._db, conn, state)

    def _cancelled(self, cancel: Callable[[], bool]) -> None:
        if cancel():
            raise ImportCancelled

    # ── 批量提交（全部阶段共用）─────────────────────────────────────────

    def _persist_batch(
        self,
        state: dict[str, Any],
        *,
        events: list[KeyEvent] | None = None,
        sessions: list[UsageSession] | None = None,
        extra_writes: Callable[[sqlite3.Connection], None] | None = None,
    ) -> None:
        """一个事务：rollup 写入 → 记录新行 id 段 → 调用方额外写入 → 保存状态。

        游标（调用方已写进 ``state``）与数据同事务提交——断点续传的一致性由
        这一条保证：崩溃时两者要么都发生、要么都没发生。
        """
        events = events or []
        sessions = sessions or []
        if not (events or sessions or extra_writes):
            # 没有数据也要推进游标（整批都是损坏行的场景），否则重启后
            # 同一批会被无限重取。
            with self._db.transaction() as conn:
                _save_state(self._db, conn, state)
            return
        batch: list[Any] = [*events, *sessions]
        rollup = self._writer.build_rollup(batch) if batch else None

        if rollup is not None and rollup.raw_by_month:
            # 月表 DDL 走独立事务先提交（M1 偏离 21 的教训：与数据共命运会让
            # 进程内缓存在回滚后永久说谎）。
            try:
                with self._db.transaction() as conn:
                    for month in rollup.raw_by_month:
                        self._partitions.ensure(conn, month)
            except Exception:
                self._partitions.reset()
                raise

        now = self._clock.now()
        with self._db.transaction() as conn:
            pre_session = 0
            pre_raw: dict[str, int] = {}
            if rollup is not None:
                if rollup.sessions:
                    pre_session = conn.execute(
                        "SELECT COALESCE(MAX(id), 0) FROM usage_session"
                    ).fetchone()[0]
                for month in rollup.raw_by_month:
                    table = raw_table(month)
                    pre_raw[table] = conn.execute(
                        f"SELECT COALESCE(MAX(id), 0) FROM {table}"
                    ).fetchone()[0]
                self._writer.persist(conn, rollup, now, dropped=0, write_errors=0)
            if extra_writes is not None:
                extra_writes(conn)
            if rollup is not None and rollup.sessions:
                ids = _collect_new_ids(conn, "usage_session", pre_session)
                _merge_id_ranges(state["bounds"]["session_ids"], ids)
            for table, pre_max in pre_raw.items():
                ids = _collect_new_ids(conn, table, pre_max)
                _merge_id_ranges(state["bounds"]["raw_ids"].setdefault(table, []), ids)
            _save_state(self._db, conn, state)

    def _write_capability(
        self,
        conn: sqlite3.Connection,
        state: dict[str, Any],
        days: set[str],
        *,
        backend: str,
        foreground: bool,
        titles: bool,
        key_position_stable: bool,
    ) -> None:
        """为覆盖到的每一天写 ``capture_capability``（09 文档 §2.4）。

        这张表是"历史数据为什么没有应用归因"的唯一可查依据；主键同时记进
        state，撤销时精确删除这些行。
        """
        now = self._clock.now()
        recorded = state["capability_rows"]
        for day in sorted(days):
            capability_table.upsert(
                conn,
                day_bucket=day,
                platform_id=self._platform_id,
                keyboard_backend=backend,
                foreground_available=foreground,
                titles_recorded=titles,
                key_position_stable=key_position_stable,
                now=now,
            )
            key = [day, backend, int(foreground), int(key_position_stable)]
            if key not in recorded:
                recorded.append(key)

    # ── 阶段 1：TimeLens app_usage → usage_session ─────────────────────

    def _run_timelens_sessions(
        self,
        state: dict[str, Any],
        conn: sqlite3.Connection,
        cancel: Callable[[], bool],
    ) -> None:
        cursor = state["cursors"]
        counts = state["counts"]
        app_ids: dict[str, int] = {}
        visit = _VisitContext.from_dict(cursor.get("tl_visit_ctx"))

        while True:
            self._cancelled(cancel)
            rows = conn.execute(
                "SELECT id, app_name, process_name, exe_path, window_title,"
                " start_time, end_time, duration_seconds, date"
                " FROM app_usage WHERE id > ? ORDER BY id LIMIT ?",
                (cursor["tl_usage_id"], SESSION_BATCH),
            ).fetchall()
            if not rows:
                break
            # 上一批的最后一行作为本批的第一条输入（lookahead 需要它判断延续）。
            pending = cursor.get("tl_last_row")
            stream: list[Any] = (
                [_PendingRow(pending)] if pending else []
            ) + list(rows)
            sessions: list[UsageSession] = []
            skipped = 0
            days: set[str] = set()
            for index, row in enumerate(stream):
                try:
                    start_ns = _ts_ns(row["start_time"])
                    end_ns = _ts_ns(row["end_time"])
                except ValueError:
                    skipped += 1
                    continue
                if end_ns <= start_ns:
                    skipped += 1
                    continue
                next_row = stream[index + 1] if index + 1 < len(stream) else None
                if next_row is None:
                    # 本批的最后一段**暂不写**：它是否延续要看下一批的第一行，
                    # 现在写成 'switch' 而下一行恰好延续的话，这次访问就丢了
                    # （全为 heartbeat 的访问在查询侧不存在）。它作为 pending
                    # 随游标持久化，下一批或收尾时落盘。
                    continue
                app_id = self._resolve_app(app_ids, row)
                session, visit = _build_session(row, app_id, visit, next_row)
                sessions.append(session)
                days.add(row["date"])
            if sessions or skipped:
                counts["sessions_imported"] = (
                    counts.get("sessions_imported", 0) + len(sessions)
                )
                counts["sessions_skipped"] = counts.get("sessions_skipped", 0) + skipped
                _extend_unique(state["days"]["sessions"], days)
            last = rows[-1]
            cursor["tl_usage_id"] = last["id"]
            cursor["tl_last_row"] = _serialize_row(last)
            cursor["tl_visit_ctx"] = visit.as_dict()
            self._persist_batch(state, sessions=sessions)

        # 阶段收尾：最后一段 pending 以 'switch' 落盘（没有下一段了）。
        pending = cursor.get("tl_last_row")
        if pending is not None:
            row = _PendingRow(pending)
            try:
                app_id = self._resolve_app(app_ids, row)
                session, _ = _build_session(row, app_id, visit, None)
                counts["sessions_imported"] = counts.get("sessions_imported", 0) + 1
                _extend_unique(state["days"]["sessions"], {row["date"]})
                cursor["tl_last_row"] = None
                cursor["tl_visit_ctx"] = _VisitContext().as_dict()
                self._persist_batch(state, sessions=[session])
            except (ValueError, LegacyImportError):
                logger.warning("收尾段无法导入，跳过", exc_info=True)

        days_covered = set(state["days"]["sessions"])
        if days_covered:
            has_titles = bool(
                conn.execute(
                    "SELECT EXISTS(SELECT 1 FROM app_usage"
                    " WHERE window_title <> '' LIMIT 1)"
                ).fetchone()[0]
            )
            counts["session_days"] = len(days_covered)
            with self._db.transaction() as conn2:
                self._write_capability(
                    conn2,
                    state,
                    days_covered,
                    backend="none",
                    foreground=True,
                    titles=has_titles,
                    key_position_stable=False,
                )
                _save_state(self._db, conn2, state)

    def _resolve_app(self, cache: dict[str, int], row: Any) -> int:
        process_name = row["process_name"] or ""
        app_id = cache.get(process_name)
        if app_id is not None:
            return app_id
        identity = AppIdentity(
            app_key=process_name.casefold(),
            identity_kind="process",
            display_name=row["app_name"] or process_name,
            process_name=process_name,
            exe_path=row["exe_path"] or "",
        )
        app_id = self._registry.resolve(identity, now=self._clock.now())
        cache[process_name] = app_id
        return app_id

    # ── 阶段 2：TimeLens key_usage → 聚合（无原始事件）──────────────────

    def _run_timelens_keys(
        self,
        state: dict[str, Any],
        conn: sqlite3.Connection,
        kt_days: set[str],
        cancel: Callable[[], bool],
    ) -> None:
        cursor = state["cursors"]
        counts = state["counts"]
        skipped: set[str] = set(state["skipped_days"])

        while True:
            self._cancelled(cancel)
            where = ""
            params: tuple[Any, ...] = ()
            last = cursor.get("tl_key_row")
            if last is not None:
                where = "WHERE (date, hour, key_name) > (?, ?, ?)"
                params = (last[0], last[1], last[2])
            rows = conn.execute(
                f"SELECT date, hour, key_name, press_count FROM key_usage {where}"
                f" ORDER BY date, hour, key_name LIMIT {KEY_USAGE_BATCH}",
                params,
            ).fetchall()
            if not rows:
                break

            key_day: dict[tuple[str, str], int] = {}
            key_hour: dict[tuple[str, int, str], int] = {}
            press_hour: dict[tuple[str, int], int] = {}
            imported_days: set[str] = set()

            for row in rows:
                day, hour, name, press = (
                    row["date"],
                    row["hour"],
                    row["key_name"],
                    row["press_count"],
                )
                if day in kt_days:
                    # 冲突规则（03 文档 §7.4）：同日两库都有按键，以 KeyTrace 为准。
                    skipped.add(day)
                    continue
                key_id = map_key_name(name)
                if key_id is None:
                    unmapped = counts.setdefault("unmapped_keys", {})
                    unmapped[name] = unmapped.get(name, 0) + press
                    continue
                key_day[(day, key_id)] = key_day.get((day, key_id), 0) + press
                key_hour[(day, hour, key_id)] = (
                    key_hour.get((day, hour, key_id), 0) + press
                )
                press_hour[(day, hour)] = press_hour.get((day, hour), 0) + press
                imported_days.add(day)

            last_row = rows[-1]
            cursor["tl_key_row"] = [last_row["date"], last_row["hour"], last_row["key_name"]]
            state["skipped_days"] = sorted(skipped)
            if key_day:
                counts["key_rows"] = counts.get("key_rows", 0) + len(rows)
                counts["key_presses"] = (
                    counts.get("key_presses", 0) + sum(key_day.values())
                )
                _extend_unique(state["days"]["key_usage"], imported_days)

            self._persist_batch(
                state,
                extra_writes=lambda write_conn, kd=key_day, kh=key_hour, ph=press_hour: (
                    _apply_key_usage_delta(write_conn, kd, kh, ph)
                ),
            )

        days_covered = set(state["days"]["key_usage"])
        if days_covered:
            counts["key_usage_days"] = len(days_covered)
            with self._db.transaction() as conn2:
                self._write_capability(
                    conn2,
                    state,
                    days_covered,
                    backend="pynput_legacy",
                    foreground=False,
                    titles=False,
                    key_position_stable=False,
                )
                _save_state(self._db, conn2, state)

    # ── 阶段 3：KeyTrace raw_key_events → 原始事件 + 聚合 ───────────────

    def _run_keytrace_raw(
        self,
        state: dict[str, Any],
        conn: sqlite3.Connection,
        cancel: Callable[[], bool],
    ) -> None:
        cursor = state["cursors"]
        counts = state["counts"]
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name LIKE 'raw_key_events_%' ORDER BY name"
            )
        ]
        start_at = (
            tables.index(cursor["kt_table"]) if cursor.get("kt_table") in tables else 0
        )

        for table in tables[start_at:]:
            last_id = cursor["kt_id"] if table == cursor.get("kt_table") else 0
            while True:
                self._cancelled(cancel)
                rows = conn.execute(
                    f"SELECT id, key_id, down_ts_ns, up_ts_ns, duration_ms,"
                    f" scan_code, virtual_key_code FROM {table}"
                    f" WHERE id > ? ORDER BY id LIMIT {RAW_BATCH}",
                    (last_id,),
                ).fetchall()
                if not rows:
                    break
                events: list[KeyEvent] = []
                days: set[str] = set()
                for row in rows:
                    key_id = row["key_id"]
                    if key_id not in KNOWN_KEY_IDS:
                        unmapped = counts.setdefault("unmapped_keys", {})
                        unmapped[key_id] = unmapped.get(key_id, 0) + 1
                        continue
                    events.append(
                        KeyEvent(
                            key_id=key_id,
                            down_ts_ns=row["down_ts_ns"],
                            up_ts_ns=row["up_ts_ns"],
                            duration_ms=row["duration_ms"],
                            app_id=0,
                            confidence="unknown",
                            native_code=row["scan_code"],
                            native_code2=row["virtual_key_code"],
                        )
                    )
                    days.add(day_bucket(row["down_ts_ns"], self._tz))
                last = rows[-1]
                last_id = last["id"]
                cursor["kt_table"] = table
                cursor["kt_id"] = last_id
                counts["raw_imported"] = counts.get("raw_imported", 0) + len(events)
                _extend_unique(state["days"]["raw"], days)
                self._persist_batch(state, events=events)
                if len(rows) < RAW_BATCH:
                    break

        days_covered = set(state["days"]["raw"])
        if days_covered:
            counts["raw_days"] = len(days_covered)
            with self._db.transaction() as conn2:
                self._write_capability(
                    conn2,
                    state,
                    days_covered,
                    backend="raw_input",
                    foreground=False,
                    titles=False,
                    key_position_stable=True,
                )
                _save_state(self._db, conn2, state)

    # ── 撤销（09 文档 §2.5）──────────────────────────────────────────────

    def undo(self, state: dict[str, Any]) -> None:
        """删除导入的数据并按天重算。新采集的数据（含重叠日）保留。"""
        if state.get("status") not in ("done", "paused", "importing", "failed"):
            raise LegacyImportError("当前状态没有可撤销的导入")
        bounds = state["bounds"]
        days = sorted(
            set(state["days"]["sessions"])
            | set(state["days"]["key_usage"])
            | set(state["days"]["raw"])
        )
        contributions = self._legacy_contributions(state, days)

        with self._db.transaction() as conn:
            where, params = _ranges_where("id", bounds["session_ids"])
            if params:
                conn.execute(f"DELETE FROM usage_session WHERE {where}", params)
            for table, ranges in bounds["raw_ids"].items():
                if not self._db.table_exists(table):
                    continue
                where, params = _ranges_where("id", ranges)
                if params:
                    conn.execute(f"DELETE FROM {table} WHERE {where}", params)

            for day in days:
                self._rebuild_day(conn, day, contributions)

            self._rebuild_derived(conn, contributions)

            for day, backend, foreground, stable in state["capability_rows"]:
                conn.execute(
                    "DELETE FROM capture_capability WHERE day_bucket = ?"
                    " AND platform_id = ? AND keyboard_backend = ?"
                    " AND foreground_available = ? AND key_position_stable = ?",
                    (day, self._platform_id, backend, foreground, stable),
                )

            state["status"] = "undone"
            state["finished_at"] = datetime.now().astimezone().isoformat(
                timespec="seconds"
            )
            _save_state(self._db, conn, state)
            self._db.bump_data_version(conn)

    # ── 撤销的内部机制 ──────────────────────────────────────────────────

    def _legacy_contributions(
        self, state: dict[str, Any], days: list[str]
    ) -> _Contributions:
        """从备份快照重算当年导入加进聚合的量（撤销补差公式里的减项）。

        快照缺失时抛 :class:`LegacyImportError`——补差没有它就会把本该删除的
        导入量当成"无支撑量"加回去，撤销变成空操作，宁可拒绝。
        """
        backup_dir = Path(state["backup_dir"])
        tl_snapshot = backup_dir / "usage.db"
        kt_snapshot = backup_dir / "keytrace.sqlite3"
        contributions = _Contributions()
        day_set = set(days)
        skipped = set(state.get("skipped_days", []))

        needs_tl = state["days"]["key_usage"] or state["days"]["sessions"]
        if needs_tl:
            if not tl_snapshot.exists():
                raise LegacyImportError(
                    "撤销导入需要导入时的备份快照（data/backup/…/usage.db），但它已不存在"
                )
            conn = connect_readonly(tl_snapshot)
            try:
                for row in conn.execute(
                    "SELECT date, hour, key_name, press_count FROM key_usage"
                ):
                    day = row["date"]
                    if day not in day_set or day in skipped:
                        continue
                    key_id = map_key_name(row["key_name"])
                    if key_id is None:
                        continue
                    press = row["press_count"]
                    # key_usage 只有次数：时长两列为 0（与导入时的写入口径一致）。
                    contributions.key_day[(day, key_id)] = _Contributions._merge(
                        contributions.key_day.get((day, key_id)), [press, 0.0, 0.0]
                    )
                    contributions.key_hour[(day, row["hour"], key_id)] = _Contributions._merge(
                        contributions.key_hour.get((day, row["hour"], key_id)),
                        [press, 0.0],
                    )
                    contributions.press_hour[(day, row["hour"])] = _Contributions._merge(
                        contributions.press_hour.get((day, row["hour"])), [press, 0.0]
                    )
                # 会话贡献同样要从快照重算：session 行虽已物理删除，但它们对
                # ``agg_app_day`` / ``agg_app_hour`` 的量是补差公式的减项——
                # 不减的话，"删除前 − 重建后"会把导入的时长当成无支撑量加回。
                # 重放用与导入**同一套**访问推断（gap 阈值），保证重算 = 当年增量。
                if state["days"]["sessions"]:
                    self._replay_timelens_sessions(conn, day_set, contributions)
            finally:
                conn.close()

        if state["days"]["raw"]:
            if not kt_snapshot.exists():
                raise LegacyImportError(
                    "撤销导入需要导入时的备份快照"
                    "（data/backup/…/keytrace.sqlite3），但它已不存在"
                )
            conn = connect_readonly(kt_snapshot)
            try:
                raw_days = set(state["days"]["raw"])
                months = sorted({day[:7] for day in day_set if day in raw_days})
                for month in months:
                    table = f"raw_key_events_{month.replace('-', '_')}"
                    exists = conn.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                        (table,),
                    ).fetchone()
                    if not exists:
                        continue
                    for day in (d for d in day_set if d.startswith(month) and d in raw_days):
                        start_ns, end_ns = _day_bounds_ns(day, self._tz)
                        rows = conn.execute(
                            f"SELECT key_id, down_ts_ns, up_ts_ns, duration_ms"
                            f" FROM {table}"
                            " WHERE down_ts_ns >= ? AND down_ts_ns < ?",
                            (start_ns, end_ns),
                        ).fetchall()
                        events = [
                            KeyEvent(
                                key_id=row["key_id"],
                                down_ts_ns=row["down_ts_ns"],
                                up_ts_ns=row["up_ts_ns"],
                                duration_ms=row["duration_ms"],
                            )
                            for row in rows
                            if row["key_id"] in KNOWN_KEY_IDS
                        ]
                        rollup = self._writer.build_rollup(events)
                        contributions.add_rollup(rollup)
            finally:
                conn.close()
        return contributions

    def _replay_timelens_sessions(
        self,
        conn: sqlite3.Connection,
        day_set: set[str],
        contributions: _Contributions,
    ) -> None:
        """从快照重放 TimeLens 会话导入，把当年的聚合增量算进贡献清单。

        与 :meth:`_run_timelens_sessions` 用同一套访问推断（``HEARTBEAT_GAP_NS``
        与 lookahead）——重算必须等于当年增量，否则撤销的减项本身就不对。
        只需覆盖受影响的日子；``app_id`` 用 ``app`` 表的现状解析（导入建的行
        还在，撤销不删 ``app`` 维表行）。
        """
        registry = AppRegistry(self._db, self._platform_id)
        app_ids: dict[str, int] = {}
        visit = _VisitContext()
        batch: list[UsageSession] = []

        def flush() -> None:
            nonlocal batch
            if batch:
                rollup = self._writer.build_rollup(list(batch))
                contributions.add_rollup(rollup)
            batch = []

        rows = conn.execute(
            "SELECT id, app_name, process_name, exe_path, window_title,"
            " start_time, end_time, duration_seconds, date"
            " FROM app_usage ORDER BY id"
        ).fetchall()
        for index, row in enumerate(rows):
            next_row = rows[index + 1] if index + 1 < len(rows) else None
            try:
                start_ns = _ts_ns(row["start_time"])
                end_ns = _ts_ns(row["end_time"])
            except ValueError:
                continue
            if end_ns <= start_ns:
                continue
            if row["date"] not in day_set:
                continue
            process_name = row["process_name"] or ""
            app_id = app_ids.get(process_name)
            if app_id is None:
                app_id = registry.resolve(
                    AppIdentity(
                        app_key=process_name.casefold(),
                        identity_kind="process",
                        display_name=row["app_name"] or process_name,
                        process_name=process_name,
                        exe_path=row["exe_path"] or "",
                    ),
                    now=self._clock.now(),
                )
                app_ids[process_name] = app_id
            session, visit = _build_session(row, app_id, visit, next_row)
            batch.append(session)
            if len(batch) >= SESSION_BATCH:
                flush()
        flush()

    def _rebuild_day(
        self, conn: sqlite3.Connection, day: str, contributions: _Contributions
    ) -> None:
        """删除该日全部聚合格并从剩余原始数据重建，再补回无支撑量。

        重建只写**日粒度**的七张表——不能走 ``writer.persist``：它会顺带
        INSERT ``usage_session``（重读的会话被二次插入）并把 ``agg_key_total``
        等全期表再累加一遍。全期表由 :meth:`_rebuild_derived` 在最后整表重建。
        """
        day_tables = (
            ("agg_key_day", "bucket"),
            ("agg_key_hour", "day_bucket"),
            ("agg_press_hour", "day_bucket"),
            ("agg_press_minute", "day_bucket"),
            ("agg_key_app_day", "day_bucket"),
            ("agg_app_day", "day_bucket"),
            ("agg_app_hour", "day_bucket"),
        )
        before = _snapshot_day(conn, day_tables, day)

        for table, column in day_tables:
            conn.execute(f"DELETE FROM {table} WHERE {column} = ?", (day,))

        start_ns, end_ns = _day_bounds_ns(day, self._tz)
        events = self._read_events_between(conn, day, start_ns, end_ns)
        sessions = self._read_sessions_covering(conn, day, start_ns)
        batch: list[Any] = [*events, *sessions]
        if batch:
            self._persist_day_rollup(conn, self._writer.build_rollup(batch))

        after = _snapshot_day(conn, day_tables, day)

        # 补差：撤销前 − 重建后 − 导入贡献 = 无支撑量（如 store_raw 关闭期间的
        # 新采集），加回。加回量恒非负（四项是同一批聚合的分解）。
        # MAX 类列（duration_max / longest_visit）不可逆，取 max(撤销前, 重建后)：
        # store_raw 关闭期的真实极值只存在于撤销前的值里，取小了会把真数据抹成 0；
        # 取大的代价是"若导入事件恰好是全局最长按压，撤销后该值虚高"——展示性
        # 字段的保守误差，好过丢失。
        for table, _column in day_tables:
            legacy = contributions.for_table(table, day)
            delta_columns = _DELTA_COLUMNS[table]
            delta_rows: list[tuple] = []
            for key, values in before[table].items():
                rebuilt = after[table].get(key, [0.0] * len(values))
                legacy_values = legacy.get(key, [0.0] * len(values))
                row_delta: list[float] = []
                changed = False
                for index, current in enumerate(values):
                    if index in delta_columns:
                        value = current - rebuilt[index] - legacy_values[index]
                        # 浮点容差：导入与重算的累加顺序不同会让"数学上为零"
                        # 的差带上 1e-10 量级的尾数——把它写回去等于往聚合表里
                        # 注入一个永恒的负零格（真实库验证抓到过）。
                        if abs(value) < _DELTA_EPSILON:
                            value = 0.0
                        changed = changed or value != 0
                        row_delta.append(value)
                    else:
                        # MAX 类列：见上面的注释——不丢失优先于不虚高。
                        row_delta.append(
                            max(current, rebuilt[index] if key in after[table] else 0.0)
                        )
                if changed:
                    delta_rows.append((*key, *row_delta))
            if delta_rows:
                conn.executemany(_UPSERT_FOR[table], delta_rows)

    def _persist_day_rollup(self, conn: sqlite3.Connection, rollup: Any) -> None:
        """把 rollup 里的日粒度聚合写进七张日表（撤销重建专用）。

        与 ``writer.persist`` 的区别：不写原始行、不写会话（它们本来就在库里，
        只是被读回来重算）、不碰全期表（由整表重建负责）、不 bump
        ``data_version``（撤销末尾统一做一次）。
        """
        _exec = conn.executemany
        if rollup.key_day:
            _exec(_UPSERT_FOR["agg_key_day"],
                  [(*key, *values) for key, values in rollup.key_day.items()])
        if rollup.key_hour:
            _exec(_UPSERT_FOR["agg_key_hour"],
                  [(*key, *values) for key, values in rollup.key_hour.items()])
        if rollup.press_hour:
            _exec(_UPSERT_FOR["agg_press_hour"],
                  [(*key, *values) for key, values in rollup.press_hour.items()])
        if rollup.press_minute:
            _exec(_UPSERT_FOR["agg_press_minute"],
                  [(*key, count) for key, count in rollup.press_minute.items()])
        if rollup.key_app_day:
            _exec(_UPSERT_FOR["agg_key_app_day"],
                  [(*key, *values) for key, values in rollup.key_app_day.items()])
        if rollup.app_day:
            _exec(_UPSERT_FOR["agg_app_day"],
                  [(*key, *values) for key, values in rollup.app_day.items()])
        if rollup.app_hour:
            _exec(_UPSERT_FOR["agg_app_hour"],
                  [(*key, value) for key, value in rollup.app_hour.items()])

    def _read_events_between(
        self, conn: sqlite3.Connection, day: str, start_ns: int, end_ns: int
    ) -> list[KeyEvent]:
        table = raw_table(day[:7])
        if not self._db.table_exists(table):
            return []
        rows = conn.execute(
            f"SELECT key_id, app_id, down_ts_ns, up_ts_ns, duration_ms,"
            f" native_code, native_code2, hid_usage, confidence FROM {table}"
            " WHERE down_ts_ns >= ? AND down_ts_ns < ?",
            (start_ns, end_ns),
        ).fetchall()
        names = {0: "unknown", 1: "boundary", 2: "high"}
        return [
            KeyEvent(
                key_id=row["key_id"],
                down_ts_ns=row["down_ts_ns"],
                up_ts_ns=row["up_ts_ns"],
                duration_ms=row["duration_ms"],
                app_id=row["app_id"],
                confidence=names.get(row["confidence"], "unknown"),  # type: ignore[arg-type]
                native_code=row["native_code"],
                native_code2=row["native_code2"],
                hid_usage=row["hid_usage"],
            )
            for row in rows
        ]

    def _read_sessions_covering(
        self, conn: sqlite3.Connection, day: str, day_start_ns: int
    ) -> list[UsageSession]:
        """覆盖该日的会话段。``day_bucket`` 是起始日，向前看两天足够——
        心跳落盘让单段最长十几秒，不存在跨三天的段。"""
        since = (datetime.fromisoformat(day) - timedelta(days=2)).strftime("%Y-%m-%d")
        rows = conn.execute(
            "SELECT app_id, window_title, start_ts_ns, end_ts_ns, duration_ms,"
            " day_bucket, idle_trimmed, end_reason, visit_start_ts_ns"
            " FROM usage_session"
            " WHERE day_bucket BETWEEN ? AND ? AND end_ts_ns > ?",
            (since, day, day_start_ns),
        ).fetchall()
        return [
            UsageSession(
                app_id=row["app_id"],
                start_ts_ns=row["start_ts_ns"],
                end_ts_ns=row["end_ts_ns"],
                duration_ms=row["duration_ms"],
                window_title=row["window_title"],
                idle_trimmed=bool(row["idle_trimmed"]),
                end_reason=row["end_reason"],  # type: ignore[arg-type]
                visit_start_ts_ns=row["visit_start_ts_ns"],
            )
            for row in rows
        ]

    def _rebuild_derived(
        self, conn: sqlite3.Connection, contributions: _Contributions
    ) -> None:
        """月/年/总计表从（已重算的）日表整表重建；``agg_app_key_total``
        从全部原始月表重建并补差。日表已含补回的无支撑量，因此派生表直接
        替换即正确——无需逐表再补差。

        ``agg_app_*`` 的重建带 ``HAVING``：增量写入路径只让**会话**建
        (周期, 应用) 行（按键只动 ``press_count`` 槽），无会话的 (日, 应用)
        因此没有月/年/总计行。不加过滤的话，重建会给"只有按键没有前台"的
        组合建出一堆 ``duration = 0`` 的行——它们在增量库里的等价物不存在。
        """
        conn.execute("DELETE FROM agg_key_month")
        conn.execute(
            "INSERT INTO agg_key_month (bucket, key_id, press_count,"
            " duration_total_ms, duration_max_ms)"
            " SELECT substr(bucket, 1, 7), key_id, SUM(press_count),"
            " SUM(duration_total_ms), MAX(duration_max_ms)"
            " FROM agg_key_day GROUP BY substr(bucket, 1, 7), key_id"
        )
        conn.execute("DELETE FROM agg_key_year")
        conn.execute(
            "INSERT INTO agg_key_year (bucket, key_id, press_count,"
            " duration_total_ms, duration_max_ms)"
            " SELECT substr(bucket, 1, 4), key_id, SUM(press_count),"
            " SUM(duration_total_ms), MAX(duration_max_ms)"
            " FROM agg_key_day GROUP BY substr(bucket, 1, 4), key_id"
        )
        conn.execute("DELETE FROM agg_key_total")
        conn.execute(
            "INSERT INTO agg_key_total (key_id, press_count, duration_total_ms,"
            " duration_max_ms)"
            " SELECT key_id, SUM(press_count), SUM(duration_total_ms),"
            " MAX(duration_max_ms) FROM agg_key_day GROUP BY key_id"
        )
        conn.execute("DELETE FROM agg_app_month")
        conn.execute(
            "INSERT INTO agg_app_month (month_bucket, app_id, duration_ms, session_count)"
            " SELECT substr(day_bucket, 1, 7), app_id, SUM(duration_ms),"
            " SUM(session_count) FROM agg_app_day"
            " GROUP BY substr(day_bucket, 1, 7), app_id"
            " HAVING SUM(duration_ms) > 0 OR SUM(session_count) > 0"
        )
        conn.execute("DELETE FROM agg_app_year")
        conn.execute(
            "INSERT INTO agg_app_year (year_bucket, app_id, duration_ms, session_count)"
            " SELECT substr(day_bucket, 1, 4), app_id, SUM(duration_ms),"
            " SUM(session_count) FROM agg_app_day"
            " GROUP BY substr(day_bucket, 1, 4), app_id"
            " HAVING SUM(duration_ms) > 0 OR SUM(session_count) > 0"
        )
        conn.execute("DELETE FROM agg_app_total")
        conn.execute(
            "INSERT INTO agg_app_total (app_id, duration_ms, session_count, last_used_ts_ns)"
            " SELECT d.app_id, SUM(d.duration_ms), SUM(d.session_count),"
            " COALESCE((SELECT MAX(s.end_ts_ns) FROM usage_session s"
            "           WHERE s.app_id = d.app_id), 0)"
            " FROM agg_app_day d GROUP BY d.app_id"
            " HAVING SUM(d.duration_ms) > 0 OR SUM(d.session_count) > 0"
        )

        # agg_app_key_total：唯一的例外——它从原始月表重建，而 store_raw 关闭
        # 期间的新采集没有原始行，用与按天重建相同的补差公式保住它们。
        before = {
            (row[0], row[1]): [row[2], row[3], row[4]]
            for row in conn.execute(
                "SELECT app_id, key_id, press_count, duration_total_ms,"
                " duration_max_ms FROM agg_app_key_total"
            )
        }
        conn.execute("DELETE FROM agg_app_key_total")
        for month in Partitions.existing_months(conn):
            table = raw_table(month)
            conn.execute(
                f"INSERT INTO agg_app_key_total (app_id, key_id, press_count,"
                f" duration_total_ms, duration_max_ms)"
                f" SELECT app_id, key_id, COUNT(*), SUM(duration_ms), MAX(duration_ms)"
                f" FROM {table} GROUP BY app_id, key_id"
                " ON CONFLICT(app_id, key_id) DO UPDATE SET"
                " press_count = press_count + excluded.press_count,"
                " duration_total_ms = duration_total_ms + excluded.duration_total_ms,"
                " duration_max_ms = MAX(duration_max_ms, excluded.duration_max_ms)"
            )
        after = {
            (row[0], row[1]): [row[2], row[3], row[4]]
            for row in conn.execute(
                "SELECT app_id, key_id, press_count, duration_total_ms,"
                " duration_max_ms FROM agg_app_key_total"
            )
        }
        restore: list[tuple] = []
        for key, values in before.items():
            rebuilt = after.get(key, [0, 0.0, 0.0])
            legacy = contributions.app_key_total.get(key, [0, 0.0, 0.0])
            delta = [
                values[0] - rebuilt[0] - legacy[0],
                values[1] - rebuilt[1] - legacy[1],
            ]
            if delta[0] or delta[1]:
                restore.append((*key, delta[0], delta[1], values[2]))
        if restore:
            conn.executemany(
                """
                INSERT INTO agg_app_key_total (app_id, key_id, press_count,
                 duration_total_ms, duration_max_ms) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(app_id, key_id) DO UPDATE SET
                 press_count = press_count + excluded.press_count,
                 duration_total_ms = duration_total_ms + excluded.duration_total_ms,
                 duration_max_ms = MAX(duration_max_ms, excluded.duration_max_ms)
                """,
                restore,
            )


# ── 辅助：访问推断、快照重算贡献、按天重建的簿记 ────────────────────────


class _VisitContext:
    """跨批次延续的访问推断状态（TimeLens 心跳段 → 一次访问）。"""

    __slots__ = ("app_id", "last_end_ns", "visit_start_ns")

    def __init__(self, app_id: int = -1, last_end_ns: int = 0, visit_start_ns: int = 0):
        self.app_id = app_id
        self.last_end_ns = last_end_ns
        self.visit_start_ns = visit_start_ns

    def as_dict(self) -> dict[str, int]:
        return {
            "app_id": self.app_id,
            "last_end_ns": self.last_end_ns,
            "visit_start_ns": self.visit_start_ns,
        }

    @classmethod
    def from_dict(cls, data: dict[str, int] | None) -> _VisitContext:
        if not data:
            return cls()
        return cls(
            data.get("app_id", -1),
            data.get("last_end_ns", 0),
            data.get("visit_start_ns", 0),
        )


class _PendingRow:
    """从 state 序列化字段还原的"上一批最后一行"。鸭子类型兼容 ``sqlite3.Row``。"""

    _FIELDS = (
        "id",
        "app_name",
        "process_name",
        "exe_path",
        "window_title",
        "start_time",
        "end_time",
        "duration_seconds",
        "date",
    )

    def __init__(self, values: list[Any]):
        self._values = values

    def __getitem__(self, key: str) -> Any:
        return self._values[self._FIELDS.index(key)]


def _serialize_row(row: sqlite3.Row) -> list[Any]:
    return [row[name] for name in _PendingRow._FIELDS]


def _build_session(
    row: Any,
    app_id: int,
    visit: _VisitContext,
    next_row: Any | None,
) -> tuple[UsageSession, _VisitContext]:
    """一行 ``app_usage`` → ``UsageSession``，并更新访问上下文。

    ``end_reason`` 由**下一行**决定（lookahead）：延续段是 ``heartbeat``，
    否则是 ``switch``——一次访问因此恰有一行 ``end_reason <> 'heartbeat'``，
    与 M2 偏离 41 的访问口径完全一致。``visit_start`` 沿用或重开。
    """
    start_ns = _ts_ns(row["start_time"])
    end_ns = _ts_ns(row["end_time"])
    continues_from_prev = (
        visit.app_id == app_id
        and visit.last_end_ns
        and 0 <= start_ns - visit.last_end_ns <= HEARTBEAT_GAP_NS
    )
    visit_start = visit.visit_start_ns if continues_from_prev else start_ns
    continues_to_next = False
    if next_row is not None:
        try:
            next_start = _ts_ns(next_row["start_time"])
            continues_to_next = (
                0 <= next_start - end_ns <= HEARTBEAT_GAP_NS
                and (next_row["process_name"] or "").casefold()
                == (row["process_name"] or "").casefold()
            )
        except ValueError:
            continues_to_next = False
    session = UsageSession(
        app_id=app_id,
        start_ts_ns=start_ns,
        end_ts_ns=end_ns,
        duration_ms=round(row["duration_seconds"] * 1000),
        window_title=row["window_title"] or "",
        idle_trimmed=False,
        end_reason="heartbeat" if continues_to_next else "switch",
        visit_start_ts_ns=0 if visit_start == start_ns else visit_start,
    )
    return session, _VisitContext(app_id, end_ns, visit_start)


def _apply_key_usage_delta(
    conn: sqlite3.Connection,
    key_day: dict[tuple[str, str], int],
    key_hour: dict[tuple[str, int, str], int],
    press_hour: dict[tuple[str, int], int],
) -> None:
    """TimeLens ``key_usage`` 只进聚合，不生成原始事件（03 文档 §7.3）。

    时长维度留 0；应用维度不进任何表。月/年/总计在日贡献的基础上同步派生，
    与写线程的增量口径相同。
    """
    if key_day:
        conn.executemany(
            AGG_KEY_DAY_UPSERT,
            [(day, key_id, count, 0.0, 0.0) for (day, key_id), count in key_day.items()],
        )
        months: dict[tuple[str, str], int] = {}
        years: dict[tuple[str, str], int] = {}
        totals: dict[str, int] = {}
        for (day, key_id), count in key_day.items():
            months[(day[:7], key_id)] = months.get((day[:7], key_id), 0) + count
            years[(day[:4], key_id)] = years.get((day[:4], key_id), 0) + count
            totals[key_id] = totals.get(key_id, 0) + count
        conn.executemany(
            AGG_KEY_MONTH_UPSERT,
            [(month, key_id, count, 0.0, 0.0) for (month, key_id), count in months.items()],
        )
        conn.executemany(
            AGG_KEY_YEAR_UPSERT,
            [(year, key_id, count, 0.0, 0.0) for (year, key_id), count in years.items()],
        )
        conn.executemany(
            AGG_KEY_TOTAL_UPSERT,
            [(key_id, count, 0.0, 0.0) for key_id, count in totals.items()],
        )
    if key_hour:
        conn.executemany(
            AGG_KEY_HOUR_UPSERT,
            [
                (day, hour, key_id, count, 0.0)
                for (day, hour, key_id), count in key_hour.items()
            ],
        )
    if press_hour:
        conn.executemany(
            AGG_PRESS_HOUR_UPSERT,
            [(day, hour, count, 0.0) for (day, hour), count in press_hour.items()],
        )


class _Contributions:
    """导入当年写进各聚合表的量（从快照重算）。撤销补差公式的减项。

    值列表的长度**必须等于对应表的值列数**——补差按位置相减，长度不齐会
    静默算错（或越界）。``[count, total, max]`` 三元在 ``add_rollup`` 里
    按列语义合并：计数累加、总量累加、极值取大。
    """

    def __init__(self) -> None:
        self.key_day: dict[tuple[str, str], list[float]] = {}
        self.key_hour: dict[tuple[str, int, str], list[float]] = {}
        self.press_hour: dict[tuple[str, int], list[float]] = {}
        self.press_minute: dict[tuple[str, int], list[float]] = {}
        self.key_app_day: dict[tuple[str, int, str], list[float]] = {}
        self.app_key_total: dict[tuple[int, str], list[float]] = {}
        #: 会话导入对 ``agg_app_day`` 的贡献（值列序同表：duration, session,
        #: longest, press——会话只动前两列）。
        self.app_day_sessions: dict[tuple[str, int], list[float]] = {}
        #: 按键导入对 ``agg_app_day`` press_count 槽的贡献。
        self.app_day_presses: dict[tuple[str, int], int] = {}
        #: 会话导入对 ``agg_app_hour`` 的贡献（duration）。
        self.app_hour: dict[tuple[str, int, int], float] = {}

    @staticmethod
    def _merge(slot: list[float] | None, values: list) -> list[float]:
        if slot is None:
            return [float(value) for value in values]
        for index in range(min(len(slot), len(values))):
            slot[index] += float(values[index]) if index < 2 else max(
                slot[index], float(values[index])
            )
        return slot

    def add_rollup(self, rollup: Any) -> None:
        for key, values in rollup.key_day.items():
            self.key_day[key] = self._merge(self.key_day.get(key), values)
        for key, values in rollup.key_hour.items():
            self.key_hour[key] = self._merge(self.key_hour.get(key), values)
        for key, values in rollup.press_hour.items():
            self.press_hour[key] = self._merge(self.press_hour.get(key), values)
        for key, count in rollup.press_minute.items():
            self.press_minute[key] = self._merge(
                self.press_minute.get(key), [count]
            )
        for key, values in rollup.key_app_day.items():
            self.key_app_day[key] = self._merge(self.key_app_day.get(key), values)
        for key, values in rollup.app_key_total.items():
            self.app_key_total[key] = self._merge(self.app_key_total.get(key), values)
        for (day, app_id), slot in rollup.app_day.items():
            press_slot = self.app_day_presses.get((day, app_id), 0)
            self.app_day_presses[(day, app_id)] = press_slot + slot[3]
            session_slot = self.app_day_sessions.get((day, app_id))
            if session_slot is None:
                self.app_day_sessions[(day, app_id)] = [float(slot[0]), float(slot[1])]
            else:
                session_slot[0] += float(slot[0])
                session_slot[1] += float(slot[1])
        for key, duration in rollup.app_hour.items():
            self.app_hour[key] = self.app_hour.get(key, 0.0) + duration

    def for_table(self, table: str, day: str) -> dict[tuple, list[float]]:
        if table == "agg_key_day":
            return {key: values for key, values in self.key_day.items() if key[0] == day}
        if table == "agg_key_hour":
            return {key: values for key, values in self.key_hour.items() if key[0] == day}
        if table == "agg_press_hour":
            return {key: values for key, values in self.press_hour.items() if key[0] == day}
        if table == "agg_press_minute":
            return {
                key: values for key, values in self.press_minute.items() if key[0] == day
            }
        if table == "agg_key_app_day":
            return {
                key: values for key, values in self.key_app_day.items() if key[0] == day
            }
        if table == "agg_app_day":
            merged: dict[tuple, list[float]] = {}
            for key, (duration, sessions) in self.app_day_sessions.items():
                if key[0] == day:
                    merged[(key[0], key[1])] = [duration, sessions, 0.0, 0.0]
            for key, press in self.app_day_presses.items():
                if key[0] != day:
                    continue
                slot = merged.setdefault((key[0], key[1]), [0.0, 0.0, 0.0, 0.0])
                slot[3] += press
            return merged
        if table == "agg_app_hour":
            return {
                (key[0], key[1], key[2]): [value]
                for key, value in self.app_hour.items()
                if key[0] == day
            }
        return {}


def _extend_unique(target: list[str], additions: set[str]) -> None:
    known = set(target)
    for item in additions:
        if item not in known:
            target.append(item)
            known.add(item)


#: 按天重建里，每张表**参与补差**的数值列索引（值列 = 全部列去掉主键后的顺序）。
#: 其余列是 MAX 类（duration_max / longest_visit），不可逆也不补。
_DELTA_COLUMNS = {
    "agg_key_day": (0, 1),  # press_count, duration_total_ms
    "agg_key_hour": (0, 1),
    "agg_press_hour": (0, 1),
    "agg_press_minute": (0,),
    "agg_key_app_day": (0, 1),
    "agg_app_day": (0, 1, 3),  # duration_ms, session_count, press_count（2 号位是 longest）
    "agg_app_hour": (0,),
}

_UPSERT_FOR = {
    "agg_key_day": AGG_KEY_DAY_UPSERT,
    "agg_key_hour": AGG_KEY_HOUR_UPSERT,
    "agg_press_hour": AGG_PRESS_HOUR_UPSERT,
    "agg_press_minute": """
        INSERT INTO agg_press_minute (day_bucket, minute, press_count) VALUES (?, ?, ?)
        ON CONFLICT(day_bucket, minute) DO UPDATE SET
            press_count = agg_press_minute.press_count + excluded.press_count
    """,
    "agg_key_app_day": """
        INSERT INTO agg_key_app_day (day_bucket, app_id, key_id, press_count,
         duration_total_ms, duration_max_ms) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(day_bucket, app_id, key_id) DO UPDATE SET
            press_count = agg_key_app_day.press_count + excluded.press_count,
            duration_total_ms = agg_key_app_day.duration_total_ms + excluded.duration_total_ms,
            duration_max_ms = MAX(agg_key_app_day.duration_max_ms, excluded.duration_max_ms)
    """,
    "agg_app_day": """
        INSERT INTO agg_app_day (day_bucket, app_id, duration_ms, session_count,
         longest_visit_ms, press_count) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(day_bucket, app_id) DO UPDATE SET
            duration_ms = agg_app_day.duration_ms + excluded.duration_ms,
            session_count = agg_app_day.session_count + excluded.session_count,
            longest_visit_ms = MAX(agg_app_day.longest_visit_ms, excluded.longest_visit_ms),
            press_count = agg_app_day.press_count + excluded.press_count
    """,
    "agg_app_hour": """
        INSERT INTO agg_app_hour (day_bucket, hour, app_id, duration_ms)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(day_bucket, hour, app_id) DO UPDATE SET
            duration_ms = agg_app_hour.duration_ms + excluded.duration_ms
    """,
}

#: 补差的浮点容差（毫秒级数据的累加顺序差异远小于它）。
_DELTA_EPSILON = 1e-6

#: 每张按天聚合表的主键列数（其余列是数值列）。
_KEY_LEN = {
    "agg_key_day": 2,
    "agg_key_hour": 3,
    "agg_press_hour": 2,
    "agg_press_minute": 2,
    "agg_key_app_day": 3,
    "agg_app_day": 2,
    "agg_app_hour": 3,
}


def _snapshot_day(
    conn: sqlite3.Connection, day_tables: tuple, day: str
) -> dict[str, dict[tuple, list[float]]]:
    """该日各聚合表的当前值快照（主键元组 → 数值列）。"""
    snapshot: dict[str, dict[tuple, list[float]]] = {}
    for table, column in day_tables:
        key_len = _KEY_LEN[table]
        rows = conn.execute(f"SELECT * FROM {table} WHERE {column} = ?", (day,)).fetchall()
        snapshot[table] = {
            tuple(row[:key_len]): [float(value) for value in row[key_len:]]
            for row in rows
        }
    return snapshot


__all__ = [
    "AMBIGUOUS_DISPLAY_NAMES",
    "HEARTBEAT_GAP_SECONDS",
    "KEY_NAME_MAP",
    "KNOWN_KEY_IDS",
    "STATE_KEY",
    "ImportCancelled",
    "LegacyImportError",
    "LegacyImporter",
    "classify_legacy_database",
    "connect_readonly",
    "detect_legacy",
    "load_state",
    "map_key_name",
    "scan_keytrace",
    "scan_timelens",
    "snapshot_legacy",
    "up",
]
