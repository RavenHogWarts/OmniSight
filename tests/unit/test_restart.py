"""重启与令牌继承（18 文档 批 5）。

这一条路上有四个"点错了会出事"的地方，四个都只在这里被钉住：

1. **先起后停。** 反过来做的话，新实例起不来时用户只剩一个消失的托盘图标——而他要表达的
   只是"让改动生效"。因此 ``restart()`` 必须在确认接班进程活着之后才安排停机，起不来时
   一步都不能动。
2. **接班实例继承令牌。** 否则重启会让每一个已经打开的标签页在几秒后集体 401，而它们无从
   获得新令牌。冷启动仍然每次换一个（那是威胁模型要的），只有接班这条路沿用。
3. **令牌要在等单实例锁之前读，而旧实例不许把 runtime.json 带走。** 等锁等到的正是旧实例
   停机结束那一刻；而它停机比接班实例的解释器起得来还快（onefile 解包 1 秒上下，停机几百
   毫秒，现场日志相差 39 毫秒）。这两件事只做对一件，第 2 条就仍然不成立，症状一样是重启
   后已打开的页面集体 401（2026-09-06 在产物上两脚都踩过）。
4. **接班实例不许继承 PyInstaller 的引导环境。** 继承下去它会复用本进程解包出来的临时
   目录，而那个目录在本进程退出时被删掉：资源在接班实例脚下消失。
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from omnisight.core import relaunch
from omnisight.core.lifecycle import Lifecycle


class FakeProcess:
    """``subprocess.Popen`` 的替身。``code`` 为 None 表示"还活着"。"""

    def __init__(self, code: int | None = None) -> None:
        self.code = code

    def poll(self) -> int | None:
        return self.code


@pytest.fixture(autouse=True)
def instant_probe(monkeypatch):
    """把两个等待窗口压到 0：这组用例验的是顺序与判断，不是计时。"""
    monkeypatch.setattr("omnisight.core.lifecycle.RESTART_PROBE_SECONDS", 0)
    monkeypatch.setattr("omnisight.core.lifecycle.SHUTDOWN_DELAY_SECONDS", 0)


def _lifecycle(monkeypatch, spawned: FakeProcess | None) -> tuple[Lifecycle, list[str]]:
    calls: list[str] = []
    lifecycle = Lifecycle()
    monkeypatch.setattr(relaunch, "spawn", lambda: spawned)
    monkeypatch.setattr(lifecycle, "shutdown", lambda: calls.append("shutdown"))
    return lifecycle, calls


def test_a_live_successor_gets_the_current_instance_to_stand_down(monkeypatch):
    lifecycle, calls = _lifecycle(monkeypatch, FakeProcess(code=None))
    assert lifecycle.restart() is True
    # 停机排在一个短延时的线程里（响应要先出门），这里把它等出来。
    for thread in threading.enumerate():
        if thread.name == "shutdown-soon":
            thread.join(timeout=5)
    assert calls == ["shutdown"]


def test_a_successor_that_cannot_start_leaves_everything_alone(monkeypatch):
    """``spawn()`` 返回 None：命令行拼不出来、或者根本没能创建进程。"""
    lifecycle, calls = _lifecycle(monkeypatch, None)
    assert lifecycle.restart() is False
    assert calls == []


def test_a_successor_that_dies_immediately_is_not_mistaken_for_a_live_one(monkeypatch):
    """它起来了又立刻退了（参数不认、DLL 缺失）。**这正是观察窗口存在的理由。**"""
    lifecycle, calls = _lifecycle(monkeypatch, FakeProcess(code=1))
    assert lifecycle.restart() is False
    assert calls == []


# ── 令牌继承 ────────────────────────────────────────────────────────────
def test_a_cold_start_gets_a_fresh_token(tmp_path):
    (tmp_path / "runtime.json").write_text(json.dumps({"token": "old"}), encoding="utf-8")
    token = Lifecycle()._session_token(tmp_path)
    assert token != "old" and len(token) > 20


def test_a_takeover_inherits_the_previous_token(tmp_path):
    """已经打开的页面因此不掉线——那是"重新启动"这个功能存在的意义的一半。"""
    (tmp_path / "runtime.json").write_text(
        json.dumps({"port": 6100, "token": "inherited"}), encoding="utf-8"
    )
    assert Lifecycle(takeover=True)._session_token(tmp_path) == "inherited"


def test_a_takeover_without_a_readable_runtime_file_falls_back_to_a_new_token(tmp_path):
    """读不到就换新的：一个空令牌会让接班实例的每个请求都 401。"""
    token = Lifecycle(takeover=True)._session_token(tmp_path)
    assert token and len(token) > 20


def test_the_token_is_read_before_the_lock_is_waited_for(tmp_path, monkeypatch):
    """**顺序**：旧实例停机时先删 ``runtime.json``、后放单实例锁（``shutdown`` 的最后几行），
    而"等锁"等到的正是它停机结束那一刻。因此令牌必须在等锁**之前**读。

    第一版把它放在了锁后面，于是接管路径上永远读到一个已经不存在的文件，然后悄悄换一个
    新令牌——重启之后每一个已经打开的页面都 401（2026-09-06 在打包产物上实测）。
    """
    (tmp_path / "runtime.json").write_text(json.dumps({"token": "inherited"}), encoding="utf-8")
    lifecycle = Lifecycle(takeover=True)

    def acquire_after_the_old_instance_cleaned_up(_adapter_set):
        # 拿到锁的那一刻，那个文件已经被旧实例删掉了。
        (tmp_path / "runtime.json").unlink()
        return True

    monkeypatch.setattr(
        lifecycle, "_acquire_instance_lock", acquire_after_the_old_instance_cleaned_up
    )
    assert lifecycle._claim_session(tmp_path, object()) == "inherited"


def test_a_second_instance_gets_neither_the_lock_nor_a_token(tmp_path, monkeypatch):
    """锁没拿到就是"已经有一个在跑"，调用方据此退出（EXIT_ALREADY_RUNNING）。"""
    lifecycle = Lifecycle()
    monkeypatch.setattr(lifecycle, "_acquire_instance_lock", lambda _adapter_set: False)
    assert lifecycle._claim_session(tmp_path, object()) is None


# ── 接班实例的环境 ──────────────────────────────────────────────────────
def test_the_successor_does_not_inherit_the_bootloader_environment():
    """PyInstaller onefile 的引导器用几个环境变量交接"归档解包到哪儿了"。

    继承下去，接班实例就复用本进程那个临时目录，而本进程退出时它的引导器父进程会把目录
    删掉——症状是接班实例已经在跑之后资源在它脚下消失：先是"前端产物缺失"，再是首页 500，
    再重启一次连 werkzeug 的包元数据都没了（2026-09-06 三档全中）。
    """
    source = {"PATH": "keep-me", **dict.fromkeys(relaunch.BOOTLOADER_ENV, "/tmp/_MEIabc")}
    assert relaunch.child_environment(source) == {"PATH": "keep-me"}


def test_spawn_hands_the_scrubbed_environment_to_the_successor(monkeypatch):
    """光有 ``child_environment`` 不算修好——``spawn`` 必须真的把它传下去。"""
    monkeypatch.setenv("_PYI_APPLICATION_HOME_DIR", "/tmp/_MEIabc")
    seen: dict[str, object] = {}
    monkeypatch.setattr(
        relaunch.subprocess, "Popen", lambda argv, **kwargs: seen.update(argv=argv, **kwargs)
    )
    relaunch.spawn()
    env = seen["env"]
    assert isinstance(env, dict)
    assert "_PYI_APPLICATION_HOME_DIR" not in env
    assert env, "不能是个空环境：PATH 之类还得留着"


def test_the_elevated_path_can_only_scrub_its_own_environment(monkeypatch):
    """``ShellExecuteExW`` 没有 env 参数，新进程拿的是调用方的环境块——因此提权重启只能
    先把那几个变量从自己身上摘掉。"""
    monkeypatch.setenv("_PYI_ARCHIVE_FILE", "C:/x/OmniSight.exe")
    relaunch.scrub_process_env()
    assert "_PYI_ARCHIVE_FILE" not in relaunch.os.environ


def test_the_runtime_file_is_left_behind_for_the_successor(tmp_path):
    """拉起过接班实例就不许删 runtime.json——那是它继承令牌的唯一来源。

    时间上没有余量可赌：接班实例是 onefile 产物，引导器解包要 1 秒上下，而本实例停机只用
    几百毫秒。"删掉它、让接班实例自己去读"必然读到空（2026-09-06 现场日志相差 39 毫秒，
    那一晚三次重启全部退化成新令牌，重启后已打开的页面集体 401）。
    """
    from omnisight.presentation import security

    security.write_runtime_file(tmp_path, port=6100, token="t0")
    lifecycle = Lifecycle()
    lifecycle._successor_pending = True
    lifecycle._release_runtime_file(tmp_path)
    assert (security.read_runtime_file(tmp_path) or {}).get("token") == "t0"


def test_an_ordinary_shutdown_still_takes_the_runtime_file_with_it(tmp_path):
    """没有接班实例时照旧删掉：留一份指向已关闭端口的文件会把下一次启动带错路。"""
    from omnisight.presentation import security

    security.write_runtime_file(tmp_path, port=6100, token="t0")
    Lifecycle()._release_runtime_file(tmp_path)
    assert not security.read_runtime_file(tmp_path)


def test_both_restart_paths_mark_the_handover_before_shutting_down(monkeypatch):
    """两条接班路径（普通重启、提权重启）都必须先立起那面旗，否则第 3 条只修了一半。"""
    lifecycle, _ = _lifecycle(monkeypatch, FakeProcess(code=None))
    assert lifecycle.restart() is True
    assert lifecycle._successor_pending is True

    source = Path(__file__).resolve().parents[2] / "src/omnisight/core/lifecycle.py"
    body = source.read_text(encoding="utf-8")
    elevate = body.split("def _elevate(")[1].split("\n    def ")[0]
    assert "self._successor_pending = True" in elevate, "提权重启这条路也要留下 runtime.json"
