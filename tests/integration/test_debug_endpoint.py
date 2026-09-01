"""``/api/v1/_debug/attribution``：M1 纵切的 HTTP 出口（12 文档 §2 的最后一项交付物）。

这是**临时端点**，M2 起由正式接口取代。它值得有测试的理由不是形状稳定（恰恰相反），
而是它承载了两件不临时的事：

1. 合并的核心产出（应用×键、键×应用）真的能被一次请求查到；
2. 三条隐私硬约束在**新增端点上也成立**——需要令牌、不返回窗口标题、非法参数 400。
   隐私回归测试必须遍历「全部端点」，否则每加一个端点就是一次新的泄漏机会
   （11 文档 §4.5）。
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from flask.testing import FlaskClient

from omnisight.adapters.ports import AppIdentity
from omnisight.capture.coordinator import CaptureCoordinator
from omnisight.capture.models import KeyEvent, UsageSession
from omnisight.capture.queue import EventQueue
from omnisight.core.bus import EventBus
from omnisight.core.config import default_config
from omnisight.core.lifecycle import CaptureBundle
from omnisight.presentation import security
from omnisight.presentation.web import AppContext, create_app
from omnisight.storage.migrations import TARGET_VERSION
from omnisight.storage.repositories.apps import AppRegistry
from omnisight.storage.repositories.keys import KeyRepository
from omnisight.storage.repositories.usage import UsageRepository
from omnisight.storage.writer import StorageWriter

TOKEN = "debug-token"
TZ = ZoneInfo("Asia/Shanghai")
DAY = "2026-08-31"
MOMENT = datetime(2026, 8, 31, 14, 30, tzinfo=TZ)
#: 播种一个绝不该出现在任何响应里的标题。断言用它比断言「不含 window_title 字段」更强：
#: 字段可以改名，内容不会。
SECRET_TITLE = "季度并购方案-绝密.xlsx — Excel"


@pytest.fixture
def bundle(database) -> CaptureBundle:
    queue = EventQueue()
    registry = AppRegistry(database, "windows")
    coordinator = CaptureCoordinator()
    writer = StorageWriter(database, queue, tz=TZ, registry=registry)
    app_id = registry.resolve(
        AppIdentity(
            app_key="code.exe", identity_kind="process",
            display_name="code.exe", process_name="code.exe",
        )
    )
    down = int(MOMENT.timestamp() * 1_000_000_000)
    for index, key_id in enumerate(("key_a", "key_a", "control_left", "space")):
        queue.put(
            KeyEvent(
                key_id=key_id,
                down_ts_ns=down + index * 1_000_000_000,
                up_ts_ns=down + index * 1_000_000_000 + 80_000_000,
                duration_ms=80.0,
                app_id=app_id,
                confidence="high",
            )
        )
    queue.put(
        UsageSession(
            app_id=app_id,
            start_ts_ns=down,
            end_ts_ns=down + 600_000_000_000,
            duration_ms=600_000,
            window_title=SECRET_TITLE,
        )
    )
    while queue.depth:
        writer.flush_once()

    coordinator.set_foreground(app_id)
    return CaptureBundle(
        bus=EventBus(),
        queue=queue,
        coordinator=coordinator,
        writer=writer,
        registry=registry,
        keys=KeyRepository(database),
        usage=UsageRepository(database),
    )


def _context(database, capabilities, tmp_path, capture) -> AppContext:
    return AppContext(
        config=default_config(),
        database=database,
        capabilities=capabilities,
        token=TOKEN,
        started_at="2026-08-31T22:15:03+08:00",
        data_dir=tmp_path,
        schema_version=TARGET_VERSION,
        capture=capture,
    )


@pytest.fixture
def client(database, full_capabilities, tmp_path, bundle) -> FlaskClient:
    app = create_app(_context(database, full_capabilities, tmp_path, bundle))
    app.config.update(TESTING=True)
    return app.test_client()


def _auth() -> dict[str, str]:
    return {security.TOKEN_HEADER: TOKEN}


def test_endpoint_answers_the_question_the_merge_exists_to_answer(client: FlaskClient):
    """「Code.exe 按了几次 A」——合并前需要跨进程 HTTP + 区间求交，现在是一次点查。"""
    payload = client.get(f"/api/v1/_debug/attribution?date={DAY}", headers=_auth()).get_json()

    app_keyboard = payload["app_keyboard"]
    assert app_keyboard["app_name"] == "code.exe"
    keys = {item["key_id"]: item for item in app_keyboard["keys"]}
    assert keys["key_a"]["press_count"] == 2
    assert keys["key_a"]["label"] == "A"
    assert keys["control_left"]["label"] == "Ctrl"

    # 反向视图：某个键主要被哪些应用按。合并前完全无法回答。
    key_apps = client.get(
        f"/api/v1/_debug/attribution?date={DAY}&key_id=key_a", headers=_auth()
    ).get_json()["key_apps"]
    assert key_apps["key_id"] == "key_a"
    assert [row["name"] for row in key_apps["apps"]] == ["code.exe"]


def test_endpoint_reports_the_aggregate_self_check(client: FlaskClient):
    """聚合一致性做成端点上可见的自检：不主动核对，漂移就永远不会被发现（R6）。"""
    consistency = client.get(
        f"/api/v1/_debug/attribution?date={DAY}", headers=_auth()
    ).get_json()["consistency"]
    assert consistency["match"] is True
    assert consistency["agg_key_day"] == 4
    assert len({consistency[key] for key in consistency if key != "match"}) == 1


def test_endpoint_exposes_live_capture_state(client: FlaskClient):
    payload = client.get("/api/v1/_debug/attribution", headers=_auth()).get_json()
    assert payload["attribution"]["app_name"] == "code.exe"
    assert payload["attribution"]["confidence"] in {"high", "boundary"}
    assert payload["capture"]["queue_depth"] == 0
    assert payload["usage"]["data_range"]["min_date"] == DAY
    assert payload["note"], "临时端点必须自报「别依赖我」"


def test_no_endpoint_returns_window_titles(client: FlaskClient):
    """标题可以存（用户显式开启），但**绝不出接口**——08 文档的硬约束。

    遍历全部端点而不是只测这一个：每加一个端点就是一次新的泄漏机会。
    """
    paths = [
        "/api/v1/status",
        f"/api/v1/_debug/attribution?date={DAY}",
        f"/api/v1/_debug/attribution?date={DAY}&key_id=space",
        "/healthz",
        "/",
    ]
    for path in paths:
        body = client.get(path, headers=_auth()).get_data(as_text=True)
        assert SECRET_TITLE not in body, f"{path} 泄漏了窗口标题"
        assert "绝密" not in body, f"{path} 泄漏了标题片段"


def test_recent_sessions_repository_also_withholds_titles(bundle):
    """仓储层就不该把标题读出来——让它进内存，就总有一天会被某个端点序列化出去。"""
    sessions = bundle.usage.recent_sessions()
    assert sessions, "夹具里播了一条会话，读不到说明查询写错了"
    for row in sessions:
        assert "window_title" not in row
        assert SECRET_TITLE not in str(row)


@pytest.mark.parametrize(
    "bad",
    ["2026-13-01", "not-a-date", "2026-02-30", "'; DROP TABLE app; --", "2026-08-31T00:00"],
)
def test_invalid_date_is_rejected_rather_than_silently_defaulting(
    client: FlaskClient, bad: str
):
    """非法参数一律 400。静默回退到今天会让用户以为自己查的是别的日期（05 文档 §1.5）。"""
    response = client.get(f"/api/v1/_debug/attribution?date={bad}", headers=_auth())
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_date"


def test_empty_date_parameter_means_today_not_an_error(client: FlaskClient):
    """``?date=`` 与不传等价，走默认值分支——这是刻意的，不是漏洞。"""
    assert client.get("/api/v1/_debug/attribution?date=", headers=_auth()).status_code == 200


def test_debug_endpoint_requires_the_token(client: FlaskClient):
    """下划线前缀不代表它可以免鉴权——那会让它成为一个免鉴权的信息出口。"""
    assert client.get("/api/v1/_debug/attribution").status_code == 401
    assert not any("debug" in name for name in security.PUBLIC_ENDPOINTS)


def test_endpoint_reports_422_when_no_capture_pipeline_was_assembled(
    database, full_capabilities, tmp_path
):
    """没有采集管道时如实说「这次运行没有」，而不是返回一堆 0 让人以为没按过键。"""
    app = create_app(_context(database, full_capabilities, tmp_path, None))
    app.config.update(TESTING=True)
    response = app.test_client().get("/api/v1/_debug/attribution", headers=_auth())
    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "capture_unavailable"


def test_sql_injection_shaped_key_id_is_treated_as_an_unknown_key(client: FlaskClient):
    """全部查询都是参数化的；这条用例固定住「以后也不许改成拼字符串」。"""
    response = client.get(
        f"/api/v1/_debug/attribution?date={DAY}&key_id='; DROP TABLE app; --",
        headers=_auth(),
    )
    assert response.status_code == 200
    assert response.get_json()["key_apps"]["apps"] == []
    # 表还在：下一次请求仍能正常返回。
    assert client.get("/api/v1/status", headers=_auth()).status_code == 200


def test_empty_database_returns_a_well_formed_payload_not_a_500(
    database, full_capabilities, tmp_path
):
    """新装用户第一次打开就是空库，而空数据路径是最少被人工走到的路径。"""
    queue = EventQueue()
    registry = AppRegistry(database, "windows")
    bundle = CaptureBundle(
        bus=EventBus(),
        queue=queue,
        coordinator=CaptureCoordinator(),
        writer=StorageWriter(database, queue, tz=TZ, registry=registry),
        registry=registry,
        keys=KeyRepository(database),
        usage=UsageRepository(database),
    )
    app = create_app(_context(database, full_capabilities, tmp_path, bundle))
    app.config.update(TESTING=True)
    payload = app.test_client().get(
        "/api/v1/_debug/attribution", headers=_auth()
    ).get_json()

    assert payload["keyboard"]["press_total"] == 0
    assert payload["keyboard"]["top_keys"] == []
    assert payload["app_keyboard"]["keys"] == []
    assert payload["usage"]["ranking"] == []
    assert payload["usage"]["data_range"] == {"min_date": None, "max_date": None}
    assert payload["consistency"]["match"] is True
    assert payload["attribution"]["app_id"] == 0
