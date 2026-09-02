"""崩溃收集（10 文档 §8、08 文档 §7）。

``--noconsole`` 打包后，未捕获异常会**静默**杀掉进程或线程：用户只看到"托盘图标
消失了"，日志里什么都没有——因为默认的 ``sys.excepthook`` 往一个不存在的 stderr 写。
这里把三条逃逸路径都堵上：主线程（:func:`sys.excepthook`）、后台线程
（:func:`threading.excepthook`，Python 3.8+）、以及未被 await 的 asyncio 任务不适用
（本项目无 asyncio）。

**红线与 08 文档 §7 一致：不含局部变量、不自动上报。**
``traceback.format_exception`` 只输出"类型 + 位置 + 源码行"，不像 ``cgitb`` /
``faulthandler`` 那样把栈帧里的局部变量倒出来——而局部变量里可能有窗口标题或键位。
写盘前再过一道 :func:`~omnisight.core.logging.scrub`，与运行日志同一道防线。
生成的文件**只落在本机日志目录**，程序不会把它发到任何地方（无遥测，08 文档 §7）。

崩溃文件与 ``STARTUP_ERROR.txt`` 分工不同：后者是"启动没能完成"的用户可读线索
（10 文档 §6），前者是"跑起来之后炸了"的诊断材料，因此放在 ``logs/`` 而不是数据根，
并保留最近若干个。

**平台信息由调用方以"提供者"的形式注入，不在这里读 ``sys.platform``。** 核心层不许
判断平台（01 文档非功能需求，`tools/check_platform_leaks.py` 强制），而报告里那行
"在什么系统上崩的"确实有诊断价值——正确的来源是探测出来的
:class:`~omnisight.adapters.ports.Capabilities`。之所以是**可调用对象**而不是字符串：
崩溃钩子必须在日志装配后立刻安装（在这之前抛出的异常还有 stderr 兜底，之后的会
静默消失），而那时适配器还没探测完。传个 lambda，取值推迟到真的崩了那一刻。
"""

from __future__ import annotations

import logging
import sys
import threading
import traceback
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from types import TracebackType

from . import logging as log_setup

logger = logging.getLogger(__name__)

CRASH_PREFIX = "crash-"
CRASH_SUFFIX = ".txt"
#: 保留多少份崩溃文件。多于此数时删最旧的——崩溃循环不该把磁盘写满。
KEEP = 10

_installed = False


def crash_path(logs_dir: Path, when: datetime) -> Path:
    return logs_dir / f"{CRASH_PREFIX}{when.strftime('%Y%m%d-%H%M%S')}{CRASH_SUFFIX}"


def format_report(
    *,
    kind: str,
    exc_type: type[BaseException] | None,
    exc: BaseException | None,
    tb: TracebackType | None,
    when: datetime,
    thread: str,
    version: str,
    environment: str = "",
) -> str:
    """崩溃报告正文。**只有类型、位置与源码行**，没有局部变量（08 文档 §7）。"""
    header = [
        f"OmniSight {version} 崩溃报告",
        f"时间：{when.isoformat(timespec='seconds')}",
        f"来源：{kind}（线程 {thread}）",
        f"Python {sys.version.split()[0]} / {environment or '平台未探测'}",
        "",
        "这份文件只在本机保存，程序不会把它发送到任何地方。",
        "它不含窗口标题、按键内容或局部变量；可以直接附在问题报告里。",
        "",
    ]
    if exc_type is None:
        body = ["（没有异常信息）"]
    else:
        body = traceback.format_exception(exc_type, exc, tb)
    return log_setup.scrub("\n".join(header) + "".join(body))


def write_report(logs_dir: Path, report: str, *, when: datetime | None = None) -> Path | None:
    """写一份崩溃报告并轮转旧文件。**绝不抛异常**——它跑在错误路径上。"""
    when = when or datetime.now().astimezone()
    try:
        logs_dir.mkdir(parents=True, exist_ok=True)
        path = crash_path(logs_dir, when)
        # 同一秒内连续崩溃（线程组一起炸）不能互相覆盖。
        index = 1
        while path.exists():
            stamp = when.strftime("%Y%m%d-%H%M%S")
            path = logs_dir / f"{CRASH_PREFIX}{stamp}-{index}{CRASH_SUFFIX}"
            index += 1
        path.write_text(report, encoding="utf-8")
    except OSError:
        logger.exception("无法写入崩溃报告")
        return None
    _rotate(logs_dir)
    return path


def _rotate(logs_dir: Path, keep: int = KEEP) -> None:
    try:
        files = sorted(logs_dir.glob(f"{CRASH_PREFIX}*{CRASH_SUFFIX}"))
    except OSError:  # pragma: no cover - 目录刚被删掉
        return
    for stale in files[:-keep] if len(files) > keep else []:
        try:
            stale.unlink()
        except OSError:  # pragma: no cover
            logger.debug("删除旧崩溃报告失败：%s", stale.name)


def install(
    logs_dir: Path,
    *,
    version: str = "",
    environment: Callable[[], str] | None = None,
    on_crash: Callable[[Path], None] | None = None,
) -> None:
    """接管未捕获异常。可重复调用（后一次覆盖前一次），进程退出时不需要卸载。

    ``environment`` 是**惰性**的平台描述提供者（见模块说明）：安装时平台还没探测完，
    因此这里存的是取值方式而不是取值结果。它抛异常时报告照旧生成——诊断信息缺一行
    可以接受，为了那一行让崩溃处理自己崩掉不行。

    ``KeyboardInterrupt`` 走原钩子：它是用户主动中断，不是崩溃，写一份报告只会
    在开发时制造噪声。
    """
    global _installed
    previous_hook = sys.excepthook
    previous_thread_hook = threading.excepthook

    def _environment() -> str:
        if environment is None:
            return ""
        try:
            return environment() or ""
        except Exception:  # pragma: no cover - 探测信息不可用不该盖住真正的异常
            return ""

    def _record(kind: str, exc_type, exc, tb, thread: str) -> None:
        when = datetime.now().astimezone()
        report = format_report(
            kind=kind,
            exc_type=exc_type,
            exc=exc,
            tb=tb,
            when=when,
            thread=thread,
            version=version,
            environment=_environment(),
        )
        # 先记日志：崩溃报告写盘可能失败，而日志此刻通常还活着。
        name = exc_type.__name__ if exc_type else "?"
        logger.critical("未捕获异常（%s，线程 %s）：%s", kind, thread, name)
        logger.critical("%s", "".join(traceback.format_exception(exc_type, exc, tb)))
        path = write_report(logs_dir, report, when=when)
        if path is not None and on_crash is not None:
            try:
                on_crash(path)
            except Exception:  # pragma: no cover - 通知失败不能再抛
                logger.debug("崩溃回调失败", exc_info=True)

    def hook(exc_type, exc, tb) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            previous_hook(exc_type, exc, tb)
            return
        _record("主线程", exc_type, exc, tb, threading.current_thread().name)
        previous_hook(exc_type, exc, tb)

    def thread_hook(args) -> None:
        if args.exc_type is not None and issubclass(args.exc_type, SystemExit):
            return
        thread_name = args.thread.name if args.thread is not None else "?"
        _record("后台线程", args.exc_type, args.exc_value, args.exc_traceback, thread_name)
        previous_thread_hook(args)

    sys.excepthook = hook
    threading.excepthook = thread_hook
    _installed = True


def installed() -> bool:
    return _installed


__all__ = [
    "CRASH_PREFIX",
    "KEEP",
    "crash_path",
    "format_report",
    "install",
    "installed",
    "write_report",
]
