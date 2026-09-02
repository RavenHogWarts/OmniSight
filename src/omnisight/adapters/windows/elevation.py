"""管理员（提权）运行模式（10 文档 §5.2）。

**为什么需要它。** Windows 不允许普通完整性级别的进程收到发往更高完整性级别进程的
输入。以管理员身份运行的编辑器、终端、任务管理器里敲的键，普通权限的 OmniSight
一个也收不到——11 文档人工清单里那条"UAC 提权窗口期间的按键不被记录"只是这条规则
最显眼的一个特例。症状很难归因：程序看起来完全正常，前台应用也认得出来，只是那个
应用的按键数一直是 0。管理员模式把 OmniSight 放到与它们相同的权限层级上。

**为什么是一次性的动作，而不是一个持久开关。** 进程的完整性级别在运行中无法改变，
提权只能靠重启成一个新进程；而"下次开机也用管理员模式"意味着注册表自启项不够用
（注册表 ``Run`` 键无法提权），得换成 ``/RL HIGHEST`` 的计划任务——那等于让一个记录
键盘的程序在每次登录时静默拿到管理员权限。这个决定太重，不该由一个托盘菜单项顺带
做掉，因此管理员模式**只对本次运行有效**（10 文档 §5.2 记下了这个取舍）。

本模块只做三件事：现在是什么权限、能不能提权、以及重新起一个提权的自己。
"""

from __future__ import annotations

import ctypes
import logging
import os
import subprocess
import sys
from collections.abc import Sequence
from ctypes import wintypes
from pathlib import Path, PureWindowsPath
from typing import ClassVar
from urllib.parse import unquote, urlparse

logger = logging.getLogger(__name__)

#: 提权后的新实例带上它：旧实例此刻还握着单实例锁与端口，新实例必须等它退干净
#: （由 :meth:`omnisight.core.lifecycle.Lifecycle._acquire_instance_lock` 实现）。
#: 与 ``autostart.AUTOSTART_FLAG`` 一样，这个字面量与 ``app.py`` 的 argparse 各写一遍，
#: 由 ``tests/adapters/test_elevation.py`` 钉住两处一致。
TAKEOVER_FLAG = "--takeover"

TOKEN_QUERY = 0x0008
#: ``TOKEN_INFORMATION_CLASS``：18 = ``TokenElevationType``，20 = ``TokenElevation``。
TOKEN_ELEVATION_TYPE = 18
TOKEN_ELEVATION = 20

#: UAC 关闭，或当前账户根本不是管理员——两种情况都没有"受限令牌"这回事。
ELEVATION_TYPE_DEFAULT = 1
#: 已经是完整的管理员令牌。
ELEVATION_TYPE_FULL = 2
#: 管理员账户的受限令牌：**同一个账户**确认一次就能提权，这是唯一可以提的情形。
ELEVATION_TYPE_LIMITED = 3

#: ``SEE_MASK_NOASYNC``：调用方紧接着就要停机，而异步执行有可能在 shell 真正接手
#: 之前进程就没了。文档明确要求这种场合带上它。
SEE_MASK_NOASYNC = 0x00000100
SW_SHOWNORMAL = 1
ERROR_CANCELLED = 1223

#: ``CLSID_ShellWindows``。桌面上那个 shell 视图跑在**普通完整性级别**的 explorer 里，
#: 把 ``ShellExecute`` 交给它就等于降权——这是 Windows 上唯一不需要额外服务、计划任务或
#: 令牌操作的降权办法（``open_unelevated`` 的 URL 分支）。
CLSID_SHELL_WINDOWS = "{9BA05972-F6A8-11CF-A442-00A0C90A8F39}"
#: ``IShellWindows.FindWindowSW`` 的两个入参：找桌面那一个，并且要它的 ``IDispatch``。
SWC_DESKTOP = 8
SWFO_NEEDDISPATCH = 1


class SHELLEXECUTEINFOW(ctypes.Structure):
    """``ShellExecuteExW`` 的入参。

    用 ``Ex`` 版本而非 ``ShellExecuteW``，只为了能把"用户在 UAC 确认框上点了取消"
    （``ERROR_CANCELLED``）与真正的失败区分开——前者要安静地继续运行，后者该进日志。
    """

    _fields_: ClassVar = [
        ("cbSize", wintypes.DWORD),
        ("fMask", wintypes.ULONG),
        ("hwnd", wintypes.HWND),
        ("lpVerb", wintypes.LPCWSTR),
        ("lpFile", wintypes.LPCWSTR),
        ("lpParameters", wintypes.LPCWSTR),
        ("lpDirectory", wintypes.LPCWSTR),
        ("nShow", ctypes.c_int),
        ("hInstApp", wintypes.HINSTANCE),
        ("lpIDList", wintypes.LPVOID),
        ("lpClass", wintypes.LPCWSTR),
        ("hkeyClass", wintypes.HKEY),
        ("dwHotKey", wintypes.DWORD),
        # 真实结构里 hIcon 与 hMonitor 是一个联合体，大小相同，这里只需占位。
        ("hIcon", wintypes.HANDLE),
        ("hProcess", wintypes.HANDLE),
    ]


def _token_dword(information_class: int) -> int | None:
    """读一个 DWORD 形状的令牌信息。失败返回 ``None``——探测失败不是异常。"""
    try:
        advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    except OSError:  # pragma: no cover - 系统 DLL 缺失
        return None
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    advapi32.OpenProcessToken.argtypes = (
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.HANDLE),
    )
    advapi32.OpenProcessToken.restype = wintypes.BOOL
    advapi32.GetTokenInformation.argtypes = (
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    )
    advapi32.GetTokenInformation.restype = wintypes.BOOL

    token = wintypes.HANDLE()
    if not advapi32.OpenProcessToken(
        kernel32.GetCurrentProcess(), TOKEN_QUERY, ctypes.byref(token)
    ):
        logger.debug("OpenProcessToken 失败（错误码 %s）", ctypes.get_last_error())
        return None
    try:
        value = wintypes.DWORD()
        written = wintypes.DWORD()
        ok = advapi32.GetTokenInformation(
            token,
            information_class,
            ctypes.byref(value),
            ctypes.sizeof(value),
            ctypes.byref(written),
        )
        if not ok:
            logger.debug(
                "GetTokenInformation(%s) 失败（错误码 %s）",
                information_class,
                ctypes.get_last_error(),
            )
            return None
        return int(value.value)
    finally:
        kernel32.CloseHandle(token)


def is_elevated() -> bool:
    """当前进程是否握着完整的管理员令牌。

    ``IsUserAnAdmin`` 只是兜底：它被官方标注为"可能在未来版本移除"，但在令牌查询失败
    的机器上（组策略锁死、异常的令牌）它仍然给得出一个可用的答案。
    """
    value = _token_dword(TOKEN_ELEVATION)
    if value is not None:
        return value != 0
    try:
        shell32 = ctypes.WinDLL("shell32", use_last_error=True)
        shell32.IsUserAnAdmin.restype = wintypes.BOOL
        return bool(shell32.IsUserAnAdmin())
    except OSError:  # pragma: no cover - 系统 DLL 缺失
        return False


def elevation_type() -> int:
    """``TokenElevationType``。查不到时按最保守的 ``DEFAULT`` 处理（= 不给提权入口）。"""
    value = _token_dword(TOKEN_ELEVATION_TYPE)
    return ELEVATION_TYPE_DEFAULT if value is None else value


def relaunch_arguments(
    argv: Sequence[str] | None = None,
    *,
    frozen: bool | None = None,
    executable: str | None = None,
) -> tuple[str, list[str]]:
    """提权重启要执行的 ``(程序, 参数列表)``。

    刻意做成纯函数：``ShellExecuteExW`` 那一半没法自动测（它要么弹 UAC 要么什么都不
    做），而"命令行拼错了"是这里唯一会真正伤人的错误——参数错一个字，用户点下去就只
    看到程序没了。

    **不带上本次运行的其他参数。** 目前只有 ``--autostart``，而它的语义是"我是被自启项
    拉起来的"；用户从托盘手动提权重启显然不是那回事。
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


def _explorer_path() -> str:
    """``explorer.exe`` 的完整路径。

    不写裸文件名：这个调用发生在**已提权**的进程里，让 ``PATH`` 决定执行哪个
    ``explorer.exe`` 是白送一次以管理员权限运行任意程序的机会。
    """
    root = os.environ.get("SYSTEMROOT") or r"C:\Windows"
    return str(PureWindowsPath(root) / "explorer.exe")


def _local_path(target: str) -> str | None:
    """把 ``target`` 解成一个**本地路径**；它是 URL 时返回 ``None``。

    这个区分是踩出来的（2026-09-02 实测）：**explorer.exe 只可靠地处理路径。**
    把带查询串的 URL（仪表盘地址一定带 ``?token=``）交给它，它会把整个参数当成一个
    看不懂的路径，然后**打开"文档"文件夹**——而 ``Popen`` 照样返回成功，调用方无从
    发现自己刚把用户送错了地方。静默送错比报错糟得多，所以 URL 在这里就被挑出来，
    交给 :func:`shell_dispatch` 那条 COM 通道（见 :meth:`WindowsElevation.open_unelevated`）。
    """
    parsed = urlparse(target)
    scheme = parsed.scheme.lower()
    if scheme == "file":
        path = unquote(parsed.path)
        if parsed.netloc:  # file://server/share → UNC 路径
            return str(PureWindowsPath(f"//{parsed.netloc}{path}"))
        return str(PureWindowsPath(path.lstrip("/")))
    # 单字母 scheme 是 Windows 盘符（``urlparse("E:/data")`` 给出 scheme='e'），
    # 两个字母以上才是真的协议（http、https、mailto……）。
    if len(scheme) > 1:
        return None
    return target


def shell_dispatch() -> object | None:
    """桌面 shell 的 ``IShellDispatch2``；拿不到时返回 ``None``。

    这条链子长，但每一环都必要：``CLSID_ShellWindows`` 拿到的是**已经在跑的** explorer
    里那个集合（不是新建一个进程，那样又会继承管理员令牌），从中找出桌面视图，再顺着
    ``Document.Application`` 取回它的 ``IShellDispatch2``。之后调它的 ``ShellExecute``，
    真正执行的是 explorer 那个普通权限的进程。

    用 ``dynamic.Dispatch`` 而不是 ``win32com.client.Dispatch``：后者会去查类型库、必要时
    在运行时用 makepy **生成**一个包装模块，而打包产物里既没有生成好的模块也不该在用户机
    器上生成代码。纯后期绑定只多一次 ``IDispatch`` 查名字，这里一共调三次。

    失败一律返回 ``None`` 让调用方兜底：拿不到降权通道时"照常打开"仍然是可用的，而抛异常
    会把一次打开仪表盘变成一次崩溃。
    """
    try:
        import pythoncom
        from win32com.client import dynamic
    except ImportError:  # pragma: no cover - 打包漏了 pywin32
        logger.debug("win32com 不可用，降权打开走兜底")
        return None
    try:
        # 托盘回调所在的线程未必初始化过 COM。已经初始化过会返回 S_FALSE（无害），
        # 套间模式不同则抛 RPC_E_CHANGED_MODE——那种情况下后面的调用照样能走。
        try:
            pythoncom.CoInitialize()
        except Exception:  # 见上：这里失败不影响后续调用
            logger.debug("CoInitialize 未成功，继续尝试", exc_info=True)
        windows = dynamic.Dispatch(
            pythoncom.CoCreateInstance(
                CLSID_SHELL_WINDOWS,
                None,
                pythoncom.CLSCTX_LOCAL_SERVER,
                pythoncom.IID_IDispatch,
            )
        )
        desktop = windows.FindWindowSW(
            pythoncom.Empty, pythoncom.Empty, SWC_DESKTOP, 0, SWFO_NEEDDISPATCH
        )
        return desktop.Document.Application
    except Exception:  # pythoncom 抛 com_error，链子断在中途还会是 AttributeError
        logger.debug("拿不到桌面 shell 的 IShellDispatch2", exc_info=True)
        return None


class WindowsElevation:
    """:class:`~omnisight.adapters.ports.ElevationControl` 的 Windows 实现。"""

    __slots__ = ("_elevated", "_type")

    def __init__(self) -> None:
        # 进程的完整性级别在其生命周期内不会变，探测一次就够——而托盘每画一次菜单都会
        # 问一遍状态，那是每次右键都要走的路径。
        self._elevated: bool | None = None
        self._type: int | None = None

    def is_elevated(self) -> bool:
        if self._elevated is None:
            self._elevated = is_elevated()
        return self._elevated

    def can_elevate(self) -> bool:
        """能否**以同一个账户**提权。

        标准用户账户上 ``runas`` 会要求输入**另一个**管理员账户的口令，提权后的进程属于
        那个账户：``%LOCALAPPDATA%`` 随之改变，安装形态下等于对着一个空数据库运行，而
        用户以为自己只是换了权限。这种结果比"那一项是灰的"糟得多，所以这里如实返回
        False，由托盘把入口禁掉并在文字里说明原因。
        """
        if self.is_elevated():
            return False
        if self._type is None:
            self._type = elevation_type()
        return self._type == ELEVATION_TYPE_LIMITED

    def relaunch_elevated(self) -> bool:
        """请求 UAC 提权重启。

        True = 新进程已经在启动，调用方**必须**随即停机（否则两个实例会同时抢锁）；
        False = 用户取消或系统拒绝，当前进程应当照常继续运行，什么都不改。
        """
        if self.is_elevated():
            return False
        program, arguments = relaunch_arguments()
        parameters = subprocess.list2cmdline(arguments)
        info = SHELLEXECUTEINFOW()
        info.cbSize = ctypes.sizeof(info)
        info.fMask = SEE_MASK_NOASYNC
        info.lpVerb = "runas"
        info.lpFile = program
        info.lpParameters = parameters
        info.lpDirectory = os.getcwd()
        info.nShow = SW_SHOWNORMAL
        try:
            shell32 = ctypes.WinDLL("shell32", use_last_error=True)
        except OSError:  # pragma: no cover - 系统 DLL 缺失
            logger.warning("shell32 不可用，无法提权")
            return False
        shell32.ShellExecuteExW.argtypes = (ctypes.POINTER(SHELLEXECUTEINFOW),)
        shell32.ShellExecuteExW.restype = wintypes.BOOL
        logger.info("请求以管理员身份重启：%s %s", program, parameters)
        if shell32.ShellExecuteExW(ctypes.byref(info)):
            return True
        error = ctypes.get_last_error()
        if error == ERROR_CANCELLED:
            logger.info("用户在 UAC 确认框里取消了提权，继续以普通权限运行")
        else:
            logger.warning("ShellExecuteExW 提权失败（错误码 %s）", error)
        return False

    def open_unelevated(self, target: str) -> bool:
        """以普通权限打开本地路径或 URL；没能降权时返回 False，由调用方兜底。

        为什么要降权：子进程默认继承父进程的令牌，管理员模式下直接打开文件管理器或浏览器，
        它们就跟着拿到管理员权限——一个记录键盘的程序不该顺手把浏览器也提上去。

        两种目标走两条路，因为它们的坑不同：

        * **本地路径** → ``explorer.exe``。它跑在普通完整性级别上，把请求转交给它就降了权。
        * **URL** → 桌面 shell 的 ``IShellDispatch2.ShellExecute``（见 :func:`shell_dispatch`）。
          URL **不能**走 explorer：仪表盘地址一定带 ``?token=``，而 explorer 会把整个参数
          当成一个看不懂的路径，然后**打开"文档"文件夹**，同时 ``Popen`` 返回成功——调用方
          连兜底的机会都没有（2026-09-02 实测，见 :func:`_local_path`）。COM 这条路把地址
          原样交给桌面 shell，查询串完整保留（2026-09-03 实测确认）。

        拿不到 COM 通道时返回 False，调用方退回 ``webbrowser.open``：那时浏览器若没在运行
        会跟着以管理员权限启动，代价如实写在 `docs/privacy.md` §8.1 与 10 文档 §5.2。
        """
        if not self.is_elevated():
            return False
        path = _local_path(target)
        if path is None:
            dispatch = shell_dispatch()
            if dispatch is None:
                return False
            try:
                dispatch.ShellExecute(target)
            except Exception:
                logger.exception("桌面 shell 未能打开 %s", target)
                return False
            return True
        try:
            subprocess.Popen([_explorer_path(), path], close_fds=True)
        except OSError:
            logger.exception("explorer.exe 无法打开 %s", path)
            return False
        return True
