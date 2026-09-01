"""SQLite 连接、PRAGMA、事务与 ``meta`` 访问。

三个设计决策：

* **每线程一个连接。** WAL 下多读一写是 SQLite 的强项，但 ``sqlite3.Connection``
  不宜跨线程共享。用 ``threading.local`` 而不是 ``check_same_thread=False``——
  后者只是关掉了检查，并没有让连接变安全。
* **写事务一律 ``BEGIN IMMEDIATE``。** 默认的延迟事务会在升级为写锁时才发现冲突，
  此时已经执行了一部分语句，回滚代价与出错位置都更难预料。
* **``auto_vacuum`` 只能在建库时定。** 它无法在已有数据的库上靠 PRAGMA 改（要
  整库 VACUUM），因此必须在第一张表之前设置（03 文档 §6）。
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from . import schema

logger = logging.getLogger(__name__)

BUSY_TIMEOUT_MS = 5000


class DatabaseError(RuntimeError):
    pass


class SchemaTooNewError(DatabaseError):
    """库的 schema 版本高于本程序支持的版本。

    必须明确报错而不是在不认识的结构上继续写——用户可能装了新版又退回旧版，
    此时乱写会造成不可逆的数据损坏（03 文档 §8）。
    """


class Database:
    """一个数据库文件的句柄。构造时不连接，首次使用时按线程建连。"""

    __slots__ = ("_local", "_path", "_write_lock")

    def __init__(self, path: Path) -> None:
        self._path = path
        self._local = threading.local()
        self._write_lock = threading.Lock()

    @property
    def path(self) -> Path:
        return self._path

    # ── 连接 ────────────────────────────────────────────────────────────
    def connect(self) -> sqlite3.Connection:
        """取本线程的连接，必要时新建并应用 PRAGMA。"""
        conn: sqlite3.Connection | None = getattr(self._local, "conn", None)
        if conn is not None:
            return conn
        is_new = not self._path.exists()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._path, timeout=BUSY_TIMEOUT_MS / 1000, isolation_level=None)
        conn.row_factory = sqlite3.Row
        _apply_pragmas(conn, fresh=is_new)
        self._local.conn = conn
        return conn

    def close(self) -> None:
        conn: sqlite3.Connection | None = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    # ── 事务 ────────────────────────────────────────────────────────────
    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """写事务。整批要么全进要么全不进——聚合表与原始表不允许各写一半。"""
        conn = self.connect()
        with self._write_lock:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            conn.execute("COMMIT")

    @contextmanager
    def read(self) -> Iterator[sqlite3.Connection]:
        yield self.connect()

    # ── meta ───────────────────────────────────────────────────────────
    def meta_get(self, key: str, default: str | None = None) -> str | None:
        row = self.connect().execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def meta_set(self, key: str, value: str, conn: sqlite3.Connection | None = None) -> None:
        sql = (
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
        )
        if conn is not None:
            conn.execute(sql, (key, value))
            return
        with self.transaction() as owned:
            owned.execute(sql, (key, value))

    def schema_version(self) -> int:
        if not self.table_exists("meta"):
            return 0
        return int(self.meta_get("schema_version", "0") or 0)

    # ── 自检 ────────────────────────────────────────────────────────────
    def table_exists(self, name: str) -> bool:
        row = (
            self.connect()
            .execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,))
            .fetchone()
        )
        return row is not None

    def table_names(self) -> frozenset[str]:
        rows = self.connect().execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
        return frozenset(row["name"] for row in rows)

    def quick_check(self) -> bool:
        """启动自检。损坏后继续写入会让损坏扩散（10 文档 §8）。"""
        try:
            row = self.connect().execute("PRAGMA quick_check").fetchone()
        except sqlite3.DatabaseError as exc:
            logger.error("quick_check 无法执行：%s", exc)
            return False
        return bool(row) and row[0] == "ok"

    def backup_to(self, target: Path) -> Path:
        """在线备份，无需停机（03 文档 §9）。"""
        target.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(target) as destination:
            self.connect().backup(destination)
        return target

    def checkpoint(self, mode: str = "PASSIVE") -> None:
        if mode not in {"PASSIVE", "FULL", "RESTART", "TRUNCATE"}:
            raise ValueError(f"未知的 checkpoint 模式：{mode!r}")
        self.connect().execute(f"PRAGMA wal_checkpoint({mode})")


def _apply_pragmas(conn: sqlite3.Connection, *, fresh: bool) -> None:
    if fresh:
        # 必须在建表之前：DROP 老月表后靠 incremental_vacuum 回收空间，
        # 不需要重写整库（03 文档 §6）。
        conn.execute("PRAGMA auto_vacuum=INCREMENTAL")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    # 删除时覆写页内容，让"删除敏感数据"真的删掉（08 文档 §4）。
    conn.execute("PRAGMA secure_delete=ON")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")


def create_schema(conn: sqlite3.Connection) -> None:
    """建出全部表与索引，并写入未知应用哨兵行。幂等。"""
    for ddl in schema.TABLES:
        conn.execute(ddl)
    for ddl in schema.INDEXES:
        conn.execute(ddl)
    _ensure_unknown_app(conn)


def _ensure_unknown_app(conn: sqlite3.Connection) -> None:
    """``app_id = 0`` 的哨兵行：空闲、锁屏、被排除应用期间的按键归属。

    键盘总量必须守恒——把这些按键丢弃会让"各应用按键之和"小于"总按键数"，
    用户无法解释差额（04 文档 §2.2）。
    """
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    conn.execute(
        """
        INSERT INTO app (id, app_key, identity_kind, platform_id, process_name,
                         display_name, category, category_source,
                         first_seen_at, last_seen_at)
        VALUES (?, '', 'process', 'generic', '', ?, 'uncategorized', 'auto', ?, ?)
        ON CONFLICT(id) DO NOTHING
        """,
        (schema.UNKNOWN_APP_ID, schema.UNKNOWN_APP_NAME, now, now),
    )
