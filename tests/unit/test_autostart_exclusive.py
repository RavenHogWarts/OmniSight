"""两条开机自启机制的互斥与如实上报（10 文档 §4、§5.3）。

普通自启（注册表 ``Run`` 项）与「登录时以管理员身份启动」（``/RL HIGHEST`` 登录任务）是
两套机制：同时开着会在登录时启动两个实例，而"哪一个先起来"决定了这次是不是管理员模式
——那不该由竞速决定。互斥只能在**同时看得到两个端口**的服务层维护。

这里真正钉住的是另一件事：任何一条机制开着时，界面都不许显示"开机自启：关"。谎报比
功能缺失更糟，而这个功能天生就爱谎报——它把自启搬到了另一个操作系统机制上。

真正跑 ``schtasks`` 的那一半在 ``tests/adapters/test_logon_task.py``。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from omnisight.core.config import default_config
from omnisight.core.lifecycle import Lifecycle
from omnisight.services.context import ServiceContext
from omnisight.services.settings import CapabilityMissing, SettingsService


class FakePlain:
    """注册表自启项（:class:`~omnisight.adapters.ports.AutostartControl`）。"""

    def __init__(self, enabled: bool = False, log: list | None = None) -> None:
        self.enabled = enabled
        self.log = log if log is not None else []

    def is_enabled(self) -> bool:
        return self.enabled

    def set_enabled(self, enabled: bool) -> None:
        self.log.append(("plain", enabled))
        self.enabled = enabled


class FakeTask:
    """登录任务端口。``present`` 与 ``enabled`` 分开：一个指向旧路径的任务两者不同。"""

    def __init__(
        self,
        enabled: bool = False,
        *,
        present: bool | None = None,
        reason: str = "",
        log: list | None = None,
    ) -> None:
        self.enabled = enabled
        self.present = enabled if present is None else present
        self.reason = reason
        self.log = log if log is not None else []

    def is_enabled(self) -> bool:
        return self.enabled

    def is_present(self) -> bool:
        return self.present

    def change_blocked_reason(self) -> str:
        return self.reason

    def set_enabled(self, enabled: bool) -> None:
        if self.reason:
            raise AssertionError("闸门挡住时不该走到适配器")
        self.log.append(("task", enabled))
        self.enabled = enabled
        self.present = enabled


@pytest.fixture
def build(database, full_capabilities, tmp_path):
    """按需装一个只关心自启的设置服务。``task=None`` = 本平台没有这条机制。"""

    def factory(plain: object = None, task: object = None) -> SettingsService:
        adapters = SimpleNamespace()
        if plain is not None:
            adapters.autostart = plain
        if task is not None:
            adapters.autostart_elevated = task
        context = ServiceContext(
            database=database,
            config=default_config(),
            capabilities=full_capabilities,
            adapters=adapters,
        )
        return SettingsService(context, config_path=tmp_path / "config.json")

    return factory


def _entries(service: SettingsService) -> dict:
    return service.describe()["settings"]


# ── 读：设置页那两行 ────────────────────────────────────────────────────
def test_the_plain_row_says_when_the_logon_task_has_taken_over(build):
    """开着登录任务时注册表项确实是关的，但"开机自启：关"是假话——程序每次登录都起来。"""
    entries = _entries(build(plain=FakePlain(False), task=FakeTask(True)))
    assert entries["system.autostart"]["value"] is False
    assert "接管" in entries["system.autostart"]["note"]
    assert entries["system.autostart_elevated"]["value"] is True


def test_the_elevated_row_is_absent_where_the_mechanism_does_not_exist(build):
    """macOS / Linux 上不显示那一行：一个永远灰着的开关只会招来"为什么点不了"。"""
    assert "system.autostart_elevated" not in _entries(build(plain=FakePlain()))


def test_a_blocked_switch_shows_the_reason_and_still_explains_itself(build):
    """这个开关多数时候是灰的（要装到 Program Files、要先提权）。只给原因不够——用户
    还不知道它本来是干什么的；只给说明更糟——他不知道下一步该做什么。"""
    entry = _entries(build(plain=FakePlain(), task=FakeTask(reason="需要先安装到 Program Files")))[
        "system.autostart_elevated"
    ]
    assert entry["available"] is False
    assert entry["unavailable_reason"] == "需要先安装到 Program Files"
    assert "管理员" in entry["note"]


def test_a_stale_task_is_called_out_instead_of_looking_absent(build):
    """任务存在但指向别处（或没提权）时开关是关的，可它并不是"没有这个任务"——重新打开
    会用 /F 覆盖掉那一个，这件事要先说。"""
    entry = _entries(build(plain=FakePlain(), task=FakeTask(False, present=True)))[
        "system.autostart_elevated"
    ]
    assert entry["value"] is False
    assert "改写" in entry["note"]


# ── 写：互斥 ────────────────────────────────────────────────────────────
def test_enabling_the_logon_task_removes_the_registry_entry_afterwards(build):
    """顺序有讲究：先建任务再撤注册表项。反过来一旦建任务失败，用户就同时丢了原本
    好用的自启。"""
    log: list = []
    plain, task = FakePlain(True, log=log), FakeTask(False, log=log)
    result = build(plain=plain, task=task).set_autostart_elevated(True)
    assert log == [("task", True), ("plain", False)]
    assert result["enabled"] is True
    assert "开机自启" in result["note"]


def test_a_stale_registry_entry_is_cleared_without_claiming_it_was_on(build):
    """残留的旧路径项也要删（它会去启动一个不存在的路径），但那不值得跟用户说。"""
    plain, task = FakePlain(False), FakeTask(False)
    result = build(plain=plain, task=task).set_autostart_elevated(True)
    assert plain.enabled is False
    assert result["note"] == ""


def test_a_blocked_logon_task_is_refused_with_the_gate_reason(build):
    """闸门的理由就是给用户的答复（05 文档 §1.5：此刻做不到的写操作是 422）。"""
    service = build(plain=FakePlain(), task=FakeTask(reason="现在没有管理员权限"))
    with pytest.raises(CapabilityMissing) as caught:
        service.set_autostart_elevated(True)
    assert caught.value.capability == "autostart_elevated"
    assert caught.value.message == "现在没有管理员权限"


def test_enabling_plain_autostart_takes_the_logon_task_down(build):
    log: list = []
    plain, task = FakePlain(False, log=log), FakeTask(True, log=log)
    result = build(plain=plain, task=task).set_autostart(True)
    assert log == [("task", False), ("plain", True)]
    assert "登录时以管理员身份启动" in result["note"]


def test_plain_autostart_refuses_rather_than_half_applying(build):
    """关不掉登录任务时**注册表项也不能写**：两条都开着才是最坏的结果。"""
    plain, task = FakePlain(False), FakeTask(True, reason="需要管理员权限")
    service = build(plain=plain, task=task)
    with pytest.raises(CapabilityMissing) as caught:
        service.set_autostart(True)
    assert caught.value.capability == "autostart_elevated"
    assert "需要管理员权限" in caught.value.message
    assert plain.enabled is False


def test_turning_plain_autostart_off_leaves_the_logon_task_alone(build):
    """两行各自独立：关掉这一行不该顺手删掉另一行建的东西——而另一行仍然显示"开"，
    所以没有谎报。"""
    plain, task = FakePlain(True), FakeTask(True)
    result = build(plain=plain, task=task).set_autostart(False)
    assert task.enabled is True
    assert result["enabled"] is False


def test_the_elevated_switch_needs_the_port(build):
    with pytest.raises(CapabilityMissing) as caught:
        build(plain=FakePlain()).set_autostart_elevated(True)
    assert caught.value.capability == "autostart_elevated"


# ── 托盘：一个勾选框，两条机制 ──────────────────────────────────────────
def _runtime(plain: object, task: object, *, services: object = None):
    return SimpleNamespace(
        adapter_set=SimpleNamespace(autostart=plain, autostart_elevated=task),
        services=services,
    )


@pytest.mark.parametrize(
    ("plain_on", "task_on", "checked"),
    [(False, False, False), (True, False, True), (False, True, True), (True, True, True)],
)
def test_the_tray_checkbox_follows_either_mechanism(plain_on, task_on, checked):
    """只看注册表项会在登录任务开着时显示未勾选，而程序每次登录都照常起来。"""
    runtime = _runtime(FakePlain(plain_on), FakeTask(task_on))
    assert Lifecycle()._autostart_enabled(runtime) is checked


def test_unchecking_the_tray_switch_clears_both_mechanisms():
    """取消勾选后程序还是每次登录都起来，那这个勾选框就是个装饰。"""
    log: list = []
    plain, task = FakePlain(True, log=log), FakeTask(True, log=log)
    Lifecycle()._toggle_autostart(_runtime(plain, task), False)
    assert (plain.enabled, task.enabled) == (False, False)


def test_checking_the_tray_switch_does_not_create_a_logon_task():
    """从托盘勾一下不该顺带建一个每次登录静默提权的计划任务：那个决定要连同它的代价
    一起摆在设置页上。"""
    plain, task = FakePlain(False), FakeTask(False)
    Lifecycle()._toggle_autostart(_runtime(plain, task), True)
    assert (plain.enabled, task.enabled) == (True, False)


def test_a_blocked_logon_task_still_lets_the_registry_entry_go(caplog):
    """关不掉任务时至少把能关的关掉，并把原因写进日志——托盘没有说话的地方。"""
    plain, task = FakePlain(True), FakeTask(True, reason="需要管理员权限")
    Lifecycle()._toggle_autostart(_runtime(plain, task), False)
    assert plain.enabled is False
    assert task.enabled is True
    assert "需要管理员权限" in caplog.text


def test_the_tray_switch_goes_through_the_settings_service_when_there_is_one():
    """与设置页同一条路径：互斥、写配置、清缓存都只有一处实现（``_set_paused`` 同理）。"""
    calls: list = []
    services = SimpleNamespace(
        settings=SimpleNamespace(set_autostart=lambda enabled: calls.append(enabled))
    )
    plain = FakePlain(False)
    Lifecycle()._toggle_autostart(_runtime(plain, FakeTask(False), services=services), True)
    assert calls == [True]
    assert plain.enabled is False, "服务层负责写，装配层不该再写一遍"
