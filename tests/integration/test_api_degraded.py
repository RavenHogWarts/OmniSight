"""空数据与能力缺失下的行为（05 文档 §1.4 结尾、11 文档 §4.3、12 文档 M2）。

这两条路径是最少被人工走到的，也是最容易 500 的：

* **空库**是每个新装用户的第一屏。除零、``max()`` on empty、``None`` 参与算术都藏在这里。
* **能力缺失不是错误**。当前环境不支持应用归因（Wayland 会话）时，应用维度接口仍要返回
  200 与结构完整的空数据，并在 ``coverage.gaps`` 里说明原因——因为这些接口在**历史数据里
  可能是有值的**（用户上周还在 X11 上），周期查询不能因"今天的能力"而整体失败。
"""

from __future__ import annotations

import pytest
from test_api_privacy import _readable_paths

from seeded import BLIND_DAY

RANGES = ("day", "week", "month", "year", "total", "custom")


def _path_with_range(path: str, range_name: str) -> str:
    joiner = "&" if "?" in path else "?"
    if range_name == "custom":
        return f"{path}{joiner}range=custom&start=2026-08-01&end=2026-09-02"
    return f"{path}{joiner}range={range_name}"


# ── 空库 ────────────────────────────────────────────────────────────────
#: 空库上不返回 200 的两个合法例外：那个应用真的不存在（404），以及它没有图标（204）。
#: 其余端点一律要给结构完整的 200。
_ALLOWED = {
    "/api/v1/apps/1": {200, 404},
    "/api/v1/apps/1/icon": {200, 204, 404},
}


def _allowed_for(path: str) -> set[int]:
    for prefix, codes in sorted(_ALLOWED.items(), key=lambda item: -len(item[0])):
        if path.startswith(prefix):
            return codes
    return {200}


@pytest.mark.parametrize("range_name", RANGES)
def test_an_empty_database_returns_well_formed_payloads_not_500(
    api_client, api_context, range_name: str
):
    from omnisight.presentation.web import create_app

    for path in _readable_paths(create_app(api_context)):
        response = api_client.get(_path_with_range(path, range_name))
        assert response.status_code in _allowed_for(path), f"{path} 在空库上 {response.status_code}"


def test_empty_overview_is_all_zeros_with_a_complete_shape(api_client):
    payload = api_client.get("/api/v1/overview?range=day").get_json()
    assert payload["screen_time"]["total_seconds"] == 0
    assert payload["keyboard"]["total_presses"] == 0
    assert payload["top_apps"] == []
    assert payload["categories"] == []
    assert len(payload["trend"]["buckets"]) == 24, "空库也要有 24 个桶，否则图表画不出坐标轴"


def test_empty_heatmap_still_draws_a_full_keyboard(api_client):
    """一张缺格的键盘比一张全冷的键盘更让人困惑。"""
    payload = api_client.get("/api/v1/keyboard/heatmap?range=day").get_json()
    assert len(payload["keys"]) == 104
    assert payload["totals"]["press_count"] == 0
    assert payload["scale"] == {"min": 0, "max": 0, "p95": 0, "metric": "press_count"}


def test_empty_status_reports_no_data_range_rather_than_a_fake_one(api_client):
    payload = api_client.get("/api/v1/status").get_json()
    assert payload["data_range"] == {"min_date": None, "max_date": None}
    assert payload["data_version"] >= 0


def test_empty_total_period_does_not_span_the_epoch(api_client):
    """``range=total`` 在空库上退化成今天。取 1970 会让趋势图画出两万个空桶。"""
    period = api_client.get("/api/v1/overview?range=total").get_json()["period"]
    assert period["start"] == period["truncated_end"] == "2026-09-02"


def test_empty_integrity_check_matches(api_client):
    payload = api_client.get("/api/v1/maintenance/integrity").get_json()
    assert payload["match"] is True
    assert set(payload["aggregates"].values()) == {0}


# ── 能力缺失 ────────────────────────────────────────────────────────────
def test_a_day_without_foreground_returns_200_and_a_gap_not_an_error(seeded_client):
    """12 文档 M2 的完成判据之一：``foreground_available = 0`` 的一天要 200 +
    ``coverage.gaps``，**不是 4xx，也不是一片 0**。"""
    response = seeded_client.get(
        f"/api/v1/usage/period?range=custom&start={BLIND_DAY}&end={BLIND_DAY}"
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["coverage"]["foreground_days"] == 0
    assert payload["coverage"]["recorded_days"] == 1
    gap = payload["coverage"]["gaps"][0]
    assert gap["missing"] == "foreground"
    assert "键盘统计仍然正常" in gap["message"]


def test_the_blind_day_still_reports_its_keyboard_data(seeded_client):
    """"没有应用归因"不等于"没有数据"。键盘那一半必须照常给出来。"""
    payload = seeded_client.get(
        f"/api/v1/keyboard/heatmap?range=custom&start={BLIND_DAY}&end={BLIND_DAY}"
    ).get_json()
    assert payload["totals"]["press_count"] == 7
    assert payload["coverage"]["gaps"][0]["missing"] == "foreground"


def test_the_blind_days_presses_are_unattributed_not_invisible(seeded_client):
    payload = seeded_client.get(
        f"/api/v1/insights/app-keyboard?range=custom&start={BLIND_DAY}&end={BLIND_DAY}"
    ).get_json()
    assert payload["apps"] == []
    assert payload["unattributed_presses"] == 7


def test_capability_gated_setting_is_rejected_with_the_capability_named(
    api_context, database
):
    """只有当请求的操作**此刻就无法执行**时才用 4xx，并且要说清是哪一项能力
    （05 文档 §1.4）。"""
    from dataclasses import replace

    from omnisight.presentation.web import create_app

    api_context.capabilities = replace(api_context.capabilities, autostart=False)
    api_context.services.context.capabilities = api_context.capabilities
    client = create_app(api_context).test_client()
    client.environ_base["HTTP_X_OMNISIGHT_TOKEN"] = "test-token-value"
    client.environ_base["HTTP_SEC_FETCH_SITE"] = "same-origin"

    described = client.get("/api/v1/settings").get_json()["settings"]
    entry = described["system.autostart"]
    assert entry["available"] is False
    assert entry["unavailable_reason"], "不可用必须给出原因，否则界面只能显示一个灰开关"

    response = client.post("/api/v1/settings/autostart", json={"enabled": True})
    assert response.status_code == 422
    error = response.get_json()["error"]
    assert error["code"] == "capability_unavailable"
    assert error["capability"] == "autostart"


def test_icon_urls_are_omitted_when_the_platform_cannot_provide_icons(
    api_context, seeded
):
    """不返回一个注定 204 的地址：那会让每个应用都发一次无谓的请求（04 文档 §6）。"""
    from dataclasses import replace

    from omnisight.presentation.web import create_app

    api_context.capabilities = replace(api_context.capabilities, icons=False)
    api_context.services.context.capabilities = api_context.capabilities
    client = create_app(api_context).test_client()
    client.environ_base["HTTP_X_OMNISIGHT_TOKEN"] = "test-token-value"
    payload = client.get("/api/v1/usage/period?range=day").get_json()
    assert payload["apps"]
    assert all(app["icon_url"] is None for app in payload["apps"])
