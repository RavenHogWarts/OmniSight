"""旧数据导入服务（09 文档 §2 的后端半边）。

导入器本体在 :mod:`omnisight.storage.migrations.m003_import_legacy`（存储层，
离 SQL 最近）。本模块负责它外面的所有事：

* **发现**——默认路径探测，交给向导步骤 1 展示；
* **预览**——只读扫描 + 损失说明（向导步骤 2 的数据源）；
* **执行**——后台线程驱动导入器，暂停/续传，进度可查询；
* **报告**——``data/import-report.json`` 与人类可读摘要；
* **广播**——导入或撤销完成后发 ``write_flushed``，前端经既有的 ``invalidate``
  链路自动刷新，不需要新事件类型。

导入在独立线程上以批次执行，与写线程通过 ``BEGIN IMMEDIATE`` + 进程内写锁
交错串行——采集线程只往队列放事件，从不直接写库，因此**导入不阻塞采集**
（09 文档 §2.3）。
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, tzinfo
from pathlib import Path
from typing import Any

from ..core import paths
from ..core.bus import EventBus
from ..storage.database import Database
from ..storage.migrations.m003_import_legacy import (
    ImportCancelled,
    LegacyImporter,
    LegacyImportError,
    classify_legacy_database,
    connect_readonly,
    detect_legacy,
    load_state,
    scan_keytrace,
    scan_timelens,
)
from ..storage.writer import TOPIC_WRITE_FLUSHED

logger = logging.getLogger(__name__)

#: Deprecation 头与 Sunset 的口径见 09 文档 §4.2：兼容层保留一个大版本。
SUNSET_DATE = "2027-09-01"


class LegacyService:
    """导入向导的后端。线程安全：同一时刻至多一个导入/撤销任务在跑。"""

    def __init__(
        self,
        db: Database,
        *,
        data_dir: Path,
        tz: tzinfo | None = None,
        store_raw: bool = True,
        platform_id: str = "windows",
        bus: EventBus | None = None,
    ) -> None:
        self._db = db
        self._data_dir = Path(data_dir)
        self._tz = tz
        self._store_raw = store_raw
        self._platform_id = platform_id
        self._bus = bus
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._cancel = threading.Event()
        self._task: str | None = None  # "import" | "undo"
        self._error: str | None = None

    # ── 发现与预览（向导步骤 1/2）───────────────────────────────────────

    def detect(self) -> list[dict[str, Any]]:
        """默认搜索路径下的旧库。检测失败不影响启动（09 文档 §2.1）。"""
        try:
            return detect_legacy(paths.exe_dir())
        except Exception:  # pragma: no cover - 探测是纯读，防御性兜底
            logger.debug("旧库探测失败", exc_info=True)
            return []

    def preview(self, sources: dict[str, str | Path | None]) -> dict[str, Any]:
        """只读扫描，产出向导步骤 2 的"将导入什么 / 会丢什么"。

        ``sources``: ``{"timelens": 路径|None, "keytrace": 路径|None}``。
        类型不匹配的文件直接报错——导入器拒绝猜。
        """
        resolved: dict[str, Path | None] = {}
        for name in ("timelens", "keytrace"):
            value = sources.get(name)
            if value in (None, ""):
                resolved[name] = None
                continue
            path = Path(str(value)).expanduser()
            if not path.is_file():
                raise LegacyImportError(f"文件不存在：{path}")
            kind = classify_legacy_database(path)
            if kind != name:
                raise LegacyImportError(
                    f"{path} 不是{' TimeLens' if name == 'timelens' else ' KeyTrace'}"
                    f"的数据库（识别为 {kind or '未知格式'}）"
                )
            resolved[name] = path

        result: dict[str, Any] = {
            "sources": {k: str(v) if v else None for k, v in resolved.items()}
        }
        kt_days: set[str] = set()
        if resolved["keytrace"] is not None:
            conn = connect_readonly(resolved["keytrace"])
            try:
                kt = scan_keytrace(conn)
            finally:
                conn.close()
            kt_days = set(kt["key_days"])
            result["keytrace"] = kt

        tl_key_days: set[str] = set()
        if resolved["timelens"] is not None:
            conn = connect_readonly(resolved["timelens"])
            try:
                result["timelens"] = scan_timelens(conn)
                tl_key_days = set(
                    row[0]
                    for row in conn.execute("SELECT DISTINCT date FROM key_usage")
                )
            finally:
                conn.close()

        conflicts = sorted(tl_key_days & kt_days)
        result["conflict_days"] = conflicts
        result["losses"] = _losses(result, conflicts)
        return result

    # ── 执行（向导步骤 3/4）─────────────────────────────────────────────

    def start(
        self, sources: dict[str, str | Path | None], *, losses: list[str] | None = None
    ) -> dict[str, Any]:
        """启动（或续传）后台导入。已在跑时返回当前状态而不报错。

        ``losses`` 来自 :meth:`preview` 的损失说明，随状态持久化——完成页与
        报告文件展示的必须是用户在步骤 2 确认过的那一份。
        """
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return self.status()
            state = load_state(self._db)
            if state is not None and state.get("status") == "done":
                raise LegacyImportError("历史数据已导入；如需重新导入，请先撤销")
            if state is not None and state.get("status") == "undone":
                state = None  # 撤销过：从头开始一次新的导入
            state = state or {}
            state.setdefault("losses", losses or [])

            resolved: dict[str, Path | None] = {}
            for name in ("timelens", "keytrace"):
                value = sources.get(name)
                resolved[name] = Path(str(value)).expanduser() if value else None
            if resolved["timelens"] is None and resolved["keytrace"] is None:
                raise LegacyImportError("至少要选择一个旧数据库")
            # 续传时沿用第一次的快照与来源，忽略本次传入的差异——否则两次选择
            # 不同的文件会产生两份叠加的数据。
            if state.get("sources"):
                resolved = {
                    name: (Path(value) if value else None)
                    for name, value in state["sources"].items()
                }

            stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
            backup_dir = self._data_dir / "backup" / f"import-{stamp}"
            backup_dir.mkdir(parents=True, exist_ok=True)
            # 新库自身的快照：撤销是删除性操作，这是最后保险。在线 backup
            # 无需停机（03 文档 §9）；每秒重做一次的代价由幂等判断挡掉。
            if not state.get("self_backup_done"):
                try:
                    self._db.backup_to(backup_dir / "omnisight.db")
                    state["self_backup_done"] = True
                except Exception:  # pragma: no cover - 备份失败不阻止导入
                    logger.warning("导入前备份新库失败", exc_info=True)
            self._cancel.clear()
            self._error = None
            self._task = "import"
            # 先把"导入中"落库再启动线程：否则 start() 的响应与紧随其后的
            # progress 轮询可能在线程写下第一笔状态之前读到 idle，前端会
            # 误判为"没启动"。导入器自身的 _init_state 是幂等的 setdefault，
            # 重复执行无害。
            state["status"] = "importing"
            with self._db.transaction() as conn:
                self._db.meta_set(
                    "legacy_import", json.dumps(state, ensure_ascii=False), conn=conn
                )
            self._thread = threading.Thread(
                target=self._run_import,
                args=(state, resolved, backup_dir),
                name="legacy-import",
                daemon=True,
            )
            self._thread.start()
        return self.status()

    def cancel(self) -> dict[str, Any]:
        """暂停。游标已保存，再次 :meth:`start` 即续传。"""
        self._cancel.set()
        return self.status()

    def undo(self) -> dict[str, Any]:
        """撤销导入（09 文档 §2.5）。同样在后台线程执行。"""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                raise LegacyImportError("有任务正在进行，无法撤销")
            state = load_state(self._db)
            if state is None:
                raise LegacyImportError("还没有导入过历史数据")
            if state.get("status") == "undone":
                raise LegacyImportError("导入已经撤销过了")
            self._cancel.clear()
            self._error = None
            self._task = "undo"
            self._thread = threading.Thread(
                target=self._run_undo, args=(state,), name="legacy-undo", daemon=True
            )
            self._thread.start()
        return self.status()

    def status(self) -> dict[str, Any]:
        """向导与横幅的唯一状态来源。"""
        state = load_state(self._db)
        busy = self._thread is not None and self._thread.is_alive()
        payload: dict[str, Any] = {
            "state": "idle",
            "busy": busy,
            "task": self._task if busy else None,
            "error": self._error,
        }
        if state is None:
            payload["available"] = bool(self.detect())
            return payload
        payload["state"] = state.get("status", "idle")
        payload["phase"] = state.get("phase")
        payload["counts"] = state.get("counts", {})
        payload["skipped_days"] = state.get("skipped_days", [])
        payload["sources"] = state.get("sources", {})
        payload["backup_dir"] = state.get("backup_dir")
        if state.get("status") == "done" and busy is False:
            payload["report"] = self._read_report()
        return payload

    # ── 报告 ─────────────────────────────────────────────────────────────

    def report(self) -> dict[str, Any] | None:
        """完整导入报告（已完成时）。"""
        state = load_state(self._db)
        if state is None or state.get("status") != "done":
            return None
        return self._read_report()

    def _report_path(self, suffix: str) -> Path:
        return self._data_dir / f"import-report.{suffix}"

    def _read_report(self) -> dict[str, Any] | None:
        path = self._report_path("json")
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            logger.exception("导入报告读取失败")
            return None

    def _write_report(self, state: dict[str, Any], preview_losses: list[str]) -> None:
        report = build_report(state, preview_losses)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._report_path("json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self._report_path("txt").write_text(
            render_report_text(report), encoding="utf-8"
        )

    # ── 后台线程体 ──────────────────────────────────────────────────────

    def _run_import(
        self,
        state: dict[str, Any],
        sources: dict[str, Path | None],
        backup_dir: Path,
    ) -> None:
        try:
            importer = LegacyImporter(
                self._db,
                tz=self._tz,
                store_raw=self._store_raw,
                platform_id=self._platform_id,
            )
            importer.run(
                state, sources, backup_dir, cancel_check=self._cancel.is_set
            )
        except ImportCancelled:
            with self._db.transaction() as conn:
                state["status"] = "paused"
                self._db.meta_set(
                    "legacy_import", json.dumps(state, ensure_ascii=False), conn=conn
                )
            logger.info("导入已暂停，可随时续传")
        except Exception as exc:
            self._error = str(exc) or exc.__class__.__name__
            with self._db.transaction() as conn:
                state["status"] = "failed"
                state["error"] = self._error
                self._db.meta_set(
                    "legacy_import", json.dumps(state, ensure_ascii=False), conn=conn
                )
            logger.exception("导入失败")
        else:
            try:
                self._write_report(state, state.get("losses", []))
            except Exception:  # pragma: no cover - 报告失败不影响导入结果
                logger.exception("写导入报告失败")
        finally:
            self._announce()

    def _run_undo(self, state: dict[str, Any]) -> None:
        try:
            importer = LegacyImporter(
                self._db,
                tz=self._tz,
                store_raw=self._store_raw,
                platform_id=self._platform_id,
            )
            importer.undo(state)
        except Exception as exc:
            self._error = str(exc) or exc.__class__.__name__
            logger.exception("撤销导入失败")
        finally:
            self._announce()

    def _announce(self) -> None:
        """让前端经既有的 ``invalidate`` 链路刷新（不需要新事件类型）。"""
        if self._bus is None:
            return
        try:
            self._bus.publish(TOPIC_WRITE_FLUSHED, self._db.data_version())
        except Exception:  # pragma: no cover
            logger.debug("导入完成广播失败", exc_info=True)


# ── 报告生成 ─────────────────────────────────────────────────────────────


def _losses(preview: dict[str, Any], conflicts: list[str]) -> list[str]:
    """向导步骤 2 与报告共用的损失说明（数据驱动，不夸大也不隐瞒）。"""
    losses: list[str] = []
    timelens = preview.get("timelens") or {}
    key_usage = timelens.get("key_usage") or {}
    if key_usage.get("rows"):
        losses.append(
            "TimeLens 的按键统计没有按压时长：这段时间的“平均按压 / 最长按压”"
            "将显示为空，热力图仅次数可用"
        )
        losses.append(
            "TimeLens 的按键统计没有应用归因：这段时间无法查看“某应用的键盘热力图”；"
            "从今天起记录的数据不受影响"
        )
    for name in key_usage.get("ambiguous_names", []):
        losses.append(
            f"键 “{name}” 无法区分左右（或主键盘 / 小键盘）：旧版把它们记成同一个键，"
            "将全部归到左侧（或主键盘）"
        )
    if conflicts:
        losses.append(
            f"重叠日期以 KeyTrace 为准：{len(conflicts)} 天两个旧库都在记录按键，"
            "将采用 KeyTrace 的明细，忽略 TimeLens 的当日次数"
        )
    return losses


def build_report(state: dict[str, Any], losses: list[str]) -> dict[str, Any]:
    """``data/import-report.json`` 的内容（03 文档 §7.5）。"""
    counts = state.get("counts", {})
    started = state.get("started_at")
    finished = state.get("finished_at")
    duration_seconds = None
    if started and finished:
        try:
            duration_seconds = round(
                (
                    datetime.fromisoformat(finished) - datetime.fromisoformat(started)
                ).total_seconds(),
                1,
            )
        except ValueError:  # pragma: no cover
            duration_seconds = None
    return {
        "generated_at": finished,
        "duration_seconds": duration_seconds,
        "sources": state.get("sources", {}),
        "backup_dir": state.get("backup_dir"),
        "sessions": {
            "imported": counts.get("sessions_imported", 0),
            "skipped_invalid": counts.get("sessions_skipped", 0),
            "days": counts.get("session_days", 0),
            "date_range": [
                min(state["days"]["sessions"]) if state["days"]["sessions"] else None,
                max(state["days"]["sessions"]) if state["days"]["sessions"] else None,
            ],
        },
        "key_usage": {
            "presses": counts.get("key_presses", 0),
            "days": counts.get("key_usage_days", 0),
            "duration_available": False,
            "attribution_available": False,
        },
        "raw_events": {
            "imported": counts.get("raw_imported", 0),
            "days": counts.get("raw_days", 0),
        },
        "skipped_days": state.get("skipped_days", []),
        "unmapped_keys": counts.get("unmapped_keys", {}),
        "losses": losses,
        "notes": [
            "旧 TimeLens 的时间是无时区的本地时间字符串，导入按当时的本地时区解释",
            "TimeLens 每 10 秒落一段心跳，访问边界按 15 秒间隙重建（非猜测，见模块文档）",
        ],
    }


def render_report_text(report: dict[str, Any]) -> str:
    """人类可读摘要（向导步骤 4 与 ``data/import-report.txt``）。"""
    sessions = report.get("sessions", {})
    key_usage = report.get("key_usage", {})
    raw_events = report.get("raw_events", {})
    lines = [
        "OmniSight 历史数据导入报告",
        f"完成时间：{report.get('generated_at') or '未知'}",
        f"用时：{report.get('duration_seconds', 0)} 秒",
        "",
        f"应用使用记录   {sessions.get('imported', 0)} 条   "
        f"{sessions.get('days', 0)} 天",
        f"按键明细       {raw_events.get('imported', 0)} 条   "
        f"{raw_events.get('days', 0)} 天",
        f"按键次数       {key_usage.get('presses', 0)} 次（无时长、无归因）   "
        f"{key_usage.get('days', 0)} 天",
        f"跳过（重叠日） {len(report.get('skipped_days', []))} 天",
    ]
    unmapped = report.get("unmapped_keys") or {}
    if unmapped:
        lines.append(f"未能映射的键   {len(unmapped)} 个：" + "、".join(unmapped))
    losses = report.get("losses") or []
    if losses:
        lines += ["", "有损说明："]
        lines += [f"  ⚠ {loss}" for loss in losses]
    lines += ["", f"完整报告：{report.get('backup_dir') or 'data/'}",
              "旧数据文件未被修改，可随时退回旧程序。"]
    return "\n".join(lines)


__all__ = ["SUNSET_DATE", "LegacyService", "build_report", "render_report_text"]
