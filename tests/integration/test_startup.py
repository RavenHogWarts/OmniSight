"""端到端启动/停机（M0 完成判据）。

不启动托盘（那会阻塞主线程），只跑到"Web 已就绪"为止，再走完整的停机路径。
这条用例覆盖的是 M0 判据里最容易回归的三条：全新目录能建库、二次启动被挡住、
停机后不留残余线程。
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path
from uuid import uuid4

import pytest

from omnisight.core import paths
from omnisight.core.lifecycle import EXIT_ALREADY_RUNNING, Lifecycle
from omnisight.presentation import security
from omnisight.storage.migrations import TARGET_VERSION


@pytest.fixture
def isolated_root(tmp_path: Path, monkeypatch) -> Path:
    """把整个数据根目录挪到 tmp_path，绝不碰用户真实的 %LOCALAPPDATA%。

    单实例锁也要隔离：Windows 上它是**机器全局**的命名互斥体，用户自己开着
    OmniSight 时这一组用例会集体返回 ``EXIT_ALREADY_RUNNING``——失败原因与被测
    行为毫无关系，而症状（``assert 2 == 0``）完全不提示这一点。锁名按用例生成，
    同一个用例内的两个实例仍然共用它，于是"第二实例被挡住"照样测得到。
    """
    monkeypatch.setattr(paths, "exe_dir", lambda: tmp_path)
    monkeypatch.setattr(paths, "_platform_app_dir", lambda: tmp_path / "root")
    if sys.platform == "win32":
        from omnisight.adapters.windows import factory as windows_factory
        from omnisight.adapters.windows.single_instance import NamedMutexInstanceLock

        name = rf"Local\OmniSight.Test.{uuid4().hex}"
        monkeypatch.setattr(
            windows_factory,
            "NamedMutexInstanceLock",
            lambda mutex=name: NamedMutexInstanceLock(mutex),
        )
    return tmp_path / "root"


def _start_headless(monkeypatch, port: int = 6199) -> Lifecycle:
    """跳过托盘阻塞，其余启动步骤全部真实执行。"""
    lifecycle = Lifecycle()
    monkeypatch.setattr(lifecycle, "_run_tray", lambda runtime: None)
    monkeypatch.setattr(lifecycle, "_install_signal_handlers", lambda: None)
    return lifecycle


def test_first_run_creates_config_database_and_logs(isolated_root: Path, monkeypatch):
    lifecycle = _start_headless(monkeypatch)
    monkeypatch.setenv("OMNISIGHT_TEST", "1")
    try:
        assert lifecycle.start() == 0
        runtime = lifecycle.runtime
        assert runtime is not None
        assert paths.config_path(isolated_root).exists()
        assert runtime.database.path.exists()
        assert runtime.schema_version == TARGET_VERSION
        assert (isolated_root / "logs" / "omnisight.log").exists()
        # 令牌与端口交接文件在运行期存在，停机后消失。
        assert security.read_runtime_file(runtime.data_dir) is not None
    finally:
        lifecycle.shutdown()
    assert security.read_runtime_file(lifecycle.runtime.data_dir) is None


def test_capability_row_written_for_today(isolated_root: Path, monkeypatch):
    """``capture_capability`` 必须记下**实际生效**的能力，而不是探测到的能力。

    这张表的全部价值在于它能解释历史数据（03 文档 §2.8），所以判据不是某个写死的
    后端名，而是「行内容 == reconcile() 之后的能力」。M0 时期这里断言的是 ``none``；
    M1 起键盘真的启动了，写死后端名会让这条用例变成平台断言。
    """
    lifecycle = _start_headless(monkeypatch)
    try:
        assert lifecycle.start() == 0
        runtime = lifecycle.runtime
        rows = runtime.database.connect().execute(
            "SELECT platform_id, keyboard_backend, foreground_available,"
            " titles_recorded, key_position_stable FROM capture_capability"
        ).fetchall()
        assert len(rows) == 1
        row = rows[0]
        effective = runtime.capabilities
        assert row["platform_id"] == effective.platform_id
        assert row["keyboard_backend"] == effective.keyboard_backend
        assert bool(row["foreground_available"]) is bool(effective.foreground)
        assert bool(row["key_position_stable"]) is bool(effective.key_position_stable)
        # 标题是「能力允许 ∧ 用户开启」的合取，默认配置下用户没开。
        assert bool(row["titles_recorded"]) is False

        # 键盘真的起来了就不许记成 none，反过来也一样——两者不一致就意味着这天的
        # 数据无法被解释。
        started = runtime.capture is not None and runtime.capture.keyboard is not None
        assert (row["keyboard_backend"] != "none") is started
    finally:
        lifecycle.shutdown()


def test_second_instance_is_blocked(isolated_root: Path, monkeypatch):
    first = _start_headless(monkeypatch)
    opened: list[str] = []
    try:
        assert first.start() == 0
        second = _start_headless(monkeypatch)
        monkeypatch.setattr("webbrowser.open", lambda url: opened.append(url))
        assert second.start() == EXIT_ALREADY_RUNNING
        assert opened, "第二个实例必须唤起已有实例，而不是静默退出"
        assert first.runtime.token in opened[0]
    finally:
        first.shutdown()


def test_shutdown_is_idempotent_and_leaves_no_threads(isolated_root: Path, monkeypatch):
    before = {t.name for t in threading.enumerate()}
    lifecycle = _start_headless(monkeypatch)
    assert lifecycle.start() == 0
    lifecycle.shutdown()
    lifecycle.shutdown()  # 注销与强杀可能并发调用两次
    after = {t.name for t in threading.enumerate()}
    assert after - before == set(), f"残留线程：{after - before}"


def test_invalid_config_aborts_without_touching_the_file(isolated_root: Path, monkeypatch):
    isolated_root.mkdir(parents=True, exist_ok=True)
    config_file = paths.config_path(isolated_root)
    config_file.write_text('{"server": {"host": "0.0.0.0"}}', encoding="utf-8")
    original = config_file.read_bytes()

    lifecycle = _start_headless(monkeypatch)
    assert lifecycle.start() == 1
    assert config_file.read_bytes() == original
    # 启动失败必须留下用户能自己发现的线索（10 文档 §6）。
    assert (isolated_root / "STARTUP_ERROR.txt").exists()


def test_port_conflict_reports_clearly(isolated_root: Path, monkeypatch):
    """端口被占用时必须给出可读的指引，而不是静默换端口（09 文档 §3.1）。

    这里让 ``WebServer`` 直接抛 ``OSError``，不去真的占一个端口：``SO_REUSEADDR``
    的语义在 Windows 与 POSIX 上不同（Windows 上后来者能抢占），用真实套接字会让
    这条用例在不同平台上表现不一致——而全部测试都必须能在三个平台跑通
    （11 文档 §1）。
    """
    isolated_root.mkdir(parents=True, exist_ok=True)

    def refuse(*_args, **_kwargs):
        raise OSError(10048, "通常每个套接字地址只允许使用一次")

    monkeypatch.setattr("omnisight.core.lifecycle.WebServer", refuse)
    lifecycle = _start_headless(monkeypatch)
    try:
        assert lifecycle.start() == 1
        message = (isolated_root / "STARTUP_ERROR.txt").read_text(encoding="utf-8")
        assert "端口被占用" in message
        assert "server.port" in message
        # 提到旧版程序：老用户的 6001/6002 仍在自启是最常见的原因。
        assert "TimeLens" in message
    finally:
        lifecycle.shutdown()
