"""首次运行说明（08 文档 §6.1、12 文档 M6 判据 4/5）。

核心断言是**一致性**："会记录"与"不会记录"两张清单由能力与配置推导——同一项
绝不允许同时出现在两边，也不允许两边都不出现（用户会以为这项数据不存在）。
写死的文案在配置变化时就会撒谎，这套推导不会。
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from pathlib import Path

from fakes import FakeClock
from omnisight.adapters.ports import Capabilities
from omnisight.core.config import default_config
from omnisight.services import Services
from omnisight.storage.database import Database

WHEN = datetime(2026, 9, 2, 10, 0, 0)


def build_services(database: Database, *, config=None, capabilities: Capabilities) -> Services:
    return Services.build(
        database=database,
        config=config or default_config(),
        capabilities=capabilities,
        config_path=Path("config.json"),
        clock=FakeClock(WHEN),
    )


def test_acknowledged_is_none_until_the_user_confirms(database: Database, full_capabilities):
    services = build_services(database, capabilities=full_capabilities)
    assert services.onboarding.acknowledged() is None
    assert services.onboarding.describe()["required"] is True


def test_acknowledge_persists_and_clears_the_requirement(database: Database, full_capabilities):
    services = build_services(database, capabilities=full_capabilities)
    stamp = services.onboarding.acknowledge()
    assert stamp is not None
    assert services.onboarding.acknowledged() == stamp
    assert services.onboarding.describe()["required"] is False


def test_acknowledgement_survives_a_restart_and_is_shared_across_browsers(
    database: Database, full_capabilities
):
    """状态在数据库（``meta`` 表）而不是浏览器的 localStorage：换浏览器不该被再问一次
    （API 模块文档的立论）。两个服务实例模拟两次进程启动。"""
    build_services(database, capabilities=full_capabilities).onboarding.acknowledge()
    again = build_services(database, capabilities=full_capabilities)
    assert again.onboarding.describe()["required"] is False


def test_an_older_acknowledgement_requires_the_new_notice(database: Database, full_capabilities):
    """``ONBOARDING_VERSION`` 提升后旧的确认失效——改到"用户该重新读一遍"的程度时
    必须如此，否则新加的承诺永远到不了老用户眼前。"""
    database.meta_set("onboarding_ack", "2026-01-01T00:00:00+08:00")
    database.meta_set("onboarding_ack_version", "0")
    services = build_services(database, capabilities=full_capabilities)
    assert services.onboarding.acknowledged() is None
    assert services.onboarding.describe()["required"] is True


def test_records_and_not_records_are_consistent_across_every_switch(
    database: Database, full_capabilities
):
    """四种开关组合（原始事件 × 窗口标题）下，同一数据项永远恰好出现在一边。"""
    base = default_config()
    for raw in (True, False):
        for titles in (True, False):
            config = replace(
                base,
                capture=replace(base.capture, store_raw_key_events=raw),
                privacy=replace(base.privacy, record_window_titles=titles),
            )
            payload = build_services(
                database, capabilities=full_capabilities, config=config
            ).onboarding.describe()
            recorded = {item["code"] for item in payload["records"]}
            excluded = {item["code"] for item in payload["not_records"]}
            assert not recorded & excluded, (raw, titles, recorded & excluded)
            for code in ("raw_key_events", "window_titles"):
                # 恰好出现在一边：既不同时在，也不两边都没有。
                assert (code in recorded) != (code in excluded), (raw, titles, code)


def test_l4_and_titles_move_between_lists_as_config_changes(database: Database, full_capabilities):
    """开着就出现在"会记录"（如实暴露），关掉就出现在"不会记录"。"""
    base = default_config()
    on = build_services(
        database,
        capabilities=full_capabilities,
        config=replace(
            base,
            capture=replace(base.capture, store_raw_key_events=True),
            privacy=replace(base.privacy, record_window_titles=True),
        ),
    ).onboarding.describe()
    assert "raw_key_events" in {item["code"] for item in on["records"]}
    assert "window_titles" in {item["code"] for item in on["records"]}
    assert "raw_key_events" not in {item["code"] for item in on["not_records"]}

    off = build_services(
        database,
        capabilities=full_capabilities,
        config=replace(
            base,
            capture=replace(base.capture, store_raw_key_events=False),
            privacy=replace(base.privacy, record_window_titles=False),
        ),
    ).onboarding.describe()
    assert "raw_key_events" in {item["code"] for item in off["not_records"]}
    assert "window_titles" in {item["code"] for item in off["not_records"]}
    assert "raw_key_events" not in {item["code"] for item in off["records"]}


def test_raw_events_entry_states_the_recovery_risk_plainly(database: Database, full_capabilities):
    """08 文档 §2 的立场：原始事件可还原文本这一点必须在最需要被信任的地方说出来。"""
    payload = build_services(database, capabilities=full_capabilities).onboarding.describe()
    entry = next(item for item in payload["records"] if item["code"] == "raw_key_events")
    assert "还原" in entry["detail"]


def test_keyboard_capability_off_removes_the_key_entry_entirely(
    database: Database, full_capabilities
):
    degraded = replace(full_capabilities, keyboard=False, foreground=False)
    payload = build_services(database, capabilities=degraded).onboarding.describe()
    codes = {item["code"] for item in payload["records"]}
    assert "key_counts" not in codes and "app_usage" not in codes


def test_platform_notice_names_windows_only_and_tier(
    database: Database, full_capabilities
):
    """12 文档 M6 判据 5：明确"当前仅支持 Windows"，不含糊其辞。"""
    payload = build_services(database, capabilities=full_capabilities).onboarding.describe()
    platform = payload["platform"]
    assert platform["id"] == "windows"
    assert platform["tier"] == 1
    assert "只支持 Windows" in platform["notice"]
    assert "尚未" in platform["notice"] or "规划" in platform["notice"]


def test_pause_and_documents_sections_are_present(database: Database, full_capabilities):
    payload = build_services(database, capabilities=full_capabilities).onboarding.describe()
    assert payload["pause"]["tray_item"] == "暂停记录"
    assert set(payload["paths"]) == {"database", "data_dir", "logs_dir", "config", "portable"}
    documents = payload["documents"]
    assert documents["privacy"].endswith("docs/privacy.md")
    assert documents["faq"].endswith("docs/faq.md")


def test_documents_referenced_by_onboarding_actually_exist(database: Database, full_capabilities):
    """首启说明引用的文档必须真的在仓库里——链接指向不存在的文件等于没有承诺。"""
    payload = build_services(database, capabilities=full_capabilities).onboarding.describe()
    root = Path(__file__).resolve().parents[2]
    for key in ("privacy", "faq"):
        assert (root / payload["documents"][key]).is_file(), payload["documents"][key]


def test_describe_reflects_the_current_database_path(database: Database, full_capabilities):
    """"数据在哪"一栏给的是真实路径，不是占位符——用户要靠它找到并删除数据。"""
    payload = build_services(database, capabilities=full_capabilities).onboarding.describe()
    assert Path(payload["paths"]["database"]) == database.path
    assert Path(payload["paths"]["data_dir"]) == database.path.parent
