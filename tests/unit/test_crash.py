"""崩溃收集（10 文档 §8、08 文档 §7）。

08 文档的红线在这里必须有机械化保障：崩溃报告**不含局部变量**、写盘前过
:func:`~omnisight.core.logging.scrub`、绝不抛异常（它跑在错误路径上）。
"""

from __future__ import annotations

import sys
import threading
from datetime import UTC, datetime
from pathlib import Path

import pytest

from omnisight.core import crash


@pytest.fixture(autouse=True)
def restore_hooks():
    """崩溃钩子接管的是**进程级**状态，用例结束后必须还原——否则一个用例装的钩子
    会把后面所有用例的异常都写成崩溃报告。"""
    excepthook, thread_hook = sys.excepthook, threading.excepthook
    yield
    sys.excepthook, threading.excepthook = excepthook, thread_hook


def _boom(secret: str = "window_title='季度财报（机密）'") -> None:
    """故意在局部变量与异常参数里都放敏感内容，验证它们不会出现在报告里。"""
    raise RuntimeError(f"failed with {secret}")


def test_report_carries_type_location_and_no_locals():
    try:
        _boom()
    except RuntimeError:
        info = sys.exc_info()
    report = crash.format_report(
        kind="主线程",
        exc_type=info[0],
        exc=info[1],
        tb=info[2],
        when=datetime.now(UTC),
        thread="MainThread",
        version="0.1.0-alpha.1",
    )
    assert "RuntimeError" in report
    assert "test_crash.py" in report  # 位置（源文件名）必须在
    assert "季度财报" not in report  # 异常参数不出现
    assert "0.1.0-alpha.1" in report


def test_report_scrubs_structured_leaks(tmp_path: Path):
    """``scrub`` 那道防线对崩溃报告同样生效（与运行日志同一道）。"""
    try:
        raise ValueError("window_title='秘密标题'")
    except ValueError:
        report = crash.format_report(
            kind="后台线程", exc_type=ValueError, exc=sys.exc_info()[1], tb=sys.exc_info()[2],
            when=datetime.now(UTC), thread="WriterThread", version="1.0",
        )
    assert "秘密标题" not in report
    assert "window_title=<redacted>" in report


def test_write_report_never_raises_even_if_directory_is_a_file(tmp_path: Path):
    blocker = tmp_path / "logs"
    blocker.write_text("占位", encoding="utf-8")  # 目录名被同名文件占据
    assert crash.write_report(blocker, "report") is None


def test_same_second_crashes_do_not_overwrite_each_other(tmp_path: Path):
    when = datetime(2026, 9, 2, 12, 0, 0, tzinfo=UTC)
    first = crash.write_report(tmp_path, "one", when=when)
    second = crash.write_report(tmp_path, "two", when=when)
    assert first is not None and second is not None
    assert first != second
    assert first.read_text(encoding="utf-8") == "one"
    assert second.read_text(encoding="utf-8") == "two"


def test_rotation_keeps_only_the_newest_reports(tmp_path: Path):
    base = datetime(2026, 9, 2, 12, 0, 0, tzinfo=UTC)
    for index in range(crash.KEEP + 3):
        crash.write_report(tmp_path, f"r{index}", when=base.replace(minute=index))
    files = sorted(path.name for path in tmp_path.glob("crash-*.txt"))
    assert len(files) == crash.KEEP
    assert "r0" not in {path.read_text(encoding="utf-8") for path in tmp_path.glob("crash-*.txt")}


def test_install_intercepts_main_thread_exceptions(tmp_path: Path):
    written: list[Path] = []
    crash.install(tmp_path, version="9.9.9", on_crash=written.append)
    try:
        _boom()
    except RuntimeError:
        sys.excepthook(*sys.exc_info())
    assert len(written) == 1
    contents = written[0].read_text(encoding="utf-8")
    assert "9.9.9" in contents
    assert "主线程" in contents


@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
def test_install_intercepts_background_threads(tmp_path: Path):
    """线程函数里未捕获的异常由 ``threading.excepthook`` 接管——装上钩子后
    它会自动触发，不需要手工调用。告警过滤是因为钩子链**正确地**把异常交还给了
    pytest 的捕获钩子，那本来就是安装时的承诺（不吞别人的钩子）。"""
    written: list[Path] = []
    crash.install(tmp_path, on_crash=written.append)

    def target() -> None:
        raise ValueError("thread boom")

    thread = threading.Thread(target=target, name="Worker-1")
    thread.start()
    thread.join()
    assert len(written) == 1
    contents = written[0].read_text(encoding="utf-8")
    assert "后台线程" in contents and "Worker-1" in contents


def test_keyboard_interrupt_goes_to_the_previous_hook(tmp_path: Path):
    """用户主动中断不是崩溃：写报告只会制造噪声（模块文档的明文规则）。"""
    seen: list[tuple[type, BaseException | None]] = []

    def previous(exc_type, exc, tb) -> None:
        seen.append((exc_type, exc))

    sys.excepthook = previous
    crash.install(tmp_path)
    sys.excepthook(KeyboardInterrupt, KeyboardInterrupt(), None)
    assert seen and seen[0][0] is KeyboardInterrupt
    assert not list(tmp_path.glob("crash-*.txt"))


def test_environment_provider_is_lazy_and_failure_tolerant(tmp_path: Path):
    """环境提供者在安装时还没探测完——取值必须推迟到崩溃那一刻，且它自己炸了
    也不能盖住真正的异常（模块文档的两条承诺）。"""
    calls: list[int] = []
    boom_count = 0

    def provider() -> str:
        nonlocal boom_count
        calls.append(1)
        boom_count += 1
        raise OSError("探测失败")

    crash.install(tmp_path, environment=provider)
    assert calls == []  # 安装时不求值
    try:
        raise RuntimeError("real crash")
    except RuntimeError:
        sys.excepthook(*sys.exc_info())
    reports = list(tmp_path.glob("crash-*.txt"))
    assert len(reports) == 1
    assert "real crash" in reports[0].read_text(encoding="utf-8")
    assert "平台未探测" in reports[0].read_text(encoding="utf-8")


def test_environment_label_lands_in_the_report(tmp_path: Path):
    crash.install(tmp_path, environment=lambda: "windows 10.0.26200")
    try:
        raise RuntimeError("x")
    except RuntimeError:
        sys.excepthook(*sys.exc_info())
    contents = next(iter(tmp_path.glob("crash-*.txt"))).read_text(encoding="utf-8")
    assert "windows 10.0.26200" in contents


def test_install_is_repeatable_and_overrides(tmp_path: Path):
    """可重复调用（后一次覆盖前一次）——生命周期的测试里会反复走 start()。"""
    crash.install(tmp_path, version="1")
    crash.install(tmp_path / "sub", version="2")
    assert crash.installed()
    try:
        raise RuntimeError("y")
    except RuntimeError:
        sys.excepthook(*sys.exc_info())
    reports = list((tmp_path / "sub").glob("crash-*.txt"))
    assert len(reports) == 1
    assert "OmniSight 2 崩溃报告" in reports[0].read_text(encoding="utf-8")
