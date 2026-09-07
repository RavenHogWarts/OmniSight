"""键盘后端的可选值按平台收窄（19 文档 A4）。

``config.KEYBOARD_BACKENDS`` 是跨平台**并集**——同一份 config.json 可能来自 Mac，
校验层必须放行别平台的合法值，配置才可携（见 ``test_config.py`` 的用例）。但设置页
的下拉**只列本平台实际接受的后端**，且写校验与下拉用同一份清单：否则 Windows 上会
列出 ``event_tap``、Mac 上列出 ``raw_input``，都是"选完就报错"的值——比不给这个
选项更糟。这与布局族 ``IMPLEMENTED_FAMILIES`` 的处理是同一个原则（layouts.py
模块注释第 3 条）。

真源是 ``Capabilities.keyboard_backends``，由各平台工厂在 ``detect()`` 里如实填。
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from omnisight.adapters.ports import Capabilities
from omnisight.core.config import default_config
from omnisight.services.context import ServiceContext
from omnisight.services.settings import SettingsService

#: 二级平台填好后应当长这样（macOS 工厂落在 B7；这里先钉住过滤行为本身）。
MAC_BACKENDS = ("auto", "event_tap", "pynput", "none")


@pytest.fixture
def make_service(database, tmp_path):
    def factory(capabilities: Capabilities) -> SettingsService:
        context = ServiceContext(
            database=database,
            config=default_config(),
            capabilities=capabilities,
        )
        return SettingsService(context, config_path=tmp_path / "config.json")

    return factory


def _backend_entry(service: SettingsService) -> dict:
    return service.describe()["settings"]["capture.keyboard_backend"]


def test_windows_dropdown_lists_only_windows_backends(make_service, full_capabilities):
    entry = _backend_entry(make_service(full_capabilities))
    assert set(entry["options"]) == {"auto", "raw_input", "pynput", "none"}
    assert "event_tap" not in entry["options"]
    assert "evdev" not in entry["options"]


def test_platform_vocabulary_swaps_with_capabilities(make_service, full_capabilities):
    """同一份 SPECS，能力集换成 Mac 的，下拉跟着换——过滤读的是数据，不是平台判断。"""
    mac = replace(full_capabilities, keyboard_backends=MAC_BACKENDS)
    entry = _backend_entry(make_service(mac))
    assert "event_tap" in entry["options"]
    assert "raw_input" not in entry["options"]


def test_writing_a_foreign_backend_is_rejected(make_service, full_capabilities, tmp_path):
    """下拉里没有的值，API 也不该能写进去——否则重启后采集起不来。"""
    service = make_service(full_capabilities)
    body = service.patch({"capture.keyboard_backend": "event_tap"})
    assert body["applied"] == []
    rejected = {item["field"]: item["code"] for item in body["rejected"]}
    assert rejected["capture.keyboard_backend"] == "invalid_value"
    # 配置文件没被碰：拒绝发生在落盘之前。
    assert not (tmp_path / "config.json").exists()


def test_writing_a_local_backend_still_applies(make_service, full_capabilities):
    service = make_service(full_capabilities)
    body = service.patch({"capture.keyboard_backend": "pynput"})
    assert body["requires_restart"] == ["capture.keyboard_backend"]
    assert body["rejected"] == []
