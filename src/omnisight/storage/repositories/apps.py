"""``app`` 维表的解析与维护（03 文档 §2.2）。

两个旧项目都没有应用维表：TimeLens 在 ``app_usage`` 每行重复存
``app_name``/``process_name``/``exe_path`` 并按文本 ``GROUP BY``。合并后必须有维表，
因为按键聚合表需要一个紧凑外键——在 3800 万行的量级上，整型外键与重复字符串是
450 MB 与 0 的差别。

**身份是三元组 ``(platform_id, identity_kind, app_key)``**，不是单独的 ``app_key``。
Windows 上只会写入 ``('windows', 'process', casefold(process_name))``，取值与旧
``process_key`` 完全一致，所以迁移不需要转换；但字段从第一天就位，后续平台改用
bundle id / ``.desktop`` id 时无需做一次真实的数据迁移（13 文档 §7.1）。

**解析发生在前台线程上**，这是刻意的：Coordinator 必须在按键抬起那一刻就能给出具体
的 ``app_id``（04 文档 §4.1）。代价是每遇到一个**从未见过的应用**会有一次写入——
一次安装总共几十次，且在 1 秒一次的冷路径上。按键热路径依然零数据库访问。
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from sqlite3 import Connection

from ...adapters.ports import AppIdentity
from ..database import Database
from ..schema import UNKNOWN_APP_ID

logger = logging.getLogger(__name__)

_SELECT_SQL = """
SELECT id, exe_path FROM app
WHERE platform_id = ? AND identity_kind = ? AND app_key = ?
"""

_INSERT_SQL = """
INSERT INTO app (
    app_key, identity_kind, platform_id, process_name, display_name,
    exe_path, category, category_source, first_seen_at, last_seen_at
) VALUES (?, ?, ?, ?, ?, ?, 'uncategorized', 'auto', ?, ?)
ON CONFLICT(platform_id, identity_kind, app_key) DO NOTHING
"""

_TOUCH_SQL = "UPDATE app SET last_seen_at = ? WHERE id = ?"
_SET_EXE_SQL = "UPDATE app SET exe_path = ? WHERE id = ? AND exe_path = ''"


class AppRegistry:
    """``AppIdentity`` → ``app_id``，带进程内缓存。

    缓存只存"已确认存在"的映射，因此不会因为别的进程改了库而给出错误答案；最坏情况是
    多走一次 ``SELECT``。
    """

    __slots__ = ("_cache", "_db", "_exe_known", "_lock", "_platform_id")

    def __init__(self, db: Database, platform_id: str) -> None:
        self._db = db
        self._platform_id = platform_id
        self._cache: dict[tuple[str, str], int] = {}
        #: 已经补过 exe 路径的 app_id，避免每次轮询都发一条 UPDATE。
        self._exe_known: set[int] = set()
        self._lock = threading.Lock()

    def resolve(self, identity: AppIdentity, *, now: datetime | None = None) -> int:
        """取（必要时创建）该身份的 ``app_id``。失败时返回哨兵 0 而不是抛异常。

        返回 0 的语义是"这次按键归到未知"，比让 1 秒一次的轮询线程因为一次数据库
        抖动而崩掉要好——采集必须比统计精度更抗故障。
        """
        key = (identity.identity_kind, identity.app_key)
        cached = self._cache.get(key)
        if cached is not None:
            self._maybe_fill_exe_path(cached, identity.exe_path)
            return cached
        try:
            return self._resolve_uncached(key, identity, now or _now())
        except Exception:
            logger.exception("解析应用身份失败，本次归到未知：%s", identity.app_key)
            return UNKNOWN_APP_ID

    def _resolve_uncached(
        self, key: tuple[str, str], identity: AppIdentity, now: datetime
    ) -> int:
        stamp = now.isoformat(timespec="seconds")
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None:
                return cached
            conn = self._db.connect()
            row = conn.execute(
                _SELECT_SQL, (self._platform_id, identity.identity_kind, identity.app_key)
            ).fetchone()
            if row is None:
                with self._db.transaction() as write_conn:
                    write_conn.execute(
                        _INSERT_SQL,
                        (
                            identity.app_key,
                            identity.identity_kind,
                            self._platform_id,
                            identity.process_name,
                            identity.display_name or identity.app_key,
                            identity.exe_path,
                            stamp,
                            stamp,
                        ),
                    )
                row = conn.execute(
                    _SELECT_SQL, (self._platform_id, identity.identity_kind, identity.app_key)
                ).fetchone()
                logger.info(
                    "发现新应用 %s（app_id=%s）",
                    identity.app_key,
                    row["id"] if row else "?",
                )
            if row is None:  # pragma: no cover - 插入后必然查得到
                return UNKNOWN_APP_ID
            app_id = int(row["id"])
            self._cache[key] = app_id
            if row["exe_path"]:
                self._exe_known.add(app_id)
        self._maybe_fill_exe_path(app_id, identity.exe_path)
        return app_id

    def _maybe_fill_exe_path(self, app_id: int, exe_path: str) -> None:
        """首次拿到 exe 路径时补写。

        路径可能因权限拿不到（提权进程），下一次也许就拿到了；图标提取依赖它，
        所以值得补，但不能每秒发一条 UPDATE。
        """
        if not exe_path or app_id in self._exe_known or app_id == UNKNOWN_APP_ID:
            return
        self._exe_known.add(app_id)
        try:
            with self._db.transaction() as conn:
                conn.execute(_SET_EXE_SQL, (exe_path, app_id))
        except Exception:  # pragma: no cover - 补路径失败无关紧要
            logger.debug("补写 exe 路径失败 app_id=%s", app_id, exc_info=True)

    # ── 供写入线程使用 ──────────────────────────────────────────────────
    @staticmethod
    def touch(conn: Connection, app_ids: set[int], now: datetime) -> None:
        """在写入事务内刷新 ``last_seen_at``。

        由写入线程做而不是前台线程：否则同一个应用每秒都要发一条 UPDATE，而这个字段
        的用途（应用列表排序）根本不需要秒级精度。
        """
        stamp = now.isoformat(timespec="seconds")
        payload = [(stamp, app_id) for app_id in sorted(app_ids) if app_id != UNKNOWN_APP_ID]
        if payload:
            conn.executemany(_TOUCH_SQL, payload)

    # ── 只读查询 ────────────────────────────────────────────────────────
    def display_names(self) -> dict[int, str]:
        """``app_id`` → 展示名（用户别名优先）。M2 的服务层会取代它。"""
        rows = self._db.connect().execute(
            "SELECT id, display_name, user_alias FROM app ORDER BY id"
        )
        return {int(row["id"]): (row["user_alias"] or row["display_name"]) for row in rows}

    def invalidate(self) -> None:
        with self._lock:
            self._cache.clear()
            self._exe_known.clear()


def _now() -> datetime:
    return datetime.now().astimezone()


__all__ = ["AppRegistry"]
