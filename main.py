"""PyInstaller 打包入口。

``src/omnisight/__main__.py`` 服务的是 ``python -m omnisight``，它用相对导入
（``from .app import run``）。PyInstaller 把入口脚本当**顶层脚本**执行，此时不存在
父包，相对导入会直接抛 ``ImportError``——而 ``--noconsole`` 下这个错误没有任何
出口，用户只看到"双击了没反应"。

因此打包用这个独立的启动器：绝对导入、不依赖包上下文。两个入口共用
``omnisight.app.run``，不会各自漂移。

**入口层还有一道自己的护栏**（``_report_early_crash``）：``core.crash`` 的崩溃钩子
要等启动走到日志装配之后才装上，而它注释里"在那之前还有 stderr 兜底"的假设在
macOS 的 ``--windowed`` 包上不成立——导入期的异常（最典型：打包漏收了一个模块）
会被整个吞掉，症状是"双击后 Dock 弹一下就没了"，数据目录、日志、崩溃报告一个都
不存在（2026-09-08 在 mac 虚拟机上实测踩中）。护栏用纯标准库把这种死法也写成
``STARTUP_ERROR.txt``——用户已经被所有文档指引去看的那个文件。
"""

from __future__ import annotations

import multiprocessing
import sys
from datetime import datetime
from pathlib import Path


def _report_early_crash(exc: BaseException) -> None:
    """早于日志系统装配的崩溃落盘。尽力而为：这里不许再引入新的失败点。

    写两处、成功一处即返回：数据目录的 ``STARTUP_ERROR.txt``（所有文档指引用户
    去看的位置），以及系统临时目录（前者写不进去时的兜底）。从终端拉起时
    stderr 是活的，先印一份。
    """
    import tempfile
    import traceback

    text = "".join(traceback.format_exception(exc))
    print(text, file=sys.stderr)
    targets: list[Path] = [Path(tempfile.gettempdir()) / "omnisight-startup-error.txt"]
    try:
        from omnisight.core import paths

        targets.insert(0, paths.app_root() / "STARTUP_ERROR.txt")
    except Exception:
        pass  # 连 paths 都导入不了时，临时目录那份就是唯一线索
    stamp = datetime.now().isoformat(timespec="seconds")
    for target in targets:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                f"{stamp}\n启动早期崩溃（早于日志系统装配，入口护栏记录）：\n\n{text}",
                encoding="utf-8",
            )
            return
        except OSError:
            continue


if __name__ == "__main__":
    # 打包后若将来用到多进程，没有这一行会让子进程重新执行整个启动流程。
    multiprocessing.freeze_support()
    try:
        # 导入留在 try 里：打包漏收模块时，报错点正是这一行——护栏要接得住它。
        from omnisight.app import run

        sys.exit(run(sys.argv[1:]))
    except SystemExit:
        raise
    except BaseException as exc:
        _report_early_crash(exc)
        raise
