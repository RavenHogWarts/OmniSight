"""共享夹具。

一条贯穿全部测试的原则：**除 ``windows_only`` 标记的少数用例外，所有测试都必须
能在三个平台上通过**（11 文档 §1）。这是"核心层真的不依赖 Win32"的唯一机械化
证据，因此夹具里不许出现平台假设。
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from omnisight.adapters.ports import Capabilities  # noqa: E402
from omnisight.storage.database import Database  # noqa: E402
from omnisight.storage.migrations import migrate  # noqa: E402


def pytest_collection_modifyitems(config, items):
    """非 Windows 上自动跳过 ``windows_only``，不必在每个用例里写 skipif。"""
    if sys.platform == "win32":
        return
    skip = pytest.mark.skip(reason="需要真实 Windows API")
    for item in items:
        if "windows_only" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def database(tmp_path: Path) -> Database:
    db = Database(tmp_path / "omnisight.db")
    migrate(db)
    yield db
    db.close()


@pytest.fixture
def fixed_now() -> datetime:
    return datetime(2026, 8, 31, 22, 15, 3, tzinfo=UTC)


@pytest.fixture
def full_capabilities() -> Capabilities:
    """一个"什么都能做"的能力集合，用于验证正常路径。"""
    return Capabilities(
        platform_id="windows",
        tier=1,
        os_version="10.0.26100",
        keyboard=True,
        keyboard_backend="raw_input",
        keyboard_durations=True,
        key_position_stable=True,
        foreground=True,
        window_titles=True,
        idle=True,
        icons=True,
        autostart=True,
        tray=True,
    )
