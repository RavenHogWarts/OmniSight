"""隐私硬约束的回归测试（08 文档、11 文档 §4.5）。

**遍历全部端点，而不是抽查几个。** 每加一个端点就是一次新的泄漏机会，而"忘了在新端点上
过滤标题"这种错误在功能测试里完全看不出来——响应里多一个字段，没有任何断言会失败。因此
这里的端点清单**从 Flask 的路由表现场生成**：新写的端点自动被纳入，不需要有人记得来补。

固定的四条：

1. 窗口标题不出接口（用户显式开启 + 显式请求时才例外）；
2. 每个 ``/api/v1/*`` 都要令牌；
3. 常规查询不扫 ``raw_key_events_*``（唯一例外带单日窗上限）；
4. ``app_id = 0`` 的按键不消失也不变成一个"应用"。
"""

from __future__ import annotations

import pytest
from flask import Flask

from omnisight.presentation import security
from omnisight.presentation.web import create_app
from seeded import SECRET_TITLE

#: 路径参数的填充值。新增带参路由时在这里加一项，否则下面的遍历会跳过它并失败。
PARAM_VALUES = {"app_id": "1", "key_id": "key_a"}
#: 需要副作用或长连接的路由不在只读遍历里跑；它们各自有专门的用例。
SKIP_ENDPOINTS = {"stream", "capture_pause", "static"}


def _readable_paths(app: Flask) -> list[str]:
    """路由表 → 可直接 GET 的 URL 列表（含查询串，覆盖多种周期）。"""
    paths: list[str] = []
    for rule in app.url_map.iter_rules():
        if "GET" not in rule.methods or rule.endpoint in SKIP_ENDPOINTS:
            continue
        path = str(rule)
        for name in rule.arguments:
            if name not in PARAM_VALUES:
                raise AssertionError(f"路由 {path} 的参数 {name} 没有测试填充值")
            path = path.replace(f"<int:{name}>", PARAM_VALUES[name])
            path = path.replace(f"<{name}>", PARAM_VALUES[name])
        paths.append(path)
    return sorted(paths)


@pytest.fixture
def paths(api_context) -> list[str]:
    return _readable_paths(create_app(api_context))


def test_the_route_sweep_actually_covers_the_api(paths: list[str]):
    """这条用例保护下面所有遍历型用例：清单空了或漏了，它们会全部静默通过。"""
    api = [path for path in paths if path.startswith("/api/v1/")]
    assert len(api) >= 12, f"只扫到 {len(api)} 个端点，路由发现大概坏了"
    assert "/api/v1/overview" in api
    assert "/api/v1/usage/sessions" in api


# ── 1. 窗口标题 ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("range_name", ["day", "week", "month", "year", "total"])
def test_no_endpoint_leaks_window_titles_by_default(seeded_client, paths, range_name: str):
    """标题可以存（用户显式开启），但**默认绝不出接口**。

    断言内容而不是字段名：字段可以改名，"季度并购方案-绝密"不会。
    """
    for path in paths:
        joiner = "&" if "?" in path else "?"
        body = seeded_client.get(f"{path}{joiner}range={range_name}").get_data(as_text=True)
        assert SECRET_TITLE not in body, f"{path} 泄漏了窗口标题"
        assert "绝密" not in body, f"{path} 泄漏了标题片段"


def test_sessions_withhold_titles_even_when_explicitly_requested_if_recording_is_off(
    seeded_client,
):
    """两道闸都要开：``include_titles=true`` **且** ``privacy.record_window_titles``。

    只看请求参数就返回标题，等于任何一个能发请求的人都能读到标题。
    """
    payload = seeded_client.get(
        "/api/v1/usage/sessions?range=day&include_titles=true"
    ).get_json()
    assert all(item["window_title"] is None for item in payload["sessions"])


def test_sessions_return_titles_only_when_the_user_turned_recording_on(
    api_context, seeded, seeded_client
):
    """开关打开后标题可以出——这是用户的显式选择，不是默认行为。"""
    from dataclasses import replace

    config = api_context.config
    api_context.config = replace(config, privacy=replace(config.privacy, record_window_titles=True))
    api_context.services.context.config = api_context.config
    client = create_app(api_context).test_client()
    client.environ_base["HTTP_X_OMNISIGHT_TOKEN"] = seeded_client.environ_base[
        "HTTP_X_OMNISIGHT_TOKEN"
    ]
    payload = client.get("/api/v1/usage/sessions?range=day&include_titles=true").get_json()
    titles = [item["window_title"] for item in payload["sessions"]]
    assert SECRET_TITLE in titles
    # 没有显式请求时仍然不给：开关只是"允许"，不是"总是"。
    plain = client.get("/api/v1/usage/sessions?range=day").get_json()
    assert all(item["window_title"] is None for item in plain["sessions"])


def test_the_repository_layer_reads_titles_only_where_it_must(database, seeded):
    """``recent_sessions`` 根本不把标题读出来——进了内存，就总有一天会被序列化出去。"""
    from omnisight.storage.repositories.usage import UsageRepository

    rows = UsageRepository(database).recent_sessions()
    assert rows, "夹具里播了会话，读不到说明查询写错了"
    for row in rows:
        assert "window_title" not in row
        assert SECRET_TITLE not in str(row)


# ── 2. 令牌 ─────────────────────────────────────────────────────────────
def test_every_api_endpoint_requires_the_token(api_context, paths):
    """公开端点只有 ``/`` 与 ``/healthz``——它们不返回任何统计数据。"""
    client = create_app(api_context).test_client()
    for path in paths:
        response = client.get(path)
        if path.startswith("/api/v1/"):
            assert response.status_code == 401, f"{path} 没有拦住无令牌请求"
            assert response.get_json()["error"]["code"] == "unauthorized"
        else:
            assert response.status_code < 400, f"{path} 应当是公开的"


def test_no_endpoint_name_slips_into_the_public_allowlist():
    """免鉴权清单是一个白名单，且必须短到可以人工审阅。"""
    assert set(security.PUBLIC_ENDPOINTS) <= {"index", "healthz", "static", "favicon"}


def test_write_operations_need_a_same_site_request(api_context, seeded):
    """令牌防"任意网页能不能读"；同源校验防"能不能让浏览器代替用户发起写操作"。"""
    client = create_app(api_context).test_client()
    headers = {security.TOKEN_HEADER: "test-token-value", "Sec-Fetch-Site": "cross-site"}
    response = client.patch("/api/v1/apps/1", json={"user_alias": "x"}, headers=headers)
    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "cross_site_denied"


# ── 3. 原始事件表 ───────────────────────────────────────────────────────
def _sql_touching_raw(client, database, path: str) -> list[str]:
    conn = database.connect()
    seen: list[str] = []
    conn.set_trace_callback(lambda sql: seen.append(sql) if "raw_key_events" in sql else None)
    try:
        client.get(path)
    finally:
        conn.set_trace_callback(None)
    # ``sqlite_master`` 的存在性探测不是"扫原始表"，它只读目录。
    return [sql for sql in seen if "sqlite_master" not in sql]


@pytest.mark.parametrize("range_name", ["day", "month", "year", "total"])
def test_regular_queries_never_scan_the_raw_event_tables(
    seeded_client, database, paths, range_name: str
):
    """一年的原始事件是千万级。扫一次就没有 P95 可谈了（01 文档 §4.1、12 文档 M2）。"""
    for path in paths:
        joiner = "&" if "?" in path else "?"
        touched = _sql_touching_raw(seeded_client, database, f"{path}{joiner}range={range_name}")
        assert not touched, f"{path} 扫了原始事件表：{touched}"


def test_the_one_documented_exception_is_bounded_to_a_single_day(
    seeded_client, database, seeded
):
    """应用维度的小时回溯是唯一例外，条件是**必须有时间窗上限**。"""
    touched = _sql_touching_raw(
        seeded_client,
        database,
        f"/api/v1/keyboard/timeline?view=hours&app_id={seeded.code}&range=day",
    )
    assert len(touched) == 1, "例外只该发一条查询"
    # sqlite3 的 trace 回调给出的是展开后的 SQL（参数已代入），因此断言的是"有边界"
    # 而不是占位符本身。
    sql = touched[0]
    assert f"app_id = {seeded.code}" in sql
    assert "down_ts_ns >=" in sql and "down_ts_ns <" in sql, "缺时间窗上限"
    assert "raw_key_events_2026_09" in sql, "必须落到具体月表，不能跨分区"


def test_the_exception_says_so_instead_of_drawing_zeros_when_raw_events_are_off(
    api_context, seeded, seeded_client, database
):
    """原始事件被关掉时如实报"该视图不可用"。全 0 的图会让用户以为自己没按过键。"""
    with database.transaction() as conn:
        conn.execute("DROP TABLE IF EXISTS raw_key_events_2026_09")
    payload = seeded_client.get(
        f"/api/v1/keyboard/timeline?view=hours&app_id={seeded.code}&range=day"
    ).get_json()
    assert payload["views"]["hours"]["available"] is False
    codes = {warning["code"] for warning in payload["warnings"]}
    assert "hour_view_unavailable_for_app" in codes


# ── 4. 未归因按键 ───────────────────────────────────────────────────────
def test_unattributed_presses_are_reported_not_dropped(seeded_client):
    """空闲/锁屏/被排除应用期间的按键归到 ``app_id = 0``，**不丢弃**——总量必须守恒。"""
    payload = seeded_client.get("/api/v1/insights/app-keyboard?range=year").get_json()
    assert payload["unattributed_presses"] == 9  # 2 次（今天）+ 7 次（无前台那天）
    attributed = sum(app["presses"] for app in payload["apps"])
    heatmap = seeded_client.get("/api/v1/keyboard/heatmap?range=year").get_json()
    assert attributed + payload["unattributed_presses"] == heatmap["totals"]["press_count"]


def test_the_unknown_sentinel_is_never_presented_as_an_app(seeded_client):
    for path in ("/api/v1/usage/period", "/api/v1/apps", "/api/v1/insights/app-keyboard"):
        payload = seeded_client.get(f"{path}?range=year").get_json()
        rows = payload.get("apps", [])
        assert all(row["app_id"] != 0 for row in rows), f"{path} 把未知哨兵当成了应用"


def test_querying_the_unknown_sentinel_directly_is_rejected(seeded_client):
    """它不是一个应用，不接受用户按它查询。"""
    assert seeded_client.get("/api/v1/keyboard/heatmap?range=day&app_id=0").status_code == 400
    assert seeded_client.get("/api/v1/apps/0").status_code == 404
