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
2. **EXE 所在目录普通用户改不动**。判定**读目录与 EXE 的 DACL**，不看路径长什么样：
   装到哪个盘都行，只要那个位置未提权的程序碰不到（见 :func:`is_protected_location`）。
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

#: 兜底用的目录前缀：只在 DACL 读不出来时才用（见 :func:`is_protected_location`）。
#: 取环境变量而不是写死盘符：系统装在 D: 的机器不少见。``ProgramW6432`` 是 32 位进程看
#: 64 位 Program Files 的那个变量，一并算上。
PROTECTED_ROOT_VARS = (
    "ProgramFiles",
    "ProgramFiles(x86)",
    "ProgramW6432",
    "SystemRoot",
    "windir",
)

#: 广义"普通用户"：这些 SID 出现在一条允许写的 ACE 里，就意味着一个**未提权**的程序能把
#: EXE 换掉。``BUILTIN\\Administrators``（S-1-5-32-544）**刻意不在其中**——UAC 过滤后的令牌
#: 里那个 SID 是 deny-only，针对它的允许 ACE 给不出任何权限，所以它不是漏洞。
BROAD_SIDS = frozenset(
    {
        "S-1-1-0",  # Everyone
        "S-1-5-11",  # Authenticated Users
        "S-1-5-4",  # INTERACTIVE
        "S-1-5-32-545",  # Users
        "S-1-5-32-546",  # Guests
        "S-1-5-32-547",  # Power Users（历史遗留，实际等价于可写）
    }
)

#: 允许当所有者的主体。**所有者隐含 WRITE_DAC**：他随时能给自己加写权限，于是 DACL 现在
#: 写着什么都不作数。这一条挡住的是"用户自己建的目录"——那种目录的 DACL 往往也很干净。
ADMIN_OWNER_SIDS = frozenset(
    {
        "S-1-5-32-544",  # BUILTIN\Administrators
        "S-1-5-18",  # NT AUTHORITY\SYSTEM
        # NT SERVICE\TrustedInstaller：C:\Program Files 就归它
        "S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464",
    }
)

#: 足以把一个 EXE 换掉的任一权限。``FILE_DELETE_CHILD`` 也算——删掉再放一个新的同样有效。
WRITE_MASK = (
    0x0002  # FILE_WRITE_DATA / FILE_ADD_FILE
    | 0x0004  # FILE_APPEND_DATA / FILE_ADD_SUBDIRECTORY
    | 0x0040  # FILE_DELETE_CHILD
    | 0x00010000  # DELETE
    | 0x00040000  # WRITE_DAC
    | 0x00080000  # WRITE_OWNER
    | 0x10000000  # GENERIC_ALL
    | 0x40000000  # GENERIC_WRITE
)

#: 只影响子对象、对本对象无效的 ACE（``(OI)(CI)(IO)`` 里的那个 IO），不参与判定。
INHERIT_ONLY_ACE = 0x08
ACCESS_ALLOWED_ACE_TYPE = 0x00

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


def _under_protected_root(executable: str, environ: Mapping[str, str]) -> bool:
    """兜底判定：``executable`` 是否在 Program Files / Windows 之下。

    只在 DACL 读不出来时用（见 :func:`is_protected_location`）。比较时在根目录后面补一个
    分隔符：否则 ``C:\\Program Files Extra\\x.exe`` 会因为前缀相同而被当成装在 Program
    Files 里——那正是这道闸要挡住的东西。
    """
    target = ntpath.normcase(ntpath.normpath(executable))
    for name in PROTECTED_ROOT_VARS:
        root = _env(environ, name)
        if not root:
            continue
        prefix = ntpath.normcase(ntpath.normpath(root)).rstrip("\\") + "\\"
        if target.startswith(prefix):
            return True
    return False


def writable_by_normal_users(path: str) -> bool | None:
    """一个**未提权**的程序能改这个文件/目录吗；``None`` = 查不出来。

    读所有者与 DACL，自己判，不做 ``AccessCheck``：那需要一个"普通用户"的令牌，而我们手上
    只有自己的。两条判据：

    * **所有者不是管理员一类** → 直接算可写。所有者隐含 ``WRITE_DAC``，他随时能给自己加权限，
      DACL 现在写着什么都不作数。用户自己建的目录就是这一类，而它们的 DACL 往往看起来很干净。
    * **有一条允许写的 ACE 落在广义"普通用户"上** → 可写。``Administrators`` 不算（见
      :data:`BROAD_SIDS` 的说明）。

    刻意忽略拒绝 ACE：正确的求值顺序会让"拒绝"抵消掉"允许"，而漏算它只会让判定**偏严**
    （把一个其实安全的目录判成可写）。这道闸宁可多拦。
    """
    try:
        import win32security
    except ImportError:  # pragma: no cover - 打包漏了 pywin32
        logger.warning("win32security 不可用，退回按路径前缀判定 EXE 位置")
        return None
    try:
        descriptor = win32security.GetFileSecurity(
            path,
            win32security.OWNER_SECURITY_INFORMATION | win32security.DACL_SECURITY_INFORMATION,
        )
        owner = descriptor.GetSecurityDescriptorOwner()
        dacl = descriptor.GetSecurityDescriptorDacl()
    except Exception:  # pywin32 抛 pywintypes.error，路径不存在也走这里
        logger.debug("读不到 %s 的安全描述符", path, exc_info=True)
        return None
    if owner is not None and win32security.ConvertSidToStringSid(owner) not in ADMIN_OWNER_SIDS:
        return True
    if dacl is None:
        return True  # NULL DACL = 谁都能写
    for index in range(dacl.GetAceCount()):
        ace = dacl.GetAce(index)
        (ace_type, ace_flags), mask, sid = ace[0], ace[1], ace[-1]
        if ace_type != ACCESS_ALLOWED_ACE_TYPE or ace_flags & INHERIT_ONLY_ACE:
            continue
        if not mask & WRITE_MASK:
            continue
        if win32security.ConvertSidToStringSid(sid) in BROAD_SIDS:
            return True
    return False


def is_protected_location(executable: str, environ: Mapping[str, str] | None = None) -> bool:
    """``executable`` 是否位于一个**未提权的程序改不动**的位置。

    **判定读 ACL，不看路径长什么样**（2026-09-03 改）。原先按 ``%ProgramFiles%`` 等前缀判，
    结果把一个完全安全的位置拒掉了：本机实测 ``D:\\Program Files\\OmniSight`` 由提权的安装器
    创建，所有者是 ``BUILTIN\\Administrators``、``Users`` 只有读+执行——它与 ``C:\\Program
    Files`` 下的目录一样动不了，而按前缀判会说"这不是 Program Files"。**装到哪个盘不重要，
    重要的是那个位置未提权的程序碰不到**，而这件事只有 ACL 答得上来。

    目录与 EXE 两个都查：拿到目录的写权限可以换掉整个文件，拿到文件的写权限可以就地改它。

    DACL 读不出来时（缺 pywin32、奇怪的文件系统、路径不存在）退回原来的前缀判定
    ——那比"一律拒绝"有用，也比"一律放行"安全。

    **已知的停止点**：不追溯父目录。如果 ``D:\\Program Files`` 本身归普通用户所有（用户手
    建的目录就是这样），他能改写那一级的 DACL、进而删掉并替换我们这一级。要把这条链走到底
    没有明确的终点，而这道闸的目的是拦住"解压到桌面就开开关"，不是抵抗一个已经拿到你账户、
    还愿意在你眼皮下重排 ACL 的对手——那种对手有比这条启动项更省事的路。
    """
    environ = environ if environ is not None else os.environ
    directory = ntpath.dirname(ntpath.normpath(executable)) or ntpath.normpath(executable)
    verdicts = [writable_by_normal_users(target) for target in (directory, executable)]
    if any(verdict is True for verdict in verdicts):
        return False
    if all(verdict is None for verdict in verdicts):
        return _under_protected_root(executable, environ)
    return True


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
        where = ntpath.dirname(executable) or executable
        return (
            "程序所在的目录**普通用户就能改写**，这种位置不能开这个开关："
            "任何以你的身份运行的程序都能把 EXE 换掉，而这条启动项会在下次登录时"
            "无提示地用管理员权限运行它。装到只有管理员能写的目录（安装包默认的 "
            f"Program Files 就是）之后就能开。当前位置：{where}"
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
