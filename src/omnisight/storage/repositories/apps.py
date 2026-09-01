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
from dataclasses import dataclass
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

class _Unset:
    """"没传这个字段"的哨兵。``None`` 是一个有意义的取值（清除别名），不能兼任。"""

    __slots__ = ()


UNSET = _Unset()

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


@dataclass(frozen=True, slots=True)
class AppMeta:
    """``app`` 维表的一行，供服务层拼装响应。"""

    app_id: int
    app_key: str
    identity_kind: str
    platform_id: str
    process_name: str
    display_name: str
    user_alias: str | None
    exe_path: str
    category: str
    category_source: str
    merged_into: int | None
    excluded: bool
    icon_state: str
    first_seen_at: str
    last_seen_at: str

    @property
    def display(self) -> str:
        """用户别名优先。别名存在的意义就是覆盖系统给的名字。"""
        return self.user_alias or self.display_name


_META_COLUMNS = (
    "id, app_key, identity_kind, platform_id, process_name, display_name, user_alias, "
    "exe_path, category, category_source, merged_into, excluded, icon_state, "
    "first_seen_at, last_seen_at"
)

_SORTS: dict[str, str] = {
    "name": "COALESCE(user_alias, display_name) COLLATE NOCASE ASC",
    "last_seen": "last_seen_at DESC",
    "first_seen": "first_seen_at DESC",
    "process": "process_name COLLATE NOCASE ASC",
}


def _meta(row) -> AppMeta:
    return AppMeta(
        app_id=int(row["id"]),
        app_key=row["app_key"],
        identity_kind=row["identity_kind"],
        platform_id=row["platform_id"],
        process_name=row["process_name"] or "",
        display_name=row["display_name"] or "",
        user_alias=row["user_alias"],
        exe_path=row["exe_path"] or "",
        category=row["category"] or "uncategorized",
        category_source=row["category_source"] or "auto",
        merged_into=int(row["merged_into"]) if row["merged_into"] is not None else None,
        excluded=bool(row["excluded"]),
        icon_state=row["icon_state"] or "unknown",
        first_seen_at=row["first_seen_at"],
        last_seen_at=row["last_seen_at"],
    )


class AppDirectory:
    """``app`` 维表的**查询与管理**侧（05 文档 §6）。

    与 :class:`AppRegistry` 分开是因为两者的职责与调用者完全不同：Registry 在采集热路径
    的边缘上解析身份并只做插入，Directory 服务用户操作（改别名、改分类、排除、合并）
    并回答目录查询。混在一个类里会让"采集能不能崩"这个问题变得难以回答。
    """

    __slots__ = ("_db",)

    def __init__(self, db: Database) -> None:
        self._db = db

    def _conn(self) -> Connection:
        return self._db.connect()

    # ── 查询 ────────────────────────────────────────────────────────────
    def all_meta(self) -> dict[int, AppMeta]:
        """全表。应用数是几十到几百，一次读回来比每处 JOIN 更省事也更省查询。"""
        rows = self._conn().execute(f"SELECT {_META_COLUMNS} FROM app ORDER BY id")
        return {int(row["id"]): _meta(row) for row in rows}

    def get(self, app_id: int) -> AppMeta | None:
        row = self._conn().execute(
            f"SELECT {_META_COLUMNS} FROM app WHERE id = ?", (app_id,)
        ).fetchone()
        return _meta(row) if row else None

    def find_by_process(self, process_name: str) -> AppMeta | None:
        """按进程名解析（旧接口兼容层与 ``?process_name=`` 参数要用）。"""
        row = self._conn().execute(
            f"SELECT {_META_COLUMNS} FROM app WHERE app_key = ? ORDER BY id LIMIT 1",
            (process_name.casefold(),),
        ).fetchone()
        return _meta(row) if row else None

    def search(
        self,
        *,
        query: str = "",
        category: str | None = None,
        include_excluded: bool = False,
        sort: str = "name",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AppMeta], int]:
        """目录分页查询，返回 ``(当页, 总数)``。"""
        clauses: list[str] = ["id <> 0"]
        params: list[object] = []
        if query:
            clauses.append(
                "(display_name LIKE ? COLLATE NOCASE OR process_name LIKE ? COLLATE NOCASE "
                "OR user_alias LIKE ? COLLATE NOCASE)"
            )
            like = f"%{query}%"
            params += [like, like, like]
        if category:
            clauses.append("category = ?")
            params.append(category)
        if not include_excluded:
            clauses.append("excluded = 0")
        where = " AND ".join(clauses)
        order = _SORTS.get(sort, _SORTS["name"])
        total = int(
            self._conn().execute(
                f"SELECT COUNT(*) FROM app WHERE {where}", tuple(params)
            ).fetchone()[0]
            or 0
        )
        rows = self._conn().execute(
            f"SELECT {_META_COLUMNS} FROM app WHERE {where} ORDER BY {order} LIMIT ? OFFSET ?",
            (*params, limit, offset),
        )
        return ([_meta(row) for row in rows], total)

    # ── 合并 ────────────────────────────────────────────────────────────
    def merge_map(self) -> dict[int, int]:
        """``app_id`` → 根 ``app_id``。只包含真正被合并过的行。

        **查询侧统一解析到根 id**（03 文档 §2.2）：``msedge.exe`` 与
        ``msedgewebview2.exe`` 合并后必须在每一张榜单上表现为一个应用，而聚合表里
        它们仍是两行——折叠发生在服务层，SQL 不变。

        带环保护：手工改库或先后两次合并成环时，宁可停在原地也不能无限循环。
        """
        rows = self._conn().execute(
            "SELECT id, merged_into FROM app WHERE merged_into IS NOT NULL"
        )
        direct = {int(row["id"]): int(row["merged_into"]) for row in rows}
        resolved: dict[int, int] = {}
        for app_id in direct:
            seen = {app_id}
            cursor = direct[app_id]
            while cursor in direct and cursor not in seen:
                seen.add(cursor)
                cursor = direct[cursor]
            resolved[app_id] = cursor
        return resolved

    def set_merge(self, app_id: int, into_app_id: int | None) -> None:
        """写 ``merged_into``。``None`` = 取消合并。"""
        with self._db.transaction() as conn:
            conn.execute("UPDATE app SET merged_into = ? WHERE id = ?", (into_app_id, app_id))
            self._db.bump_data_version(conn)

    # ── 用户编辑 ────────────────────────────────────────────────────────
    def update(
        self,
        app_id: int,
        *,
        user_alias: str | None | _Unset = UNSET,
        category: str | _Unset = UNSET,
        excluded: bool | _Unset = UNSET,
    ) -> None:
        """部分更新。改分类时同时写 ``category_source = 'user'``。

        用哨兵 :data:`UNSET` 区分"没传这个字段"与"传了 null"：``user_alias = null``
        的语义是"清除别名，回到系统名"，而不是"别动它"。
        """
        assignments: list[str] = []
        params: list[object] = []
        if not isinstance(user_alias, _Unset):
            assignments.append("user_alias = ?")
            params.append(user_alias or None)
        if not isinstance(category, _Unset):
            assignments += ["category = ?", "category_source = 'user'"]
            params.append(category)
        if not isinstance(excluded, _Unset):
            assignments.append("excluded = ?")
            params.append(int(bool(excluded)))
        if not assignments:
            return
        with self._db.transaction() as conn:
            conn.execute(
                f"UPDATE app SET {', '.join(assignments)} WHERE id = ?", (*params, app_id)
            )
            self._db.bump_data_version(conn)

    def apply_auto_categories(self, categorize) -> int:
        """给还没被用户改过的应用补自动分类，返回改动行数。

        分类规则会随版本更新（新增了一个应用的关键词），已入库的行不会自己变。启动时
        跑一遍很便宜（几十行），而 ``category_source = 'user'`` 的行**绝不覆盖**——
        用户的选择优先于规则。
        """
        rows = self._conn().execute(
            "SELECT id, display_name, process_name, category FROM app "
            "WHERE category_source = 'auto' AND id <> 0"
        ).fetchall()
        updates = []
        for row in rows:
            guess = categorize(row["display_name"] or "", row["process_name"] or "")
            if guess != (row["category"] or "uncategorized"):
                updates.append((guess, int(row["id"])))
        if not updates:
            return 0
        with self._db.transaction() as conn:
            conn.executemany("UPDATE app SET category = ? WHERE id = ?", updates)
            self._db.bump_data_version(conn)
        return len(updates)

    # ── 图标缓存（04 文档 §6"改动一"与"改动三"）──────────────────────────
    def icon(self, app_id: int) -> dict | None:
        row = self._conn().execute(
            "SELECT app_id, png, size, source_path, resolved_at, failed_at "
            "FROM app_icon WHERE app_id = ?",
            (app_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "app_id": int(row["app_id"]),
            "png": row["png"],
            "size": int(row["size"] or 0),
            "source_path": row["source_path"] or "",
            "resolved_at": row["resolved_at"],
            "failed_at": row["failed_at"],
        }

    def store_icon(
        self, app_id: int, png: bytes | None, *, size: int, source_path: str, now: datetime
    ) -> None:
        """写入解析结果。``png is None`` = 解析失败，记 ``failed_at`` 以便日后重试。

        现状把失败永久缓存为 ``b""``，于是用户装好某个程序后图标永远不出现（除非重启
        进程）。这里让失败可过期（见 :func:`icon_is_stale`）。
        """
        stamp = now.isoformat(timespec="seconds")
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO app_icon (app_id, png, size, source_path, resolved_at, failed_at) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(app_id) DO UPDATE SET png = excluded.png, size = excluded.size, "
                "source_path = excluded.source_path, resolved_at = excluded.resolved_at, "
                "failed_at = excluded.failed_at",
                (app_id, png, size, source_path, stamp, None if png else stamp),
            )
            conn.execute(
                "UPDATE app SET icon_state = ? WHERE id = ?",
                ("ok" if png else "missing", app_id),
            )

    def clear_icons(self) -> int:
        with self._db.transaction() as conn:
            cursor = conn.execute("DELETE FROM app_icon")
            conn.execute("UPDATE app SET icon_state = 'unknown'")
            return int(cursor.rowcount or 0)

#: 图标解析失败后多久允许重试。7 天是个折中：装好程序后不用等到下次大版本，也不会
#: 让"这台机器上确实没有图标"的应用每次刷新都触发一遍注册表遍历（04 文档 §6"改动三"）。
ICON_RETRY_DAYS = 7


def icon_is_stale(entry: dict | None, *, now: datetime) -> bool:
    """``True`` 表示应该（重新）解析。"""
    if entry is None:
        return True
    if entry.get("png"):
        return False
    failed_at = entry.get("failed_at")
    if not failed_at:
        return True
    try:
        failed = datetime.fromisoformat(str(failed_at))
    except ValueError:  # pragma: no cover - 手工改库
        return True
    if failed.tzinfo is None:
        failed = failed.replace(tzinfo=now.tzinfo)
    return (now - failed).days >= ICON_RETRY_DAYS

def _now() -> datetime:
    return datetime.now().astimezone()


__all__ = ["ICON_RETRY_DAYS", "UNSET", "AppDirectory", "AppMeta", "AppRegistry", "icon_is_stale"]
