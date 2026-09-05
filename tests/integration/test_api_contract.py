"""每个端点一条契约测试（11 文档 §4.1、12 文档 M2 的第一条完成判据）。

**断言具体数字，不只断言字段存在。** 只查形状的契约测试在聚合算错时照样全绿，而聚合
算错恰恰是这一层最可能出的错。数据来自 :mod:`seeded`，那里手算好了每个周期的预期值。

外壳（``period`` / ``coverage`` / ``data_version`` / ``generated_at`` / ``warnings``）由
05 文档 §1.4 规定，每个统计响应都必须有——因此它被单独参数化遍历，而不是在每个用例里
重复断言。
"""

from __future__ import annotations

import pytest

from seeded import BLIND_DAY, EXPECTED

#: 全部带周期外壳的统计端点。新增端点必须补进来。
ENVELOPE_PATHS = (
    "/api/v1/overview",
    "/api/v1/usage/period",
    "/api/v1/usage/sessions",
    "/api/v1/keyboard/heatmap",
    "/api/v1/keyboard/ergonomics",
    "/api/v1/keyboard/keys/key_a",
    "/api/v1/insights/app-keyboard",
    "/api/v1/insights/rhythm",
)
RANGES = ("day", "week", "month", "year", "total")


@pytest.mark.parametrize("path", ENVELOPE_PATHS)
def test_every_statistical_response_carries_the_documented_envelope(seeded_client, path: str):
    payload = seeded_client.get(f"{path}?range=week").get_json()
    assert set(payload["period"]) == {
        "range", "anchor", "start", "end", "truncated_end",
        "label", "is_current", "days", "granularity",
    }
    assert set(payload["coverage"]) == {
        "total_days", "recorded_days", "foreground_days",
        "keyboard_days", "key_position_days", "title_days", "gaps",
    }
    assert isinstance(payload["data_version"], int)
    assert payload["generated_at"].startswith("2026-09-02T22:15:03")
    assert payload["warnings"] == []


@pytest.mark.parametrize("range_name", RANGES)
def test_overview_totals_match_the_hand_computed_values(seeded_client, range_name: str):
    """首屏唯一的数据请求（05 文档 §2）。它算错等于整个产品算错。"""
    expected = EXPECTED[range_name]
    payload = seeded_client.get(f"/api/v1/overview?range={range_name}").get_json()
    assert payload["screen_time"]["total_seconds"] == expected.seconds
    assert payload["keyboard"]["total_presses"] == expected.presses


def test_overview_sections_can_be_trimmed(seeded_client):
    """轮询时只取变化的段，而不是每次重算整屏。"""
    payload = seeded_client.get("/api/v1/overview?range=day&include=screen_time").get_json()
    assert payload["included"] == ["screen_time"]
    assert "screen_time" in payload
    assert "top_apps" not in payload


def test_overview_top_apps_are_ranked_by_duration(seeded_client, seeded):
    apps = seeded_client.get("/api/v1/overview?range=day").get_json()["top_apps"]
    assert [app["app_id"] for app in apps] == [seeded.code, seeded.chrome]
    assert [app["seconds"] for app in apps] == [1800.0, 600.0]
    assert apps[0]["percent"] == 75.0
    assert apps[0]["seconds_formatted"] == "30分钟"


def test_overview_categories_sum_to_the_attributed_time(seeded_client):
    categories = seeded_client.get("/api/v1/overview?range=day").get_json()["categories"]
    assert sum(item["seconds"] for item in categories) == EXPECTED["day"].seconds
    assert sum(item["percent"] for item in categories) == pytest.approx(100.0, abs=0.2)


def test_overview_trend_has_one_bucket_per_hour_including_empty_ones(seeded_client):
    trend = seeded_client.get("/api/v1/overview?range=day").get_json()["trend"]
    assert trend["granularity"] == "hour"
    assert len(trend["buckets"]) == 24
    by_bucket = {item["bucket"]: item for item in trend["buckets"]}
    assert by_bucket["10"]["seconds"] == 1800.0
    assert by_bucket["03"]["seconds"] == 0.0  # 空桶必须在，不能跳过


@pytest.mark.parametrize("range_name", RANGES)
def test_overview_trend_buckets_carry_a_category_breakdown(seeded_client, range_name: str):
    """活动带上面板按类别堆叠（14 文档 §4.3）。

    **段之和必须等于柱高**：短一截的话用户看到的是"柱子上空了一块"，而没有任何线索
    指向"那一块是被排除的应用"。空桶给 ``{}`` 而不是省略这个键。
    """
    trend = seeded_client.get(f"/api/v1/overview?range={range_name}").get_json()["trend"]
    for bucket in trend["buckets"]:
        assert "categories" in bucket, f"{bucket['bucket']} 少了 categories"
        assert sum(bucket["categories"].values()) == pytest.approx(bucket["seconds"], abs=0.1)
        assert all(value > 0 for value in bucket["categories"].values()), "0 值不该占一个类别槽"
    assert any(bucket["categories"] for bucket in trend["buckets"]), "全是空桶，这条断言会假装成立"


@pytest.mark.parametrize("range_name", RANGES)
def test_overview_trend_total_matches_the_hero_number(seeded_client, range_name: str):
    """柱高之和 = 屏幕时间指标卡。

    改前 day/month/year 粒度走 ``bucket_totals``（整桶求和，不认识合并与排除），
    于是同一屏上柱子加起来会比英雄数值大一截。现在两边同源。
    """
    payload = seeded_client.get(f"/api/v1/overview?range={range_name}").get_json()
    total = sum(bucket["seconds"] for bucket in payload["trend"]["buckets"])
    assert total == pytest.approx(payload["screen_time"]["total_seconds"], abs=1.0)


#: range → (对照条粒度, 桶数)。年是"全部年份"，桶数随数据集，因此单独断言。
CONTEXT_SHAPES = (("day", "day", 7), ("week", "week", 8), ("month", "month", 12))


@pytest.mark.parametrize(("range_name", "grain", "count"), CONTEXT_SHAPES)
def test_overview_context_series_ends_at_the_current_period(
    seeded_client, range_name: str, grain: str, count: int
):
    """对照条 = 当前周期所在的上一档粒度序列（14 文档 §4.3）。

    序列以当前周期收尾，且**当前那根的高度必须等于英雄数值**——对不上的话"今天算多
    还是算少"这句话就是拿两套口径在比。
    """
    payload = seeded_client.get(f"/api/v1/overview?range={range_name}").get_json()
    context = payload["context"]
    assert context["grain"] == grain
    assert len(context["buckets"]) == count
    assert context["buckets"][-1]["bucket"] == context["current"], "序列该以当前周期收尾"
    current = next(item for item in context["buckets"] if item["bucket"] == context["current"])
    assert current["seconds"] == pytest.approx(payload["screen_time"]["total_seconds"], abs=1.0)
    assert current["presses"] == payload["keyboard"]["total_presses"]


def test_overview_context_series_for_year_covers_every_year_with_data(seeded_client):
    context = seeded_client.get("/api/v1/overview?range=year").get_json()["context"]
    assert context["grain"] == "year"
    assert context["current"] == "2026"
    years = [item["bucket"] for item in context["buckets"]]
    # 数据集里最早的一天在 2025（BLIND_DAY 那一段），因此两年都要在场且按序。
    assert years == sorted(years) == ["2025", "2026"]


@pytest.mark.parametrize("query", ("range=total", "range=custom&start=2026-09-01&end=2026-09-02"))
def test_overview_has_no_context_series_where_there_is_nothing_to_compare(seeded_client, query):
    """"全部"与自定义区间没有可比的同粒度序列，宁可整段缺席也不硬凑一条。"""
    payload = seeded_client.get(f"/api/v1/overview?{query}").get_json()
    assert "context" not in payload
    assert "context" in payload["included"], "段仍然被请求过，只是这两种 range 没有内容"


def test_overview_highlights_are_sentences_with_a_code(seeded_client):
    """每条结论都要能说出口径，因此带 ``code`` 让前端能定位文案与说明。"""
    highlights = seeded_client.get("/api/v1/overview?range=day").get_json()["highlights"]
    assert highlights
    assert all(item["code"] and item["text"] for item in highlights)


# ── /usage/* ────────────────────────────────────────────────────────────
@pytest.mark.parametrize("range_name", RANGES)
def test_usage_period_totals_match_the_hand_computed_values(seeded_client, range_name: str):
    payload = seeded_client.get(f"/api/v1/usage/period?range={range_name}").get_json()
    assert payload["total_seconds"] == EXPECTED[range_name].seconds
    assert sum(app["seconds"] for app in payload["apps"]) == EXPECTED[range_name].seconds


def test_usage_period_never_lists_the_unknown_app(seeded_client):
    """``app_id = 0`` 不是一个应用，是"前台未知"哨兵。它进排行等于凭空多出一个"应用"。"""
    for range_name in RANGES:
        payload = seeded_client.get(f"/api/v1/usage/period?range={range_name}").get_json()
        assert all(app["app_id"] != 0 for app in payload["apps"])


def test_usage_period_pagination_reports_the_untruncated_total(seeded_client):
    payload = seeded_client.get("/api/v1/usage/period?range=day&limit=1").get_json()
    assert len(payload["apps"]) == 1
    assert payload["pagination"] == {"limit": 1, "offset": 0, "total": 2}


@pytest.mark.parametrize("sort", ["seconds", "presses", "sessions", "name", "last_seen"])
def test_usage_period_sorting_is_stable_and_complete(seeded_client, sort: str):
    payload = seeded_client.get(f"/api/v1/usage/period?range=day&sort={sort}").get_json()
    assert len(payload["apps"]) == 2


def test_usage_period_can_sort_by_last_seen(seeded_client):
    """"最近用过的排前面"是选应用时最自然的顺序（16 文档 §A4 的第三件事）。

    ``/apps`` 早就支持这个排序键，``/usage/period`` 没有——于是应用视图的四种排序里
    唯独缺了它，而每一行都带着 ``last_seen_at``。
    """
    apps = seeded_client.get("/api/v1/usage/period?range=total&sort=last_seen").get_json()["apps"]
    stamps = [app["last_seen_at"] for app in apps]
    assert stamps == sorted(stamps, reverse=True)
    assert all(stamps), "每一行都该带 last_seen_at，否则这个排序键只是摆设"


@pytest.mark.parametrize(
    ("query", "expected_process"),
    [
        ("code", "code.exe"),        # 匹配进程名
        ("visual", "code.exe"),      # 匹配展示名，不区分大小写
        ("CHROME", "chrome.exe"),    # 大小写不敏感
    ],
)
def test_usage_period_filters_by_query_on_the_server(
    seeded_client, seeded, query, expected_process
):
    """服务端搜索（M4）：搜索结果与列表保持同一套周期口径，且能跨过单次取回上限。"""
    payload = seeded_client.get(
        f"/api/v1/usage/period?range=day&q={query}"
    ).get_json()
    assert [app["process_name"] for app in payload["apps"]] == [expected_process]
    assert payload["filtered_by"] == query
    assert payload["total_seconds"] == pytest.approx(payload["apps"][0]["seconds"])


def test_usage_period_query_with_no_match_is_an_empty_list_not_an_error(seeded_client):
    payload = seeded_client.get("/api/v1/usage/period?range=day&q=zzz").get_json()
    assert payload["apps"] == []
    assert payload["app_count"] == 0


def test_usage_period_states_the_kpm_denominator(seeded_client):
    """行内 KPM 的口径随响应下发（M4 判据 2 的后端半边）。"""
    payload = seeded_client.get("/api/v1/usage/period?range=day").get_json()
    assert "前台时长" in payload["kpm_basis"]


def test_usage_timeline_folds_the_same_hour_across_days(seeded_client, seeded):
    """"我一般几点在用什么"：跨多天时同一小时相加。"""
    payload = seeded_client.get("/api/v1/usage/timeline?range=week").get_json()
    hours = {item["hour"]: item for item in payload["hours"]}
    assert len(hours) == 24
    # 9 点：仅 9-01 的 code.exe（1200s）；10 点：仅 9-02 的 code.exe（1800s）
    assert hours[9]["total_seconds"] == 1200.0
    assert hours[10]["total_seconds"] == 1800.0
    assert hours[3]["total_seconds"] == 0.0


def test_usage_sessions_returns_visits_not_heartbeat_segments(seeded_client):
    """``granularity=visit``（默认）数的是"用了几次"，不是心跳切出来的段数。"""
    payload = seeded_client.get("/api/v1/usage/sessions?range=day").get_json()
    assert payload["pagination"]["total"] == 2
    assert {item["end_reason"] for item in payload["sessions"]} == {"switch"}
    assert [item["seconds"] for item in payload["sessions"]] == [600.0, 1800.0]


def test_usage_sessions_are_ordered_newest_first(seeded_client):
    starts = [
        item["start"]
        for item in seeded_client.get("/api/v1/usage/sessions?range=week").get_json()["sessions"]
    ]
    assert starts == sorted(starts, reverse=True)


def test_usage_sessions_can_be_filtered_by_app(seeded_client, seeded):
    payload = seeded_client.get(
        f"/api/v1/usage/sessions?range=week&app_id={seeded.chrome}"
    ).get_json()
    assert {item["app_id"] for item in payload["sessions"]} == {seeded.chrome}


# ── /keyboard/* ─────────────────────────────────────────────────────────
def test_keyboard_layout_is_the_single_source_of_key_positions(seeded_client):
    payload = seeded_client.get("/api/v1/keyboard/layout").get_json()
    assert payload["family"] == "ansi104"
    assert payload["available_families"] == ["ansi104", "iso105"]
    assert len(payload["rows"]) == 6
    assert payload["unit_hint"] == {"max_units": 23.0, "rows": 6}
    # 每个键位都自带宽度：前端不需要知道任何一个键有多宽。
    assert all("w" in slot for row in payload["rows"] for slot in row)


def test_keyboard_layout_can_be_requested_explicitly(seeded_client):
    payload = seeded_client.get("/api/v1/keyboard/layout?family=iso105").get_json()
    assert payload["family"] == "iso105"
    assert payload["source"] == "request_override"


def test_keyboard_heatmap_covers_every_layout_key_even_the_unpressed_ones(seeded_client):
    """没按过的键必须在结果里且 ``press_count = 0``——缺键会让前端画出一张缺格的键盘。"""
    payload = seeded_client.get("/api/v1/keyboard/heatmap?range=day").get_json()
    assert len(payload["keys"]) == 104
    by_id = {key["id"]: key for key in payload["keys"]}
    assert by_id["key_a"]["press_count"] == 2
    assert by_id["key_z"]["press_count"] == 0
    assert by_id["key_z"]["rank"] is None
    assert by_id["key_a"]["rank"] == 1


def test_keyboard_heatmap_totals_and_scale(seeded_client):
    payload = seeded_client.get("/api/v1/keyboard/heatmap?range=day").get_json()
    assert payload["totals"]["press_count"] == EXPECTED["day"].presses
    assert payload["totals"]["active_keys"] == 5
    # p95 归一而不是最大值归一：空格键往往是第二名的 3 倍，最大值归一会把其余键压成一片
    # 浅色（06 文档 §7）。
    assert payload["scale"]["p95"] > 0
    assert payload["scale"]["metric"] == "press_count"


def test_keyboard_heatmap_reports_keys_outside_the_layout_separately(seeded_client, database):
    """媒体键不在 ANSI104 里，但它被按过就必须能看到——静默丢弃等于总数对不上。"""
    payload = seeded_client.get("/api/v1/keyboard/heatmap?range=year").get_json()
    layout_ids = {key["id"] for key in payload["keys"]}
    orphans = {key["id"] for key in payload["orphan_keys"]}
    assert not (layout_ids & orphans)
    counted = sum(key["press_count"] for key in payload["keys"])
    counted += sum(key["press_count"] for key in payload["orphan_keys"])
    assert counted == payload["totals"]["press_count"]


@pytest.mark.parametrize("metric", ["press_count", "duration_total_ms", "duration_avg_ms"])
def test_keyboard_heatmap_supports_every_documented_metric(seeded_client, metric: str):
    payload = seeded_client.get(f"/api/v1/keyboard/heatmap?range=day&metric={metric}").get_json()
    assert payload["metric"] == metric
    assert payload["scale"]["metric"] == metric


def test_keyboard_heatmap_can_be_scoped_to_one_app(seeded_client, seeded):
    """★ 合并的最大收益点：合并前这个视图要跨进程 HTTP + 区间求交才能算出来。"""
    payload = seeded_client.get(
        f"/api/v1/keyboard/heatmap?range=day&app_id={seeded.code}"
    ).get_json()
    assert payload["scope"] == {
        "type": "app", "app_id": seeded.code, "display_name": "Visual Studio Code",
    }
    assert payload["totals"]["press_count"] == 4
    by_id = {key["id"]: key for key in payload["keys"]}
    assert by_id["key_b"]["press_count"] == 0  # key_b 是 chrome 里按的


def test_keyboard_timeline_returns_every_requested_view_in_one_request(seeded_client):
    """一次取回把 KeyTrace 首屏的 4 个请求合成 1 个（05 文档 §4）。"""
    payload = seeded_client.get(
        "/api/v1/keyboard/timeline?view=hours,days,months,years&range=day"
    ).get_json()
    assert set(payload["views"]) == {"hours", "days", "months", "years"}
    assert len(payload["views"]["hours"]["buckets"]) == 24
    assert len(payload["views"]["days"]["buckets"]) == 365
    assert len(payload["views"]["months"]["buckets"]) == 12
    assert len(payload["views"]["years"]["buckets"]) == 2  # 2025 与 2026


def test_keyboard_timeline_month_and_year_views_carry_real_numbers(seeded_client):
    """月/年桶曾经全是 0：桶列表按 ``custom`` 的日粒度生成，与月度数据永远匹配不上。

    "全 0 的图"在界面上和"那段时间没用过"长得一模一样，因此必须有一条断言盯着数值。
    """
    payload = seeded_client.get(
        "/api/v1/keyboard/timeline?view=months,years&range=day"
    ).get_json()
    months = {item["bucket"]: item["press_count"] for item in payload["views"]["months"]["buckets"]}
    assert months["2025-12"] == 5
    assert months["2026-09"] == 10  # 9-01 三次 + 9-02 七次
    years = {item["bucket"]: item["press_count"] for item in payload["views"]["years"]["buckets"]}
    assert years == {"2025": 5, "2026": 22}


def test_keyboard_timeline_hours_view_reflects_the_seeded_day(seeded_client):
    buckets = seeded_client.get(
        "/api/v1/keyboard/timeline?view=hours&range=day"
    ).get_json()["views"]["hours"]["buckets"]
    by_hour = {item["bucket"]: item["press_count"] for item in buckets}
    assert by_hour["10"] == 4
    assert by_hour["11"] == 1
    assert by_hour["12"] == 2  # 归到未知应用的按键仍然计入键盘总量


def test_key_detail_answers_both_directions(seeded_client, seeded):
    """"这个键被谁按了"是反向视图，合并之前完全无法回答。"""
    payload = seeded_client.get("/api/v1/keyboard/keys/key_a?range=week").get_json()
    assert payload["key"]["label"] == "A"
    assert payload["key"]["finger"] == "left_pinky"
    assert payload["key"]["row"] == "home"
    assert payload["key"]["in_layout"] is True
    assert payload["totals"]["press_count"] == 5  # 9-01 三次 + 9-02 两次
    assert [row["app_id"] for row in payload["by_app"]] == [seeded.code]
    assert payload["by_app"][0]["percent"] == 100.0
    assert len(payload["by_hour"]) == 24


def test_ergonomics_conserves_the_press_total_across_fingers_and_rows(seeded_client):
    """手指与键排是同一批按键的两种切法，各自求和都必须等于总数。"""
    payload = seeded_client.get("/api/v1/keyboard/ergonomics?range=day").get_json()
    total = payload["total_presses"]
    assert total == EXPECTED["day"].presses
    assert sum(item["press_count"] for item in payload["fingers"]) == total
    assert sum(item["press_count"] for item in payload["rows"]) == total
    assert payload["hands"]["left"] + payload["hands"]["right"] + payload["hands"]["neutral"] \
        == total


def test_ergonomics_states_the_modifier_basis(seeded_client):
    """"修饰键占比"数的是修饰键自身被按下的次数，不是和弦。口径必须随数据一起给出。"""
    ratio = seeded_client.get("/api/v1/keyboard/ergonomics?range=day").get_json()["modifier_ratio"]
    assert ratio["basis"] == "modifier_keys_pressed"
    assert ratio["with_modifier"] == 1  # control_left 一次
    assert ratio["plain"] == 6


# ── /insights/* ─────────────────────────────────────────────────────────
def test_app_keyboard_answers_the_question_the_merge_exists_to_answer(seeded_client, seeded):
    """"Code.exe 里按了几次 A"——合并前需要跨进程 HTTP + 区间求交，现在是一次点查。"""
    payload = seeded_client.get("/api/v1/insights/app-keyboard?range=day").get_json()
    apps = {app["app_id"]: app for app in payload["apps"]}
    code = apps[seeded.code]
    assert code["display_name"] == "Visual Studio Code"
    assert code["presses"] == 4
    assert code["seconds"] == 1800.0
    top = {item["id"]: item for item in code["top_keys"]}
    assert top["key_a"]["press_count"] == 2
    assert top["key_a"]["label"] == "A"
    assert top["control_left"]["label"] == "Ctrl"


def test_app_keyboard_keeps_the_press_total_conserved(seeded_client):
    """各应用之和 + 未归因 = 键盘总量。守恒被破坏说明有按键被静默丢掉了。"""
    payload = seeded_client.get("/api/v1/insights/app-keyboard?range=day").get_json()
    attributed = sum(app["presses"] for app in payload["apps"])
    assert attributed + payload["unattributed_presses"] == EXPECTED["day"].presses
    assert payload["unattributed_presses"] == EXPECTED["day"].unattributed


def test_app_keyboard_states_the_kpm_denominator(seeded_client):
    """"每分钟 56 键"取决于分母是"在线时长"还是"该应用前台时长"，能差好几倍。"""
    payload = seeded_client.get("/api/v1/insights/app-keyboard?range=day").get_json()
    assert "前台时长" in payload["kpm_basis"]


def test_app_keyboard_distribution_covers_all_four_profiles(seeded_client):
    payload = seeded_client.get("/api/v1/insights/app-keyboard?range=day").get_json()
    buckets = {item["id"]: item for item in payload["distribution"]["buckets"]}
    assert set(buckets) == {"input_heavy", "interactive", "passive", "idle_open"}
    assert sum(item["seconds"] for item in buckets.values()) == EXPECTED["day"].seconds


def test_rhythm_counts_visits_not_heartbeat_segments(seeded_client):
    """``switch_count`` 是注意力碎片化指标。数成段数会差两个数量级。"""
    payload = seeded_client.get("/api/v1/insights/rhythm?range=day").get_json()
    assert payload["switch_count"] == 2
    assert payload["longest_focus_minutes"] == 30.0
    assert [block["minutes"] for block in payload["focus_blocks"]] == [30.0, 10.0]


def test_rhythm_reports_minute_level_peaks_and_bounds(seeded_client):
    """``peak_kpm.at`` 与 ``active_hours`` 要求分钟精度——用小时均值充当峰值是在编数据。"""
    payload = seeded_client.get("/api/v1/insights/rhythm?range=day").get_json()
    assert payload["active_hours"] == {"first": "10:00", "last": "12:00", "span_hours": 2.0}
    assert payload["peak_kpm"]["value"] == 4
    assert payload["peak_kpm"]["at"].startswith("2026-09-02T10:00")


def test_rhythm_states_the_switch_basis(seeded_client):
    assert seeded_client.get("/api/v1/insights/rhythm?range=day").get_json()["switches_basis"]


def test_app_keyboard_gives_the_modifier_breakdown(seeded_client, seeded):
    """快捷键偏好（M4）：每个应用里哪个修饰键用得多。口径与 modifier_percent 一致。"""
    payload = seeded_client.get("/api/v1/insights/app-keyboard?range=day").get_json()
    code = next(app for app in payload["apps"] if app["app_id"] == seeded.code)
    assert code["modifier_breakdown"] == [
        {"id": "control_left", "label": "Ctrl", "press_count": 1, "percent": 100.0}
    ]


def test_rhythm_hourly_contrasts_typing_density_with_screen_time(seeded_client):
    """M4 节奏分析：一天中打字最密集的时段 vs 屏幕时间最长的时段。

    播种日：10 点 Code（30 分钟、4 键）、11 点 Chrome（10 分钟、1 键）、
    12 点无前台（2 键，不计入任何小时时长）。两个峰值都落在 10 点。
    """
    payload = seeded_client.get("/api/v1/insights/rhythm?range=day").get_json()
    hourly = {item["hour"]: item for item in payload["hourly"]}
    assert len(payload["hourly"]) == 24
    assert hourly[10] == {"hour": 10, "seconds": 1800.0, "presses": 4, "kpm": 0.1}
    assert hourly[11] == {"hour": 11, "seconds": 600.0, "presses": 1, "kpm": 0.1}
    # 无前台时段的按键仍在 hourly 里（presses 计入），但时长为 0，KPM 也为 0——
    # 不静默丢弃，也不拿它除出一个人为的 KPM。
    assert hourly[12] == {"hour": 12, "seconds": 0.0, "presses": 2, "kpm": 0.0}
    peaks = payload["hour_peaks"]
    assert peaks["typing"]["hour"] == 10
    assert peaks["screen"] == {"hour": 10, "seconds": 1800.0}
    assert peaks["same_hour"] is True
    assert "前台" in payload["hourly_basis"]
    assert "分钟" in peaks["typing_basis"]


def test_rhythm_hourly_ignores_undersized_hours_for_the_typing_peak(seeded_client):
    """只开过几分钟的应用若恰好一直在打字，算出的 KPM 会压过真正的密集时段。

    播种数据没有这样的小时，因此这里断言的是门槛常量本身——它承载的是口径决策。
    """
    from omnisight.services.insights import MIN_PEAK_HOUR_SECONDS

    assert MIN_PEAK_HOUR_SECONDS == 300.0


def test_overview_highlights_explain_their_basis(seeded_client):
    """M4 判据 4：每条自然语言结论都带着"怎么算出来的"。没有口径的结论不可验证。"""
    payload = seeded_client.get("/api/v1/overview?range=day").get_json()
    codes = {item["code"] for item in payload["highlights"]}
    assert codes  # 播种日至少有结论
    for item in payload["highlights"]:
        assert item["text"]
        assert item["basis"], f"{item['code']} 缺少计算口径"


def test_overview_highlights_include_the_rhythm_contrast(seeded_client):
    """播种日的打字峰值与屏幕峰值都在 10 点——结论应是"对齐"而不是"错位"。"""
    highlights = seeded_client.get("/api/v1/overview?range=day").get_json()["highlights"]
    contrast = [item for item in highlights if item["code"].startswith("rhythm_")]
    assert [item["code"] for item in contrast] == ["rhythm_aligned"]
    assert "10:00" in contrast[0]["text"]


def test_app_keyboard_on_a_day_without_foreground_reports_unattributed(seeded_client):
    """M4 判据 3：无归因的日子必须明说，不静默算成 0 个按键。

    BLIND_DAY 有 7 次按键但没有前台数据：应用列表为空、按键单列到
    ``unattributed_presses``、``coverage.gaps`` 指名缺的是 foreground。
    """
    payload = seeded_client.get(
        f"/api/v1/insights/app-keyboard?range=day&date={BLIND_DAY}"
    ).get_json()
    assert payload["apps"] == []
    assert payload["unattributed_presses"] == 7
    gaps = [gap for gap in payload["coverage"]["gaps"] if gap["missing"] == "foreground"]
    assert gaps and gaps[0]["from"] == BLIND_DAY


# ── /apps/* ─────────────────────────────────────────────────────────────
def test_app_list_includes_metadata_the_settings_page_needs(seeded_client, seeded):
    payload = seeded_client.get("/api/v1/apps?range=total").get_json()
    apps = {app["app_id"]: app for app in payload["apps"]}
    code = apps[seeded.code]
    assert code["process_name"] == "code.exe"
    assert code["category_source"] == "auto"
    assert code["excluded"] is False
    assert code["merged_into"] is None
    assert payload["categories"][0]["id"] == "development"


def test_app_detail_reports_every_period_and_the_keyboard_profile(seeded_client, seeded):
    payload = seeded_client.get(f"/api/v1/apps/{seeded.code}").get_json()
    assert payload["app"]["display_name"] == "Visual Studio Code"
    assert set(payload["totals"]) == {"day", "week", "month", "total"}
    assert payload["totals"]["day"]["seconds"] == 1800.0
    assert payload["totals"]["week"]["seconds"] == 3000.0  # 9-01 与 9-02
    assert payload["keyboard"]["top_keys"][0]["id"] == "key_a"
    assert payload["trend"]["granularity"] == "day"
    # 快捷键偏好（M4）：code 全期 7 键里 control_left 占 1 次 → 14.3%。
    assert payload["keyboard"]["modifier_percent"] == 14.3
    assert payload["keyboard"]["modifier_breakdown"] == [
        {"id": "control_left", "label": "Ctrl", "press_count": 1, "percent": 100.0}
    ]
    assert "前台时长" in payload["keyboard"]["kpm_basis"]
    assert payload["keyboard"]["profile_name"]


def test_patching_an_app_alias_takes_effect_immediately(seeded_client, seeded):
    """别名改完立刻生效，靠的是 ``data_version`` 换代而不是显式清缓存。"""
    before = seeded_client.get("/api/v1/usage/period?range=day").get_json()
    assert any(app["display_name"] == "Visual Studio Code" for app in before["apps"])
    response = seeded_client.patch(
        f"/api/v1/apps/{seeded.code}", json={"user_alias": "写代码"}
    )
    assert response.status_code == 200
    after = seeded_client.get("/api/v1/usage/period?range=day").get_json()
    assert any(app["display_name"] == "写代码" for app in after["apps"])
    assert after["data_version"] > before["data_version"]


def test_excluding_an_app_removes_it_from_rankings_but_keeps_the_keyboard_total(
    seeded_client, seeded
):
    """被排除应用的按键归到未知而不是被丢弃——键盘总量必须守恒（04 文档 §2.2）。"""
    total_before = seeded_client.get(
        "/api/v1/keyboard/heatmap?range=day"
    ).get_json()["totals"]["press_count"]
    seeded_client.patch(f"/api/v1/apps/{seeded.chrome}", json={"excluded": True})
    payload = seeded_client.get("/api/v1/usage/period?range=day").get_json()
    assert all(app["app_id"] != seeded.chrome for app in payload["apps"])
    total_after = seeded_client.get(
        "/api/v1/keyboard/heatmap?range=day"
    ).get_json()["totals"]["press_count"]
    assert total_after == total_before


def test_merging_two_apps_folds_their_numbers_into_the_root(seeded_client, seeded):
    """折叠只发生在服务层：聚合表里成员仍是独立的 ``app_id``（合并可以撤销）。"""
    response = seeded_client.post(
        f"/api/v1/apps/{seeded.chrome}/merge", json={"into_app_id": seeded.code}
    )
    assert response.status_code == 200
    payload = seeded_client.get("/api/v1/usage/period?range=day").get_json()
    apps = {app["app_id"]: app for app in payload["apps"]}
    assert set(apps) == {seeded.code}
    assert apps[seeded.code]["seconds"] == EXPECTED["day"].seconds
    assert apps[seeded.code]["presses"] == 5  # code 的 4 次 + chrome 的 1 次

    # 撤销之后两个应用重新分开——数据从来没有被真的合并过。
    assert seeded_client.delete(f"/api/v1/apps/{seeded.chrome}/merge").status_code == 200
    restored = seeded_client.get("/api/v1/usage/period?range=day").get_json()
    assert len(restored["apps"]) == 2


def test_icon_endpoint_returns_204_when_there_is_no_icon(seeded_client, seeded):
    """204 而不是 404：图标缺失不是"这个应用不存在"，前端据此画首字母色块。"""
    assert seeded_client.get(f"/api/v1/apps/{seeded.code}/icon").status_code == 204


# ── /settings、/export、/status ──────────────────────────────────────────
def test_settings_describe_every_option_with_availability(seeded_client):
    """能力缺失时设置项必须能说明"为什么不能改"，而不是给一个改了没反应的开关。"""
    payload = seeded_client.get("/api/v1/settings").get_json()
    settings = payload["settings"]
    assert "privacy.record_window_titles" in settings
    entry = settings["capture.keyboard_backend"]
    assert entry["available"] is True
    assert entry["applies"] == "restart"
    assert set(entry["options"]) == {"auto", "none", "pynput", "raw_input"}
    assert all("value" in item and "applies" in item for item in settings.values())


def test_the_settings_surface_is_an_ordinary_hot_enum(seeded_client):
    """点 ⚙ 是开抽屉还是跳到 `/settings`，由配置决定（18 文档 §2.1）。

    钉住的是"它是一条**普通的配置项**"：写死在前端的那一版只有"新标签页打开独立页面"
    一种，而那是三种取向里唯一没人选得掉的一种。热生效——改完下一次点击就该按新的走，
    没有任何理由要重启。
    """
    entry = seeded_client.get("/api/v1/settings").get_json()["settings"]["ui.settings_surface"]
    assert entry["applies"] == "hot"
    assert set(entry["options"]) == {"drawer", "page"}
    assert entry["value"] == "drawer", "默认开抽屉：改设置时仪表盘还在原地"
    applied = seeded_client.patch(
        "/api/v1/settings", json={"ui.settings_surface": "page"}
    ).get_json()
    assert applied["applied"] == ["ui.settings_surface"]
    rejected = seeded_client.patch(
        "/api/v1/settings", json={"ui.settings_surface": "popup"}
    ).get_json()["rejected"]
    assert rejected[0]["field"] == "ui.settings_surface"


def test_patching_a_hot_setting_applies_without_restart(seeded_client):
    response = seeded_client.patch(
        "/api/v1/settings", json={"ui.week_starts_on": 6}
    )
    assert response.status_code == 200
    body = response.get_json()
    assert "ui.week_starts_on" in body["applied"]
    assert body["requires_restart"] == []
    # 立刻生效：周起始日变了，week 区间就该跟着变。
    period = seeded_client.get("/api/v1/usage/period?range=week").get_json()["period"]
    assert period["start"] == "2026-08-30"


def test_patching_a_restart_setting_says_so_instead_of_pretending(seeded_client):
    body = seeded_client.patch(
        "/api/v1/settings", json={"capture.keyboard_backend": "pynput"}
    ).get_json()
    assert body["requires_restart"] == ["capture.keyboard_backend"]


def test_unknown_setting_is_rejected_not_silently_stored(seeded_client):
    """三桶响应：``applied`` / ``requires_restart`` / ``rejected``。被拒的项要说明是哪一项
    以及为什么——"保存成功但没生效"是设置页最难排查的一类问题。"""
    body = seeded_client.patch(
        "/api/v1/settings", json={"nope.nope": 1, "ui.week_starts_on": 99}
    ).get_json()
    rejected = {item["field"]: item for item in body["rejected"]}
    assert rejected["nope.nope"]["code"] == "unknown_setting"
    assert rejected["ui.week_starts_on"]["code"] == "out_of_range"
    assert all(item["message"] for item in body["rejected"])
    assert body["applied"] == []


@pytest.mark.parametrize("scope", ["usage", "keyboard", "sessions", "apps"])
def test_export_covers_every_scope_in_both_formats(seeded_client, scope: str):
    csv = seeded_client.get(f"/api/v1/export?scope={scope}&range=day&format=csv")
    assert csv.status_code == 200
    assert csv.headers["Content-Type"].startswith("text/csv")
    assert "attachment" in csv.headers["Content-Disposition"]
    body = csv.get_data()
    assert body.startswith(b"\xef\xbb\xbf"), "缺 BOM 的 CSV 在 Excel 里是乱码"

    payload = seeded_client.get(f"/api/v1/export?scope={scope}&range=day&format=json").get_json()
    assert payload["scope"] == scope
    assert isinstance(payload["rows"], list)


def test_status_reports_what_the_ui_needs_to_decide_what_to_show(seeded_client):
    payload = seeded_client.get("/api/v1/status").get_json()
    assert payload["data_range"] == {"min_date": "2025-12-15", "max_date": "2026-09-02"}
    assert payload["capabilities"]["icons"] is True
    assert payload["degraded"] == []
    assert payload["capture"]["keyboard"]["running"] is False  # 契约测试不起采集


def test_maintenance_integrity_cross_checks_every_press_aggregate(seeded_client):
    """八张表存的是同一个事实的八种切法。对不上说明某条 upsert 漏了——界面上看不出来。"""
    payload = seeded_client.get("/api/v1/maintenance/integrity").get_json()
    assert payload["match"] is True
    assert set(payload["aggregates"]) >= {
        "agg_key_day", "agg_key_total", "agg_key_hour", "agg_key_app_day",
        "agg_app_key_total", "agg_app_day", "agg_press_hour", "agg_press_minute",
    }
    assert set(payload["aggregates"].values()) == {EXPECTED["total"].presses}
