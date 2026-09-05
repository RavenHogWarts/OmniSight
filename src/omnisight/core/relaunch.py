"""重启自己：怎么拼出接班实例的命令行，以及怎么把它拉起来（18 文档 批 5）。

**为什么住在 core 而不是 adapters**：拉起一个自己的副本是纯 Python（``subprocess.Popen``），
没有任何平台 API；只有**提权**重启是平台特有的（Windows 走 ``ShellExecuteExW "runas"``）。
后者在 ``adapters/windows/elevation.py``，它复用这里的命令行构造——于是"我该怎么再启动一次
自己"这件事只有一处答案，普通重启与提权重启不会各拼一套参数。

``arguments()`` 刻意是**纯函数**：``Popen`` 那一半在测试里只能打桩，而"命令行拼错了"是这里
唯一会真正伤人的错误——参数错一个字，用户点下去就只看到程序没了。
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

logger = logging.getLogger(__name__)

#: PyInstaller onefile 引导器的交接环境。**接班实例必须看不见它们。**
#:
#: onefile 的引导器是父子两个进程：父进程把归档解包到一个临时目录 `_MEIxxxxxx`，把它写进
#: 这几个变量，再以子进程身份重新执行自己；子进程见到它们就**跳过解包**、直接用那个目录；
#: 父进程在子进程退出后把目录删掉。
#:
#: 于是"从 Python 里再启动一次自己"会连这几个变量一起继承——接班实例因此复用了本进程那个
#: 临时目录，而本进程退出时它的引导器父进程会把目录删掉。症状分三档，全部发生在接班实例
#: 已经在跑之后，且看起来都不像"重启"造成的（2026-09-06 在 0.1.0-alpha.1 的产物上三档全中）：
#:
#:   * 模板还在、`static/dist` 没了 —— 页面显示"前端产物缺失"，而 `pnpm build` 明明跑过；
#:   * 模板也没了 —— 首页 500；
#:   * 再重启一次 —— 连 werkzeug 的包元数据都没了，接班实例启动即
#:     ``PackageNotFoundError: No package metadata was found for werkzeug``。
#:
#: 删除顺序（os.walk 自上而下）决定了这次撞上哪一档，而 Windows 删不掉已映射的 DLL，
#: 因此那棵树总是被删成半截——这也是同一个 bug 会有三种脸的原因。
#:
#: ``_MEIPASS2`` 是 PyInstaller 6 之前的名字，一并清掉：这份清单不该随打包器版本失效。
BOOTLOADER_ENV = (
    "_PYI_APPLICATION_HOME_DIR",
    "_PYI_ARCHIVE_FILE",
    "_PYI_PARENT_PROCESS_LEVEL",
    "_PYI_SPLASH_IPC",
    "_MEIPASS2",
)


def child_environment(source: Mapping[str, str] | None = None) -> dict[str, str]:
    """给接班实例的环境：本进程的环境减去 :data:`BOOTLOADER_ENV`。"""
    items = os.environ if source is None else source
    return {key: value for key, value in items.items() if key not in BOOTLOADER_ENV}


def scrub_process_env() -> None:
    """就地清掉本进程环境里的 :data:`BOOTLOADER_ENV`。

    给**没法传 env 的启动方式**用：提权重启走 ``ShellExecuteExW``，新进程从调用方的环境块
    继承，没有参数可以覆盖它（``adapters/windows/elevation.py``）。

    本进程清掉它们是安全的：引导器早在解释器起来之前就用完了，``sys._MEIPASS`` 是一个已经
    定好的属性、不会再回头读环境。调用方随后一般就要停机。
    """
    for key in BOOTLOADER_ENV:
        os.environ.pop(key, None)

#: 接班实例带上它，会在加锁那一步多等一会儿（见 ``core/lifecycle`` 的
#: ``_acquire_instance_lock``）：提权/重启后的新进程与正在停机的旧进程必然有一段重叠，
#: 而"第二个实例"与"接班的实例"在锁面前长得一模一样。
TAKEOVER_FLAG = "--takeover"


def arguments(
    argv: Sequence[str] | None = None,
    *,
    frozen: bool | None = None,
    executable: str | None = None,
) -> tuple[str, list[str]]:
    """接班实例要执行的 ``(程序, 参数列表)``。

    **不带上本次运行的其他参数。** 目前只有 ``--autostart``，而它的语义是"我是被自启项
    拉起来的"；用户手动重启显然不是那回事。
    """
    argv = list(sys.argv if argv is None else argv)
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    program = str(Path(executable or sys.executable).resolve())
    if frozen:
        return program, [TAKEOVER_FLAG]
    script = argv[0] if argv else ""
    if not script or Path(script).name == "__main__.py":
        # ``python -m omnisight``：argv[0] 是包内 ``__main__.py`` 的路径，而直接执行
        # 那个文件会因为相对导入失败（理由见仓库根 ``main.py`` 的说明）。
        return program, ["-m", "omnisight", TAKEOVER_FLAG]
    return program, [str(Path(script).resolve()), TAKEOVER_FLAG]


def spawn() -> subprocess.Popen[bytes] | None:
    """拉起接班实例。失败返回 ``None``（调用方**必须**因此放弃停机）。

    **不等它、也不收它的输出**：新实例要活得比本进程长，父子关系一断它就是个独立进程。
    ``close_fds`` 是默认值，因此它不会继承本进程的套接字——否则旧端口在旧进程退出后仍然
    被新进程的继承句柄占着，而症状是"重启后打不开页面"。

    ``env`` **必须显式给**（见 :data:`BOOTLOADER_ENV`）：继承下去的话接班实例会复用本进程
    解包出来的临时目录，而那个目录在本进程退出时被删掉。
    """
    program, args = arguments()
    logger.info("启动接班实例：%s %s", program, " ".join(args))
    try:
        return subprocess.Popen(
            [program, *args], cwd=str(Path.cwd()), env=child_environment()
        )
    except OSError:
        logger.exception("启动接班实例失败，本实例继续运行")
        return None


__all__ = [
    "BOOTLOADER_ENV",
    "TAKEOVER_FLAG",
    "arguments",
    "child_environment",
    "scrub_process_env",
    "spawn",
]
