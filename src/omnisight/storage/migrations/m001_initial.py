"""m001 —— 初始 schema。

建出 03 文档 §2 的全部表（含 ``capture_capability``）并写入创建时元信息。
``meta.timezone`` 不在这里写：它要由已解析的配置决定（``ui.timezone`` 优先于系统
时区，03 文档 §3.2），而配置属于生命周期编排的输入，不属于迁移。迁移只写与
配置无关的事实。
"""

from __future__ import annotations

from datetime import datetime
from sqlite3 import Connection

from ..database import create_schema


def up(conn: Connection) -> None:
    create_schema(conn)
    now = datetime.now().astimezone()
    _set_default(conn, "created_at", now.isoformat(timespec="seconds"))
    _set_default(conn, "data_version", "0")


def _set_default(conn: Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO NOTHING",
        (key, value),
    )
