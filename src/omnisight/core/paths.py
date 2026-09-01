"""路径解析：唯一知道"数据该放哪"的模块。

本模块是 02 文档 §1 那条"核心层不得判断平台"约束的**唯一显式豁免**：
把三行路径拼接搬进适配器不划算，而路径必须在适配器装配之前就可用
（日志、配置、单实例锁文件都依赖它）。豁免范围仅限
``_platform_app_dir()`` 一个函数，且 ``tools/check_platform_leaks.py``
只为本文件开白名单。

目录布局（03 文档 §10）::

    <app_root>/
    ├── config.json
    ├── data/
    │   └── omnisight.db
    └── logs/
        └── omnisight.log
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIR_NAME = "OmniSight"
APP_DIR_NAME_POSIX = "omnisight"
PORTABLE_MARKER = "portable.marker"
DATABASE_FILENAME = "omnisight.db"


def is_frozen() -> bool:
    """PyInstaller 打包后运行。"""
    return getattr(sys, "frozen", False)


def resource_dir() -> Path:
    """只读的随包资源目录（templates / static / assets）。

    打包后是 ``sys._MEIPASS``——**每次运行都会重建的临时目录**，
    绝不能往里写数据。可写目录一律走 :func:`app_root`。
    """
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass) / "omnisight"
    return Path(__file__).resolve().parent.parent


def exe_dir() -> Path:
    """程序所在目录：打包后是 exe 同级，开发模式是仓库根。"""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    # src/omnisight/core/paths.py → 仓库根
    return Path(__file__).resolve().parents[3]


def portable_marker_path() -> Path:
    return exe_dir() / PORTABLE_MARKER


def is_portable() -> bool:
    """便携模式：程序同级存在 ``portable.marker``。"""
    return portable_marker_path().exists()


def _platform_app_dir() -> Path:
    """各平台的用户数据惯例目录。**本仓库唯一允许判断平台的核心函数。**"""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")
        return Path(base) / APP_DIR_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_DIR_NAME
    base = os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")
    return Path(base) / APP_DIR_NAME_POSIX


def _legacy_adjacent_root() -> Path | None:
    """升级兼容：exe 同级已有数据库但没有便携标记时，沿用旧位置。

    10 文档 §2.2 的硬要求——**绝不静默把用户的数据库搬走**。旧版本一律把
    数据写在程序同级，若此时改用平台惯例目录，用户会看到"历史记录全没了"。
    """
    candidate = exe_dir() / "data" / DATABASE_FILENAME
    return exe_dir() if candidate.exists() else None


def app_root() -> Path:
    """可写数据根目录，按优先级解析：便携标记 → 旧位置 → 平台惯例。"""
    if is_portable():
        return exe_dir()
    legacy = _legacy_adjacent_root()
    if legacy is not None:
        return legacy
    return _platform_app_dir()


def config_path(root: Path | None = None) -> Path:
    return (root or app_root()) / "config.json"


def data_dir(root: Path | None = None, override: str | os.PathLike[str] | None = None) -> Path:
    """数据目录；``storage.data_dir`` 配置项可覆盖（02 文档 §6）。"""
    if override:
        return Path(override).expanduser()
    return (root or app_root()) / "data"


def logs_dir(root: Path | None = None) -> Path:
    return (root or app_root()) / "logs"


def database_path(data: Path) -> Path:
    return data / DATABASE_FILENAME


def ensure_dir(path: Path) -> Path:
    """创建目录（含父级），已存在则无操作。"""
    path.mkdir(parents=True, exist_ok=True)
    return path


def describe() -> dict[str, str]:
    """供日志首行与 ``/api/v1/status`` 使用的路径快照。"""
    root = app_root()
    return {
        "frozen": str(is_frozen()),
        "portable": str(is_portable()),
        "exe_dir": str(exe_dir()),
        "app_root": str(root),
        "config": str(config_path(root)),
        "data_dir": str(data_dir(root)),
        "logs_dir": str(logs_dir(root)),
        "resource_dir": str(resource_dir()),
    }
