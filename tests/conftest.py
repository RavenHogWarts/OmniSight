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
from omnisight.presentation.security import TOKEN_HEADER as API_TOKEN_HEADER  # noqa: E402
from omnisight.storage.database import Database  # noqa: E402
from omnisight.storage.migrations import migrate  # noqa: E402

API_TOKEN = "test-token-value"


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


@pytest.fixture
def api_context(database, full_capabilities, tmp_path):
    """带服务层的表现层上下文（M2 起 :func:`create_app` 需要它才会注册 API 路由）。

    时区与时钟都**写死**：周期查询的锚点是"今天"，用真实时间会让所有契约测试在第二天
    集体变成空数据——而"空数据"恰好也是一种合法响应，于是失败会静默。时区不写死则会
    在跨零点的 CI 机器上让日期桶漂一天。
    """
    from dataclasses import replace

    from fakes import FakeClock
    from omnisight.core.config import default_config
    from omnisight.presentation.web import AppContext
    from omnisight.services import Services
    from omnisight.storage.migrations import TARGET_VERSION
    from seeded import NOW, TZ

    base = default_config()
    config = replace(base, ui=replace(base.ui, timezone=str(TZ), week_starts_on=0))
    context = AppContext(
        config=config,
        database=database,
        capabilities=full_capabilities,
        token=API_TOKEN,
        started_at=NOW.isoformat(timespec="seconds"),
        data_dir=tmp_path,
        schema_version=TARGET_VERSION,
    )
    context.services = Services.build(
        database=database,
        config=config,
        capabilities=full_capabilities,
        config_path=tmp_path / "config.json",
        clock=FakeClock(NOW),
    )
    return context


@pytest.fixture
def api_client(api_context):
    """已带令牌与 ``Sec-Fetch-Site`` 的客户端。**空库**——需要数据的用例用 ``seeded_client``。"""
    return _client_for(api_context)


@pytest.fixture
def seeded(database):
    """把确定性数据集写进库。见 :mod:`seeded` 的分工说明。"""
    import seeded as dataset

    return dataset.seed(database)


@pytest.fixture
def seeded_client(api_context, seeded):
    return _client_for(api_context)


def _client_for(context):
    from omnisight.presentation.web import create_app

    app = create_app(context)
    app.config.update(TESTING=True)
    client = app.test_client()
    client.environ_base["HTTP_" + API_TOKEN_HEADER.upper().replace("-", "_")] = API_TOKEN
    client.environ_base["HTTP_SEC_FETCH_SITE"] = "same-origin"
    return client
