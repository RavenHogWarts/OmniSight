"""配置加载与校验。

这些用例固定的是三条设计决策，而不是实现细节：非法值一律报错（不静默回退）、
非回环监听地址一律拒绝、未知键保留不丢。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from omnisight.core import config as cfgmod


def test_default_config_is_valid_and_loopback():
    cfg = cfgmod.default_config()
    assert cfg.server.host in cfgmod.LOOPBACK_HOSTS
    assert cfg.server.port == 6100


def test_window_titles_default_off():
    """08 文档 §2.1：标题的隐私敏感度远高于进程名，而统计价值低。"""
    assert cfgmod.default_config().privacy.record_window_titles is False


def test_missing_file_generates_default(tmp_path: Path):
    path = tmp_path / "config.json"
    cfg, warnings = cfgmod.load(path)
    assert path.exists()
    assert cfg == cfgmod.default_config()
    assert any("默认配置" in w for w in warnings)


@pytest.mark.parametrize(
    "payload,expected_field",
    [
        ('{"server": {"host": "0.0.0.0"}}', "server.host"),
        ('{"server": {"host": "192.168.1.10"}}', "server.host"),
        ('{"server": {"port": 80}}', "server.port"),
        ('{"server": {"port": 70000}}', "server.port"),
        ('{"capture": {"foreground_poll_seconds": 0.1}}', "capture.foreground_poll_seconds"),
        ('{"capture": {"idle_threshold_seconds": 5}}', "capture.idle_threshold_seconds"),
        ('{"capture": {"keyboard_backend": "magic"}}', "capture.keyboard_backend"),
        ('{"capture": {"paused": "yes"}}', "capture.paused"),
        ('{"storage": {"raw_event_retention_days": -1}}', "storage.raw_event_retention_days"),
        ('{"ui": {"theme": "neon"}}', "ui.theme"),
        ('{"ui": {"heat": "rainbow"}}', "ui.heat"),
        ('{"ui": {"default_view": "hourly"}}', "ui.default_view"),
        ('{"ui": {"keyboard_layout": "ergodox"}}', "ui.keyboard_layout"),
        ('{"ui": {"settings_surface": "popup"}}', "ui.settings_surface"),
        ('{"ui": {"timezone": "Mars/Olympus"}}', "ui.timezone"),
        ('{"privacy": {"excluded_processes": "code.exe"}}', "privacy.excluded_processes"),
    ],
)
def test_invalid_values_are_rejected_not_silently_defaulted(payload, expected_field):
    """旧 TimeLens 的 ``_validate_date`` 会静默回退，掩盖 bug 也掩盖用户意图。"""
    with pytest.raises(cfgmod.ConfigError) as exc:
        cfgmod.loads(payload)
    assert exc.value.field_path == expected_field


def test_syntax_error_reports_position_and_does_not_touch_file(tmp_path: Path):
    path = tmp_path / "config.json"
    path.write_text('{"server": {', encoding="utf-8")
    before = path.read_bytes()
    with pytest.raises(cfgmod.ConfigError) as exc:
        cfgmod.load(path)
    assert "语法错误" in str(exc.value)
    assert path.read_bytes() == before


def test_unknown_top_level_keys_survive_a_round_trip():
    """旧版程序打开新版配置时不能丢掉未识别的设置。"""
    cfg, warnings = cfgmod.loads('{"version": 1, "future_feature": {"enabled": true}}')
    assert cfg.unknown == {"future_feature": {"enabled": True}}
    assert not warnings
    assert json.loads(cfgmod.dumps(cfg))["future_feature"] == {"enabled": True}


def test_unknown_section_keys_are_reported():
    _, warnings = cfgmod.loads('{"capture": {"typo_here": 1}}')
    assert any("capture.typo_here" in w for w in warnings)


def test_newer_config_version_warns_but_loads():
    cfg, warnings = cfgmod.loads('{"version": 99}')
    assert cfg.version == cfgmod.CONFIG_VERSION
    assert any("高于本程序支持" in w for w in warnings)


def test_excluded_processes_are_normalised():
    cfg, _ = cfgmod.loads('{"privacy": {"excluded_processes": ["Code.EXE", "code.exe", "  "]}}')
    assert cfg.privacy.excluded_processes == ("code.exe",)


def test_save_is_atomic_and_leaves_no_temp_file(tmp_path: Path):
    path = tmp_path / "config.json"
    cfgmod.save(path, cfgmod.default_config())
    assert path.exists()
    assert list(tmp_path.iterdir()) == [path]


def test_dashboard_url_includes_token():
    cfg = cfgmod.default_config()
    assert cfg.dashboard_url("abc") == "http://127.0.0.1:6100/?token=abc"
    assert cfg.dashboard_url() == "http://127.0.0.1:6100/"
