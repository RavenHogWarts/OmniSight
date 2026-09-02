"""迁移注册与执行器（03 文档 §8）。

关键是**向前兼容检查**：用户可能装了新版后又退回旧版，此时旧版必须明确报错，
而不是在不认识的 schema 上继续写。
"""

from __future__ import annotations

import logging
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from sqlite3 import Connection

from ..database import Database, SchemaTooNewError
from . import m001_initial, m002_query_support, m003_import_legacy

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    description: str
    up: Callable[[Connection], None]


MIGRATIONS: tuple[Migration, ...] = (
    Migration(1, "initial schema", m001_initial.up),
    Migration(2, "M2 查询层所需的列与表", m002_query_support.up),
    Migration(3, "M5 旧数据导入钩子", m003_import_legacy.up),
)

TARGET_VERSION = MIGRATIONS[-1].version


def backup_database(path: Path) -> Path | None:
    """迁移前备份——降级或回滚时唯一的保险。"""
    if not path.exists():
        return None
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    target_dir = path.parent / "backup" / stamp
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / path.name
    shutil.copy2(path, target)
    logger.info("迁移前已备份数据库到 %s", target)
    return target


def migrate(db: Database) -> int:
    """把库升到 :data:`TARGET_VERSION`，返回最终版本号。"""
    current = db.schema_version()
    if current > TARGET_VERSION:
        raise SchemaTooNewError(
            f"数据库版本 {current} 高于本程序支持的 {TARGET_VERSION}，请升级 OmniSight"
        )
    if current == TARGET_VERSION:
        return current

    if current > 0:
        backup_database(db.path)

    for migration in MIGRATIONS:
        if migration.version <= current:
            continue
        logger.info("执行迁移 %s：%s", migration.version, migration.description)
        with db.transaction() as conn:
            migration.up(conn)
            db.meta_set("schema_version", str(migration.version), conn=conn)
        current = migration.version
    return current
