"""参数校验与错误形状（05 文档 §1.5、§9，12 文档 M2 的"参数模糊测试返回结构化 400"）。

**一条铁律：非法参数一律 400，绝不静默回退。** 旧 TimeLens 的 ``_validate_date`` 遇到坏
日期就悄悄用今天，于是用户以为自己看的是 8 月 3 日，实际是今天——比报错糟得多。

第二条：**没有任何输入能变成 500**。500 意味着我们没预料到，而参数全部来自 URL，任何人
都能试。这里的模糊测试因此遍历每一个端点 × 每一类坏值，只断言"不是 5xx 且形状正确"。
"""

from __future__ import annotations

import pytest

#: 所有带周期参数的端点。新加端点时必须补进来——漏一个就是漏一整片模糊测试。
PERIODIC_PATHS = (
    "/api/v1/overview",
    "/api/v1/usage/period",
    "/api/v1/usage/timeline",
    "/api/v1/usage/sessions",
    "/api/v1/keyboard/heatmap",
    "/api/v1/keyboard/timeline",
    "/api/v1/keyboard/ergonomics",
    "/api/v1/keyboard/keys/space",
    "/api/v1/insights/app-keyboard",
    "/api/v1/insights/rhythm",
    "/api/v1/apps",
    "/api/v1/export",
)

#: 每一类坏值都对应一个真实的失败模式，不是随机字符。
FUZZ_PARAMS = (
    ("date", "2026-13-01"),          # 月份越界
    ("date", "2026-02-30"),          # 日期不存在
    ("date", "20260831"),            # ISO 基本格式：fromisoformat 会接受，我们不接受
    ("date", "2026-W35-1"),          # ISO 周日期，同上
    ("date", "not-a-date"),
    ("date", "'; DROP TABLE app; --"),
    ("date", "2026-08-31T00:00"),    # 带时间部分
    ("range", "decade"),
    ("range", "DAY"),                # 大小写敏感：静默接受会让缓存键分叉
    ("range", "../../etc/passwd"),
    ("limit", "0"),
    ("limit", "-1"),
    ("limit", "999999"),
    ("limit", "abc"),
    ("limit", "1e3"),
    ("offset", "-5"),
    ("offset", "abc"),
    ("app_id", "0"),                 # 0 是"未知"哨兵，不是一个应用
    ("app_id", "-1"),
    ("app_id", "abc"),
    ("metric", "press_countt"),
    ("sort", "; DELETE FROM app"),
    ("view", "hour"),                # 正确值是 hours
    ("view", ""),
    ("include", "screen_time,nope"),
    ("format", "xml"),
    ("scope", "everything"),
    ("include_titles", "maybe"),
    ("granularity", "century"),
)


def _assert_structured_error(response, *, path: str, param: str, value: str):
    assert response.status_code == 400, f"{path}?{param}={value} → {response.status_code}"
    payload = response.get_json()
    assert payload is not None, "错误响应必须是 JSON"
    error = payload["error"]
    assert error["code"], "错误必须带机器可读的 code"
    assert error["message"], "错误必须带给人看的 message"
    # 带元字符的坏值绝不回显：它可能是攻击载荷，回显等于一个反射型注入面。
    # （``limit=0`` 这类值会作为合法区间的一部分出现在提示里，那是有用的，不算回显。）
    if any(char in value for char in "<>'\";&|"):
        assert value not in response.get_data(as_text=True), "错误消息回显了攻击载荷"


@pytest.mark.parametrize("path", PERIODIC_PATHS)
@pytest.mark.parametrize(("param", "value"), FUZZ_PARAMS)
def test_bad_parameters_never_produce_a_500(
    seeded_client, path: str, param: str, value: str
):
    """坏参数要么被这个端点拒绝（400），要么它根本不认识这个参数（200 忽略）。

    唯一不可接受的是 5xx。"这个端点不读 limit"是合法的，"读了 limit 但被 abc 噎死"不是。
    """
    response = seeded_client.get(f"{path}?{param}={value}")
    assert response.status_code < 500, f"{path}?{param}={value} 打出了 {response.status_code}"
    if response.status_code == 400:
        _assert_structured_error(response, path=path, param=param, value=value)


@pytest.mark.parametrize("bad", ["2026-13-01", "not-a-date", "2026-02-30", "20260831"])
def test_invalid_date_is_rejected_rather_than_silently_defaulting(seeded_client, bad: str):
    response = seeded_client.get(f"/api/v1/overview?date={bad}")
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_date"
    assert response.get_json()["error"]["field"] == "date"


def test_empty_parameter_means_default_not_an_error(seeded_client):
    """``?date=`` 与不传等价，走默认值分支——这是刻意的，不是漏洞。"""
    assert seeded_client.get("/api/v1/overview?date=").status_code == 200
    assert seeded_client.get("/api/v1/usage/period?limit=&offset=").status_code == 200


def test_invalid_range_names_the_field_and_lists_the_options(seeded_client):
    error = seeded_client.get("/api/v1/overview?range=decade").get_json()["error"]
    assert error["code"] == "invalid_range"
    assert error["field"] == "range"
    assert "week" in error["message"], "要告诉用户合法取值是什么"


def test_custom_range_requires_both_ends(seeded_client):
    error = seeded_client.get(
        "/api/v1/overview?range=custom&start=2026-09-01"
    ).get_json()["error"]
    assert error["code"] == "invalid_param"
    assert error["field"] == "end"


def test_custom_range_rejects_a_reversed_interval(seeded_client):
    error = seeded_client.get(
        "/api/v1/overview?range=custom&start=2026-09-02&end=2026-09-01"
    ).get_json()["error"]
    assert error["field"] == "start"


def test_custom_range_is_capped_at_the_retention_ceiling(seeded_client):
    response = seeded_client.get(
        "/api/v1/overview?range=custom&start=2000-01-01&end=2026-09-02"
    )
    assert response.status_code == 400
    assert response.get_json()["error"]["field"] == "end"


def test_sql_injection_shaped_key_id_is_rejected_and_the_tables_survive(seeded_client):
    """全部查询都是参数化的；这条用例固定住"以后也不许改成拼字符串"。"""
    response = seeded_client.get("/api/v1/keyboard/keys/'; DROP TABLE app; --")
    assert response.status_code == 400
    assert response.get_json()["error"]["field"] == "key_id"
    # 表还在：下一次请求仍能正常返回。
    assert seeded_client.get("/api/v1/status").status_code == 200
    assert seeded_client.get("/api/v1/apps?range=day").get_json()["apps"]


def test_unknown_but_well_formed_key_id_is_an_empty_result_not_an_error(seeded_client):
    """``key_f24`` 合法但没人按过。空结果与非法输入必须是两种响应。"""
    payload = seeded_client.get("/api/v1/keyboard/keys/key_f24?range=day").get_json()
    assert payload["totals"]["press_count"] == 0
    assert payload["by_app"] == []
    # 不在任何布局里也要如实说明，而不是假装它是一个普通键。
    assert payload["key"]["in_layout"] is False


def test_unknown_app_id_is_404_not_500(seeded_client):
    assert seeded_client.get("/api/v1/apps/999999").status_code == 404


def test_unimplemented_layout_family_lists_the_options(seeded_client):
    """静默换成别的族会让"我明明选了 JIS"变成一个无法排查的问题。"""
    response = seeded_client.get("/api/v1/keyboard/layout?family=jis106")
    assert response.status_code == 400
    error = response.get_json()["error"]
    assert error["field"] == "family"
    assert "ansi104" in error["message"]


def test_unknown_route_returns_a_structured_error(seeded_client):
    assert seeded_client.get("/api/v1/nope").get_json()["error"]["code"] == "not_found"
