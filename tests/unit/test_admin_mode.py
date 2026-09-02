"""管理员模式的装配层部分（10 文档 §5.2）。

三段逻辑在这里被钉住，它们都**不认识 Windows**，因此三个平台都跑：

1. 提权状态怎么压成托盘要显示的三档（``_elevation_state``）。
2. 提权重启的交接：新实例带 ``--takeover``，加锁前要等旧实例退干净，但等待有上限。
3. 管理员模式下"打开浏览器"必须降权（``_open_external``）。

真正调 ``ShellExecuteExW`` / 读令牌的那一半在 ``tests/adapters/test_elevation.py``。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from omnisight import app
from omnisight.core import lifecycle as lifecycle_module
from omnisight.core.lifecycle import Lifecycle


class FakeElevation:
    """按剧本回答的提权端口。"""

    def __init__(
        self,
        *,
        elevated: bool = False,
        can: bool = True,
        relaunch: bool = True,
        unelevated: bool = True,
    ) -> None:
        self.elevated = elevated
        self.can = can
        self.relaunch = relaunch
        self.unelevated = unelevated
        self.opened: list[str] = []
        self.relaunches = 0

    def is_elevated(self) -> bool:
        return self.elevated

    def can_elevate(self) -> bool:
        return self.can

    def relaunch_elevated(self) -> bool:
        self.relaunches += 1
        if isinstance(self.relaunch, Exception):
            raise self.relaunch
        return self.relaunch

    def open_unelevated(self, target: str) -> bool:
        if isinstance(self.unelevated, Exception):
            raise self.unelevated
        self.opened.append(target)
        return self.unelevated


class CountingLock:
    """前 ``fails`` 次加锁失败，之后成功——旧实例正在停机时就是这个样子。"""

    def __init__(self, fails: int) -> None:
        self.fails = fails
        self.attempts = 0

    def acquire(self) -> bool:
        self.attempts += 1
        return self.attempts > self.fails


@pytest.fixture
def quick_takeover(monkeypatch) -> None:
    """把等待压缩到毫秒级：被测的是"等不等、等多久算够"，不是真实秒数。"""
    monkeypatch.setattr(lifecycle_module, "TAKEOVER_WAIT_SECONDS", 0.2)
    monkeypatch.setattr(lifecycle_module, "TAKEOVER_POLL_SECONDS", 0.01)


def adapter_set(lock) -> SimpleNamespace:
    return SimpleNamespace(instance_lock=lock)


# ── 状态映射 ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("elevated", "can", "expected"),
    [
        (True, False, "elevated"),
        (False, True, "available"),
        (False, False, "unavailable"),
        # 已提权时 can_elevate() 本该是 False，但即使端口答错也不该把"已经是管理员"
        # 显示成"可以提权"——先判 is_elevated 就是为了这个。
        (True, True, "elevated"),
    ],
)
def test_the_three_states_the_tray_can_show(elevated: bool, can: bool, expected: str):
    control = FakeElevation(elevated=elevated, can=can)
    assert lifecycle_module._elevation_state(control) == expected


def test_a_failing_probe_reports_the_least_privileged_state():
    """菜单每次右键都要画一遍，一个异常会毁掉整个菜单。"""

    class Broken:
        def is_elevated(self) -> bool:
            raise OSError("令牌打不开")

    assert lifecycle_module._elevation_state(Broken()) == "unavailable"


# ── 交接（--takeover）────────────────────────────────────────────────────
def test_a_plain_start_does_not_wait_for_anything():
    lifecycle = Lifecycle()
    lock = CountingLock(fails=1)
    assert lifecycle._acquire_instance_lock(adapter_set(lock)) is False
    assert lock.attempts == 1, "没有 --takeover 就只试一次，第二实例应当立刻退让"


def test_takeover_waits_until_the_old_instance_lets_go(quick_takeover):
    """提权后的新进程与正在停机的旧进程必然重叠：旧实例是在 UAC 有结果之后才开始退的。"""
    lifecycle = Lifecycle(takeover=True)
    lock = CountingLock(fails=3)
    assert lifecycle._acquire_instance_lock(adapter_set(lock)) is True
    assert lock.attempts == 4


def test_takeover_gives_up_rather_than_running_a_second_recorder(quick_takeover):
    """旧实例根本没在退时，宁可"提权没生效"，也不能有两个实例同时写同一个库。"""
    lifecycle = Lifecycle(takeover=True)
    lock = CountingLock(fails=10_000)
    assert lifecycle._acquire_instance_lock(adapter_set(lock)) is False
    assert lock.attempts > 1, "至少应当重试过"


# ── 托盘那一项按下去之后 ─────────────────────────────────────────────────
def runtime_with(control) -> SimpleNamespace:
    return SimpleNamespace(adapter_set=SimpleNamespace(elevation=control))


def test_a_successful_relaunch_shuts_this_instance_down():
    """新实例已经在启动了，本实例必须让位——两个实例同时抢锁只会两败俱伤。"""
    lifecycle = Lifecycle()
    stopped: list[str] = []
    lifecycle.shutdown = lambda: stopped.append("shutdown")  # type: ignore[method-assign]
    control = FakeElevation(relaunch=True)
    lifecycle._elevate(runtime_with(control))
    assert control.relaunches == 1
    assert stopped == ["shutdown"]


def test_cancelling_the_uac_prompt_leaves_the_program_running():
    """用户点「否」表达的是"算了，别提权"，不是"把程序关掉"。"""
    lifecycle = Lifecycle()
    stopped: list[str] = []
    lifecycle.shutdown = lambda: stopped.append("shutdown")  # type: ignore[method-assign]
    lifecycle._elevate(runtime_with(FakeElevation(relaunch=False)))
    assert stopped == []


def test_a_raising_port_also_leaves_the_program_running():
    lifecycle = Lifecycle()
    stopped: list[str] = []
    lifecycle.shutdown = lambda: stopped.append("shutdown")  # type: ignore[method-assign]
    control = FakeElevation()
    control.relaunch = RuntimeError("shell32 不见了")  # type: ignore[assignment]
    lifecycle._elevate(runtime_with(control))
    assert stopped == []


# ── 管理员模式下打开外部程序 ─────────────────────────────────────────────
@pytest.fixture
def opened_by_webbrowser(monkeypatch) -> list[str]:
    calls: list[str] = []
    monkeypatch.setattr(lifecycle_module.webbrowser, "open", lambda url: calls.append(url))
    return calls


URL = "http://127.0.0.1:6100/?token=t"


def test_normal_privileges_open_things_the_ordinary_way(opened_by_webbrowser):
    control = FakeElevation(elevated=False)
    Lifecycle()._open_external(runtime_with(control), URL)
    assert opened_by_webbrowser == [URL]
    assert control.opened == []


def test_admin_mode_drops_privileges_before_opening(opened_by_webbrowser):
    """子进程继承父进程的令牌：直接打开就会得到一个带管理员权限的浏览器。"""
    control = FakeElevation(elevated=True)
    Lifecycle()._open_external(runtime_with(control), URL)
    assert control.opened == [URL]
    assert opened_by_webbrowser == [], "降权成功后不该再打开第二次"


def test_a_failed_de_elevation_still_opens_it(opened_by_webbrowser):
    """"打不开"比"权限高了一档"更糟：那是用户唯一的入口。"""
    control = FakeElevation(elevated=True, unelevated=False)
    Lifecycle()._open_external(runtime_with(control), URL)
    assert opened_by_webbrowser == [URL]


def test_a_raising_de_elevation_still_opens_it(opened_by_webbrowser):
    control = FakeElevation(elevated=True)
    control.unelevated = OSError("explorer.exe 不见了")  # type: ignore[assignment]
    Lifecycle()._open_external(runtime_with(control), URL)
    assert opened_by_webbrowser == [URL]


def test_platforms_without_the_port_are_unaffected(opened_by_webbrowser):
    Lifecycle()._open_external(runtime_with(None), URL)
    assert opened_by_webbrowser == [URL]


# ── 命令行 ────────────────────────────────────────────────────────────────
def test_the_takeover_flag_exists_and_defaults_to_off():
    assert app.build_parser().parse_args([]).takeover is False
    assert app.build_parser().parse_args(["--takeover"]).takeover is True


def test_the_flag_actually_reaches_the_lifecycle(monkeypatch):
    """提权重启的新实例全靠这一个开关才知道"要等旧实例退"。"""
    seen: dict[str, object] = {}

    class FakeLifecycle:
        def __init__(self, **kwargs: object) -> None:
            seen.update(kwargs)

        def start(self) -> int:
            return 0

    monkeypatch.setattr(app, "Lifecycle", FakeLifecycle)
    assert app.run(["--takeover"]) == 0
    assert seen == {"autostart_invocation": False, "takeover": True}
