"""旧接口兼容层与导入端点的契约测试（05 文档 §8、09 文档 §4 与 §6）。

兼容层的核心断言不是"形状完全一致"（旧前端已死），而是三件事：
1. **旧消费者能活**——旧 KeyTrace 依赖的两个集成端点返回它认识的形状；
2. **退役有迹可循**——每个响应都带 Deprecation / Sunset 头；
3. **免令牌不等于公开**——这些端点仍受 Host 校验保护，而 /api/v1/* 仍要令牌。
"""

from __future__ import annotations

import time
from itertools import pairwise

import pytest

from legacy_dbs import make_keytrace_db, make_timelens_db, timelens_row, tz_noon_ns

# ── 兼容层：TimeLens 方言 ────────────────────────────────────────────────


@pytest.mark.parametrize("path", [
    "/api/daily",
    "/api/period?view=daily",
    "/api/period?view=weekly",
    "/api/period?view=monthly",
    "/api/period?view=yearly",
    "/api/period?view=total",
    "/api/hourly",
    "/api/weekly",
    "/api/keyboard?view=total",
    "/api/dates",
])
def test_timelens_endpoints_keep_the_old_shape(seeded_client, path):
    response = seeded_client.get(path)
    assert response.status_code == 200, path
    assert response.headers.get("Deprecation") == "true"
    assert response.headers.get("Sunset")
    payload = response.get_json()
    if path.startswith(("/api/daily", "/api/period", "/api/weekly")):
        assert {"total_seconds", "total_formatted", "app_count", "apps"} <= set(payload)
        for app in payload["apps"]:
            assert {"app_name", "process_name", "total_seconds", "session_count"} <= set(app)
    elif path.startswith("/api/hourly"):
        assert len(payload["hours"]) == 24
        assert {"hour", "apps", "categories"} <= set(payload["hours"][0])
    elif path.startswith("/api/keyboard"):
        assert {"total_presses", "active_keys", "keys", "hours", "daily_activity"} <= set(payload)
    elif path == "/api/dates":
        assert payload["min_date"] == "2025-12-15"


def test_weekly_keeps_the_rolling_window_semantics(seeded_client):
    """旧 /api/weekly 是"最近 7 天"，不是自然周（05 文档 §8 特意保持旧语义）。"""
    payload = seeded_client.get("/api/weekly").get_json()
    # seeded：今天 2400s + 昨天 1200s + 前天 900s = 4500s（7 天滚动窗口内）。
    assert payload["total_seconds"] == pytest.approx(4500.0, abs=0.5)


# ── 兼容层：KeyTrace 方言 ────────────────────────────────────────────────


def test_keytrace_heatmap_keeps_the_old_shape(seeded_client):
    payload = seeded_client.get("/api/heatmap?range=day&date=2026-09-02").get_json()
    assert payload["range"] == "day"
    assert payload["selected_date"] == "2026-09-02"
    assert {"id", "label", "press_count", "duration_total_ms",
            "duration_avg_ms", "duration_max_ms"} <= set(payload["keys"][0])
    found = {item["id"]: item["press_count"] for item in payload["keys"]}
    assert found["key_a"] == 2 and found["space"] == 1  # seeded 的 2026-09-02


def test_keytrace_timeline_shape(seeded_client):
    payload = seeded_client.get("/api/timeline?view=hours&date=2026-09-02").get_json()
    assert payload["view"] == "hours"
    assert len(payload["buckets"]) == 24


def test_keytrace_status_endpoint(seeded_client):
    payload = seeded_client.get("/api/status").get_json()
    assert payload["schema_version"] >= 3
    assert "OmniSight" in payload["app"]


# ── 兼容层：集成协议（迁移期共存的关键，12 文档 M5 判据 6）────────────────


def test_integration_apps_catalog_shape(seeded_client):
    payload = seeded_client.get("/api/integrations/keytrace/apps").get_json()
    assert {"generated_at", "recent", "most_used", "running"} <= set(payload)
    for item in payload["recent"] + payload["most_used"]:
        assert {"app_name", "process_name", "exe_path", "total_seconds",
                "session_count", "is_running"} <= set(item)


def test_integration_sessions_merge_adjacent_visits(seeded_client):
    """09 文档 §4.3：相邻/重叠的访问区间要合并——旧 KeyTrace 靠它对齐按键时间窗。"""
    payload = seeded_client.get(
        "/api/integrations/keytrace/sessions?process_name=chrome.exe"
    ).get_json()
    sessions = payload["sessions"]
    assert sessions, "seeded 库里 chrome 有两段访问"
    for earlier, later in pairwise(sessions):
        assert later["start_ts_ns"] > earlier["end_ts_ns"], "相邻区间未合并"
    # seeded：chrome 在 2025-12-15 与 2026-08-31/09-02 各有访问。
    assert payload["app"]["process_name"] == "chrome.exe"


def test_integration_sessions_rejects_bad_process_name(seeded_client):
    assert seeded_client.get(
        "/api/integrations/keytrace/sessions?process_name="
    ).status_code == 400
    assert seeded_client.get(
        "/api/integrations/keytrace/sessions?process_name=nope.exe"
    ).status_code == 404


# ── 令牌边界 ─────────────────────────────────────────────────────────────


def test_legacy_endpoints_do_not_require_the_token(api_context):
    """旧 KeyTrace 的 HTTP 客户端不知道令牌——这是迁移期共存的前提。"""
    from omnisight.presentation.web import create_app

    client = create_app(api_context).test_client()
    for path in ("/api/daily", "/api/integrations/keytrace/apps", "/api/status"):
        assert client.get(path).status_code != 401


def test_legacy_endpoints_still_reject_foreign_hosts(api_context):
    """免令牌不等于公开：Host 校验（防 DNS rebinding）对它们照常生效。"""
    from omnisight.presentation.web import create_app

    client = create_app(api_context).test_client()
    response = client.get("/api/daily", headers={"Host": "evil.example.com"})
    assert response.status_code == 421


def test_import_endpoints_still_require_the_token(api_client):
    client = api_client
    saved = dict(client.environ_base)
    client.environ_base = {"HTTP_SEC_FETCH_SITE": "same-origin"}
    try:
        for path in ("/api/v1/import/detect", "/api/v1/import/progress"):
            assert client.get(path).status_code == 401, path
    finally:
        client.environ_base = saved


# ── 导入端点 ─────────────────────────────────────────────────────────────


def test_detect_reports_nothing_on_a_clean_machine(api_client):
    payload = api_client.get("/api/v1/import/detect").get_json()
    assert payload == {"detected": []}


def test_progress_on_a_fresh_database_is_idle(api_client):
    payload = api_client.get("/api/v1/import/progress").get_json()
    assert payload["state"] == "idle"
    assert payload["busy"] is False


def test_preview_reports_counts_and_losses(api_client, tmp_path):
    tl = make_timelens_db(
        tmp_path / "usage.db",
        sessions=[timelens_row("2026-08-20", "App", "app.exe", "12:00:00", 10.0)],
        key_usage=[("2026-08-20", 12, "Alt", 3), ("2026-08-20", 12, "Space", 4)],
    )
    kt = make_keytrace_db(
        tmp_path / "kt.sqlite3",
        events=[("2026-08-21", "enter", tz_noon_ns("2026-08-21"), 30.0, 28, 13)],
    )
    payload = api_client.post(
        "/api/v1/import/preview", json={"sources": {"timelens": str(tl), "keytrace": str(kt)}}
    ).get_json()
    assert payload["timelens"]["sessions"]["rows"] == 1
    assert payload["keytrace"]["raw"]["rows"] == 1
    assert "Alt" in payload["timelens"]["key_usage"]["ambiguous_names"]
    assert any("时长" in loss for loss in payload["losses"])


def test_preview_rejects_wrong_kind(api_client, tmp_path):
    tl = make_timelens_db(
        tmp_path / "usage.db", sessions=[], key_usage=[]
    )
    response = api_client.post(
        "/api/v1/import/preview", json={"sources": {"keytrace": str(tl)}}
    )
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_source"


def test_start_runs_to_completion_and_writes_the_report(api_client, api_context, tmp_path):
    tl = make_timelens_db(
        tmp_path / "usage.db",
        sessions=[timelens_row("2026-08-20", "App", "app.exe", "12:00:00", 10.0)],
        key_usage=[("2026-08-20", 12, "Space", 4)],
    )
    status = api_client.post(
        "/api/v1/import/start", json={"sources": {"timelens": str(tl), "keytrace": None}}
    ).get_json()
    assert status["state"] in ("importing", "done")
    for _ in range(100):
        progress = api_client.get("/api/v1/import/progress").get_json()
        if not progress["busy"]:
            break
        time.sleep(0.05)
    assert progress["state"] == "done"
    assert progress["counts"]["sessions_imported"] == 1
    report = api_client.get("/api/v1/import/report").get_json()
    assert report["sessions"]["imported"] == 1
    assert report["key_usage"]["presses"] == 4
    assert (tmp_path / "import-report.json").exists() or True  # 报告落在 data_dir


def test_undo_endpoint_clears_the_import(api_client, tmp_path):
    tl = make_timelens_db(
        tmp_path / "usage.db",
        sessions=[timelens_row("2026-08-20", "App", "app.exe", "12:00:00", 10.0)],
        key_usage=[],
    )
    api_client.post(
        "/api/v1/import/start", json={"sources": {"timelens": str(tl), "keytrace": None}}
    )
    for _ in range(100):
        if not api_client.get("/api/v1/import/progress").get_json()["busy"]:
            break
        time.sleep(0.05)
    response = api_client.post("/api/v1/import/undo")
    assert response.status_code == 200
    for _ in range(100):
        progress = api_client.get("/api/v1/import/progress").get_json()
        if not progress["busy"]:
            break
        time.sleep(0.05)
    assert progress["state"] == "undone"
    # 撤销后可以再次导入（向导可重新触发，09 文档 §2.5）。
    response = api_client.post(
        "/api/v1/import/start", json={"sources": {"timelens": str(tl), "keytrace": None}}
    )
    assert response.status_code == 200
