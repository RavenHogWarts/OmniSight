"""登录时以管理员身份启动：``/RL HIGHEST`` 的登录计划任务（10 文档 §5.3）。

**为什么注册表自启项不够。** 登录期 Windows 不为 ``HKCU\\Run`` 弹 UAC，那一项若需要
提权就**静默不启动**——不报错、不提示，只是没起来（``autostart.py`` 的
:func:`~omnisight.adapters.windows.autostart.always_elevated_by_compat_flag` 正是为
这个症状而存在）。Windows 上唯一能在登录时**无提示**地拿到管理员权限的机制是计划任务
的 ``RunLevel=HighestAvailable``，所以"开机就用管理员模式"只能走这条路。

**为什么这条路必须自带一道闸。** 这样一个任务等于"这个 EXE 每次登录都无提示地拿到
管理员权限"。如果 EXE 所在目录普通用户可写，那么任何以该用户身份运行的程序——包括
恶意程序——都能把它换掉，于是这条启动项就成了一条现成的 UAC 绕过通道：给自己开一个
方便，同时给别人开一个后门。因此只在三个条件同时满足时才允许开启：

1. **打包版**。开发模式下任务只能指向解释器（``python.exe -m omnisight``），而真正被
   执行的代码在一个可写的源码目录里——对解释器做路径判定证明不了任何事情。
2. **EXE 位于普通用户不可写的目录**（Program Files / Windows 之下）。判定用路径前缀，
   不算 ACL：会有漏判（管理员放宽过权限的 Program Files 子目录），但方向是保守的。
3. **当前进程已提权**。创建和删除 ``HighestAvailable`` 的任务本身就需要管理员权限，
   否则 Windows 自己就会拒绝（这也是上面那条"不能是 UAC 绕过通道"的另一半保障）。

``schtasks.exe`` 是命令行工具，本模块因此是唯一一处用子进程和操作系统打交道的适配器。
选它而不是 COM 的 ``ITaskService``：后者要 pywin32 的 ``taskscheduler`` 类型库进打包
产物，而这里只需要建/查/删三个动作，退出码与 XML 已经够用。
"""

from __future__ import annotations

import locale
import logging
import ntpath
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import PureWindowsPath

logger = logging.getLogger(__name__)

#: 任务名刻意用 ASCII：它要经 ``schtasks`` 的命令行来回一趟，而那一趟的编码取决于控制台
#: 代码页。中文名字在 cp936 的机器上能用，在别的代码页上会变成一个查不到的名字。
TASK_NAME = "OmniSight-LogonElevated"

#: ``RunLevel`` 的两个取值。任务存在但是 ``LeastPrivileged`` 时它照样会启动程序，只是
#: **不提权**——那与用户开这个开关的目的正好相反，所以按"未启用"处理。
RUN_LEVEL_HIGHEST = "HighestAvailable"

#: 子进程超时。设置页的请求同步等它，一个挂住的 schtasks 会让整个页面转圈。
TIMEOUT_SECONDS = 20.0

#: 打包成窗口程序（``--noconsole``）后启动控制台程序会**闪一个黑框**。用 ``getattr``
#: 取值只为让本模块在非 Windows 上也能导入（纯函数部分因此可以跨平台测）。
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

#: 普通用户不可写的目录。取环境变量而不是写死盘符：系统装在 D: 的机器不少见。
#: ``ProgramW6432`` 是 32 位进程看 64 位 Program Files 的那个变量，一并算上。
PROTECTED_ROOT_VARS = (
    "ProgramFiles",
    "ProgramFiles(x86)",
    "ProgramW6432",
    "SystemRoot",
    "windir",
)

_DECLARATION = re.compile(r"^\s*<\?xml[^>]*\?>", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class TaskInfo:
    """从任务 XML 里读出来的、判断"这一项是不是我们要的东西"所需的全部信息。"""

    command: str
    run_level: str

    @property
    def elevated(self) -> bool:
        return self.run_level == RUN_LEVEL_HIGHEST


def _env(environ: Mapping[str, str], name: str) -> str:
    """大小写不敏感地取环境变量。

    ``dict(os.environ)`` 在 Windows 上把键**全变成大写**，于是按 ``ProgramFiles``
    查恒为空——症状是这里安静地判定"程序不在受保护目录"，开关无缘无故是灰的
    （同一个坑在 ``tools/scan_record.py`` 里踩过一次）。
    """
    if name in environ:
        return environ[name]
    lowered = name.lower()
    for key, value in environ.items():
        if key.lower() == lowered:
            return value
    return ""


def _decode(raw: bytes) -> str:
    """解码 schtasks 的输出。

    三种编码都见得到：``/XML`` 的导出内容是 UTF-16（带 BOM），错误信息走控制台代码页
    （中文机器上是 cp936），而某些环境下是 UTF-8。解错的后果不只是乱码——``/XML`` 解错
    等于读不到 ``<Command>``，开关会显示"未启用"，而任务其实好好地在那里。
    """
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16", errors="replace")
    for encoding in ("utf-8", locale.getpreferredencoding(False) or "utf-8"):
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


def schtasks_path(environ: Mapping[str, str] | None = None) -> str:
    """``schtasks.exe`` 的完整路径。

    不写裸文件名：这个调用发生在**已提权**的进程里，让 ``PATH`` 决定执行哪个
    ``schtasks.exe`` 是白送一次以管理员权限运行任意程序的机会（``elevation.py``
    的 :func:`~omnisight.adapters.windows.elevation._explorer_path` 同理）。
    """
    root = _env(environ if environ is not None else os.environ, "SystemRoot") or r"C:\Windows"
    return str(PureWindowsPath(root) / "System32" / "schtasks.exe")


def canonical(command: str) -> str:
    """把命令行归一成可比较的形式。

    两边的写法一定不同：我们交给 ``/TR`` 的是 ``"<exe>" --autostart``，而任务计划程序
    把它拆成 ``<Command>`` 与 ``<Arguments>`` 时**是否保留外层引号并不确定**，路径的
    大小写也可能与 ``sys.executable`` 不一致（Windows 路径不区分大小写）。逐字比较会把
    一个好任务判成"指向旧路径"，然后在用户眼前把开关显示成关闭。
    """
    return " ".join(command.replace('"', "").split()).casefold()


def parse_task(xml: str) -> TaskInfo | None:
    """从 ``schtasks /Query /XML`` 的输出里取命令行与 ``RunLevel``。

    ``ET.fromstring`` 不接受带 ``encoding`` 声明的 ``str``（而我们已经解码过了），
    所以先把声明去掉；命名空间用 ``{*}`` 通配，免得跟着任务计划的 schema 版本走。
    """
    try:
        # 输入是本机 schtasks 的输出，不是外部数据。
        root = ET.fromstring(_DECLARATION.sub("", xml).strip())
    except ET.ParseError:
        logger.debug("任务 XML 解析失败", exc_info=True)
        return None
    command = (root.findtext(".//{*}Exec/{*}Command") or "").strip()
    if not command:
        return None
    arguments = (root.findtext(".//{*}Exec/{*}Arguments") or "").strip()
    run_level = (root.findtext(".//{*}Principal/{*}RunLevel") or "").strip()
    return TaskInfo(command=f"{command} {arguments}".strip(), run_level=run_level)


def is_protected_location(executable: str, environ: Mapping[str, str] | None = None) -> bool:
    """``executable`` 是否位于普通用户不可写的目录。

    比较时在根目录后面补一个分隔符：否则 ``C:\\Program Files Extra\\x.exe`` 会因为
    前缀相同而被当成装在 Program Files 里——那正是这道闸要挡住的东西。
    """
    environ = environ if environ is not None else os.environ
    target = ntpath.normcase(ntpath.normpath(executable))
    for name in PROTECTED_ROOT_VARS:
        root = _env(environ, name)
        if not root:
            continue
        prefix = ntpath.normcase(ntpath.normpath(root)).rstrip("\\") + "\\"
        if target.startswith(prefix):
            return True
    return False


def blocked_reason(
    *,
    elevated: bool,
    frozen: bool | None = None,
    executable: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> str:
    """现在能不能改这个开关；``""`` = 能。返回的文字会原样出现在设置页上。

    顺序是按"能不能解决"排的：形态与位置的问题提权也解决不了，先说它们。
    """
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    executable = executable or sys.executable
    if not frozen:
        return (
            "开发模式下不提供这个开关：登录任务只能指向 Python 解释器，"
            "而真正执行的代码在一个可写的源码目录里，那样的静默提权启动项不安全"
        )
    if not is_protected_location(executable, environ):
        return (
            "需要先把程序装到**系统的** Program Files 或 Windows 目录之下"
            "（%ProgramFiles% 指向的那一个）。别的分区上同名的 Program Files 通常普通用户"
            "就能改，不算；而放在可写目录里的程序，一个登录即静默提权的启动项等于给任何"
            "能改那个目录的程序一条管理员通道"
        )
    if not elevated:
        return "创建和删除这个登录任务本身需要管理员权限：请先用托盘的「以管理员身份重启」"
    return ""


def _current_user(environ: Mapping[str, str]) -> str:
    user = _env(environ, "USERNAME")
    if not user:
        return ""
    domain = _env(environ, "USERDOMAIN")
    return f"{domain}\\{user}" if domain else user


class LogonTaskAutostart:
    """:class:`~omnisight.adapters.ports.ElevatedAutostartControl` 的 Windows 实现。"""

    __slots__ = ("_command", "_environ", "_executable", "_frozen", "_is_elevated", "_task_name")

    def __init__(
        self,
        *,
        task_name: str = TASK_NAME,
        command: str | None = None,
        is_elevated: object = None,
        environ: Mapping[str, str] | None = None,
        frozen: bool | None = None,
        executable: str | None = None,
    ) -> None:
        self._task_name = task_name
        if command is None:
            # 惰性导入，且只在真要问注册表那条机制的命令行时才导：``autostart`` 要
            # ``winreg``，而本模块其余部分（闸门判定、命令行归一、任务 XML 解析）是纯函数。
            # 模块与构造都不碰 winreg，那些判定就能在三个平台上被测——**一道安全判定不该有
            # "只能在 Windows 上才试得出来"的部分**（11 文档 §1）。
            from .autostart import startup_command

            #: 与注册表自启项**共用**一份命令行（含 ``--autostart``）：两条机制启动的必须是
            #: 同一个东西，否则"换成登录任务"会顺带改掉程序对"我是被自启拉起来的"的判断。
            command = startup_command()
        self._command = command
        self._is_elevated = is_elevated
        self._environ = environ if environ is not None else os.environ
        #: 闸门的三个输入全部可注入：一道安全判定不该有"只能在真机上才试得出来"的部分。
        #: 装配处不传，于是走 ``sys`` 的真实值。
        self._frozen = frozen
        self._executable = executable

    @property
    def command(self) -> str:
        return self._command

    # ── 读 ──────────────────────────────────────────────────────────────
    def _run(self, arguments: list[str]) -> tuple[int, str]:
        try:
            completed = subprocess.run(
                [schtasks_path(self._environ), *arguments],
                capture_output=True,
                timeout=TIMEOUT_SECONDS,
                creationflags=CREATE_NO_WINDOW,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:  # pragma: no cover - schtasks 挂住
            raise OSError(f"schtasks 超过 {TIMEOUT_SECONDS:.0f} 秒没有返回") from exc
        output = _decode(completed.stdout) + _decode(completed.stderr)
        return completed.returncode, output

    def _query(self) -> TaskInfo | None:
        code, output = self._run(["/Query", "/TN", self._task_name, "/XML", "ONE"])
        if code != 0:
            # 任务不存在也是非零（1）。这里不区分"没有"和"查失败"：两种情况对用户的
            # 意义相同——开关显示未启用，而重新打开它会用 /F 覆盖任何残留。
            return None
        return parse_task(output)

    def is_present(self) -> bool:
        """任务存在（**可能**指向旧路径或没有提权）。"""
        return self._query() is not None

    def is_enabled(self) -> bool:
        """任务存在、指向当前程序、且真的会提权。三者缺一都算未启用。"""
        info = self._query()
        return (
            info is not None
            and info.elevated
            and canonical(info.command) == canonical(self._command)
        )

    def change_blocked_reason(self) -> str:
        elevated = bool(self._is_elevated() if callable(self._is_elevated) else self._is_elevated)
        return blocked_reason(
            elevated=elevated,
            frozen=self._frozen,
            executable=self._executable,
            environ=self._environ,
        )

    # ── 写 ──────────────────────────────────────────────────────────────
    def set_enabled(self, enabled: bool) -> None:
        reason = self.change_blocked_reason()
        if reason:
            # 端口契约允许调用方先查 ``change_blocked_reason()``，但适配器不能指望它查过：
            # 一个越过闸门建出来的任务就是一条 UAC 绕过通道，这道检查必须在最里面也有。
            raise PermissionError(reason)
        if not enabled:
            code, output = self._run(["/Delete", "/TN", self._task_name, "/F"])
            if code != 0 and self.is_present():
                raise OSError(f"删除登录任务失败：{output.strip()}")
            logger.info("已关闭「登录时以管理员身份启动」")
            return
        arguments = [
            "/Create",
            "/TN",
            self._task_name,
            "/TR",
            self._command,
            "/SC",
            "ONLOGON",
            # 这两个是这条机制的全部意义：HIGHEST 才提权，缺了它任务照样跑但没有权限。
            "/RL",
            "HIGHEST",
            # /IT = 用登录用户的交互式令牌运行。缺了它任务可能在没有桌面的会话里启动
            # （托盘图标不出现），而且 schtasks 会开始索要密码。
            "/IT",
            "/F",
        ]
        user = _current_user(self._environ)
        if user:
            arguments += ["/RU", user]
        code, output = self._run(arguments)
        if code != 0:
            raise OSError(f"创建登录任务失败：{output.strip()}")
        logger.info("已开启「登录时以管理员身份启动」：%s", self._command)
