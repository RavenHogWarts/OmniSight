"""登录计划任务这条机制（10 文档 §5.3）。

**几乎整个文件都跨三个平台跑**，包括闸门判定：一道安全判定不该有"只能在 Windows 上才试得
出来"的部分。为此 ``logon_task`` 对 ``autostart``（要 ``winreg``）是惰性导入的，只有两条
真的摸 Windows 的用例标了 ``windows_only``。

这里最要紧的两条不是"功能对不对"：

* **闸门必须在最里面也成立**。一个 ``/RL HIGHEST`` 的登录任务等于"这个 EXE 每次登录都
  无提示地拿到管理员权限"，建在一个用户可写的目录上就是一条现成的 UAC 绕过通道。
* **判定不许把好任务读成坏的**。``schtasks`` 两头的写法一定不同（引号、大小写、
  ``Command``/``Arguments`` 拆分、UTF-16 输出），任何一处解错都会让开关显示"未启用"，
  而任务其实好好地在那里。
"""

from __future__ import annotations

import subprocess

import pytest

from omnisight.adapters.windows import logon_task

PROGRAM_FILES = r"C:\Program Files"
INSTALLED = r"C:\Program Files\OmniSight\OmniSight.exe"
PORTABLE = r"D:\Downloads\OmniSight\OmniSight.exe"

#: 任务计划程序导出的 XML。命名空间、``Command``/``Arguments`` 拆分与外层引号被抹掉
#: 都是真实形状——三者都能把逐字比较判成"指向旧路径"。
TASK_XML = """<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>{run_level}</RunLevel>
    </Principal>
  </Principals>
  <Actions Context="Author">
    <Exec>
      <Command>{command}</Command>
      <Arguments>--autostart</Arguments>
    </Exec>
  </Actions>
</Task>"""


def task_xml(command: str = INSTALLED, run_level: str = logon_task.RUN_LEVEL_HIGHEST) -> str:
    return TASK_XML.format(command=command, run_level=run_level)


class FakeSchtasks:
    """替掉 ``subprocess.run``：记下每一次调用，按剧本回答。

    换在 ``subprocess`` 这一层而不是换掉 ``_run``（和 ``test_elevation.py`` 换
    ``ctypes.WinDLL`` 同一个做法），于是解码、完整路径与"不闪黑框"那个标志也一起被测到。
    """

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.kwargs: list[dict] = []
        self.xml: str | None = None
        self.code = 0
        self.output = ""

    def __call__(self, argv, **kwargs):
        self.calls.append(list(argv))
        self.kwargs.append(kwargs)
        if argv[1] == "/Query":
            if self.xml is None:
                return subprocess.CompletedProcess(argv, 1, b"", "找不到任务".encode("cp936"))
            # /XML 的导出内容是 UTF-16 带 BOM，这里照原样给。
            return subprocess.CompletedProcess(argv, 0, self.xml.encode("utf-16"), b"")
        return subprocess.CompletedProcess(argv, self.code, self.output.encode("utf-8"), b"")

    @property
    def verbs(self) -> list[str]:
        return [call[1] for call in self.calls]


@pytest.fixture
def schtasks(monkeypatch) -> FakeSchtasks:
    fake = FakeSchtasks()
    monkeypatch.setattr(logon_task.subprocess, "run", fake)
    return fake


def control(
    *,
    elevated: bool = True,
    command: str = f'"{INSTALLED}" --autostart',
) -> logon_task.LogonTaskAutostart:
    """一个除 ``elevated`` 外所有闸门都放行的实例（装好在 Program Files 的打包版）。"""
    return logon_task.LogonTaskAutostart(
        command=command,
        is_elevated=lambda: elevated,
        environ={"ProgramFiles": PROGRAM_FILES, "USERNAME": "ravenclaw"},
        frozen=True,
        executable=INSTALLED,
    )


# ── 判定：不许把好任务读成坏的 ──────────────────────────────────────────
@pytest.mark.parametrize(
    "written",
    [
        f'"{INSTALLED}" --autostart',
        f"{INSTALLED} --autostart",  # 外层引号可能被任务计划程序抹掉
        f'"{INSTALLED.upper()}"  --autostart',  # 路径大小写 + 多余空白
    ],
)
def test_canonical_ignores_the_differences_that_are_not_differences(written):
    assert logon_task.canonical(written) == logon_task.canonical(f'"{INSTALLED}" --autostart')


def test_canonical_still_separates_two_different_programs():
    assert logon_task.canonical(f'"{PORTABLE}" --autostart') != logon_task.canonical(
        f'"{INSTALLED}" --autostart'
    )


def test_parse_task_joins_command_with_arguments():
    info = logon_task.parse_task(task_xml())
    assert info is not None
    assert info.command == f"{INSTALLED} --autostart"
    assert info.elevated is True


def test_parse_task_reads_a_task_that_will_not_elevate():
    """任务存在但是 LeastPrivileged 时它照样启动程序，只是不提权——与用户开这个开关的
    目的正好相反，所以按未启用处理。"""
    info = logon_task.parse_task(task_xml(run_level="LeastPrivileged"))
    assert info is not None and info.elevated is False


@pytest.mark.parametrize("xml", ["", "not xml at all", "<Task><Actions/></Task>"])
def test_parse_task_returns_none_instead_of_guessing(xml):
    assert logon_task.parse_task(xml) is None


@pytest.mark.parametrize(
    "raw",
    [
        task_xml().encode("utf-16"),  # /XML 的导出内容带 BOM
        task_xml().encode("utf-8"),
    ],
)
def test_decode_handles_both_shapes_of_schtasks_output(raw):
    assert logon_task.parse_task(logon_task._decode(raw)) is not None


def test_decode_falls_back_to_the_console_code_page(monkeypatch):
    """错误信息走控制台代码页（中文机器上是 cp936）。解错只会得到乱码，但那段文字会
    原样出现在设置页的失败提示里。"""
    monkeypatch.setattr(logon_task.locale, "getpreferredencoding", lambda *_: "cp936")
    assert logon_task._decode("拒绝访问".encode("cp936")) == "拒绝访问"


# ── 闸门 ────────────────────────────────────────────────────────────────
def test_a_neighbouring_directory_is_not_program_files():
    """``C:\\Program Files Extra`` 与 Program Files 前缀相同，而它普通用户可写——
    比较时必须补上分隔符，否则这道闸挡不住任何东西。"""
    environ = {"ProgramFiles": PROGRAM_FILES}
    assert logon_task.is_protected_location(INSTALLED, environ) is True
    assert (
        logon_task.is_protected_location(r"C:\Program Files Extra\OmniSight.exe", environ) is False
    )


def test_protected_roots_are_read_case_insensitively():
    """``dict(os.environ)`` 在 Windows 上把键全变成大写，按 ``ProgramFiles`` 查恒为空
    ——症状是开关无缘无故是灰的（同一个坑在 tools/scan_record.py 里踩过一次）。"""
    for key in ("ProgramFiles", "PROGRAMFILES", "programfiles"):
        assert logon_task.is_protected_location(INSTALLED, {key: PROGRAM_FILES}) is True


def test_nothing_is_protected_when_the_environment_is_empty():
    assert logon_task.is_protected_location(INSTALLED, {}) is False


def test_a_program_files_on_another_drive_does_not_count():
    """本机实测到的情形（2026-09-03）：用户把安装包装到了 ``D:\\Program Files\\OmniSight``。

    那个目录**不是** ``%ProgramFiles%``——数据分区根目录的默认 ACL 通常允许普通用户建
    目录，于是同名的 Program Files 往往是可写的。判定只认环境变量指向的那几个，方向保守；
    而说明文字必须点明这件事，否则用户看着"请装到 Program Files"会以为程序判错了。
    """
    environ = {"ProgramFiles": PROGRAM_FILES}
    elsewhere = r"D:\Program Files\OmniSight\OmniSight.exe"
    assert logon_task.is_protected_location(elsewhere, environ) is False
    reason = logon_task.blocked_reason(
        elevated=True, frozen=True, executable=elsewhere, environ=environ
    )
    assert "%ProgramFiles%" in reason and "分区" in reason


def test_development_mode_is_refused_before_anything_else_is_looked_at():
    """开发模式下任务只能指向解释器，而真正执行的代码在一个可写的源码目录里——对
    ``python.exe`` 做路径判定证明不了任何事情，哪怕它自己装在 Program Files 里。"""
    reason = logon_task.blocked_reason(
        elevated=True,
        frozen=False,
        executable=r"C:\Program Files\Python312\python.exe",
        environ={"ProgramFiles": PROGRAM_FILES},
    )
    assert "开发模式" in reason


def test_a_portable_copy_is_refused_even_when_elevated():
    reason = logon_task.blocked_reason(
        elevated=True, frozen=True, executable=PORTABLE, environ={"ProgramFiles": PROGRAM_FILES}
    )
    assert "Program Files" in reason


def test_being_unelevated_is_the_last_reason_because_it_is_the_fixable_one():
    reason = logon_task.blocked_reason(
        elevated=False, frozen=True, executable=INSTALLED, environ={"ProgramFiles": PROGRAM_FILES}
    )
    assert "管理员" in reason


def test_an_installed_elevated_build_is_allowed():
    assert (
        logon_task.blocked_reason(
            elevated=True,
            frozen=True,
            executable=INSTALLED,
            environ={"ProgramFiles": PROGRAM_FILES},
        )
        == ""
    )


def test_the_gate_holds_inside_the_adapter_too(schtasks):
    """服务层会先查 ``change_blocked_reason()``，但适配器不能指望它查过：一个越过闸门
    建出来的任务就是一条 UAC 绕过通道。"""
    with pytest.raises(PermissionError):
        control(elevated=False).set_enabled(True)
    assert schtasks.calls == [], "被挡住时连 schtasks 都不该跑一次"


# ── 状态与写 ────────────────────────────────────────────────────────────
def test_is_enabled_wants_all_three_conditions(schtasks):
    """存在、指向当前程序、真的会提权。缺一都算未启用。"""
    schtasks.xml = task_xml()
    assert control().is_enabled() is True
    schtasks.xml = task_xml(run_level="LeastPrivileged")
    assert control().is_enabled() is False
    schtasks.xml = task_xml(command=PORTABLE)
    assert control().is_enabled() is False
    schtasks.xml = None
    assert control().is_enabled() is False


def test_a_task_pointing_elsewhere_is_still_present(schtasks):
    """"没有这个任务"与"有一个指向别处的任务"对用户是两件事：后者要提醒他打开开关会
    覆盖掉它。"""
    schtasks.xml = task_xml(command=PORTABLE)
    stale = control()
    assert (stale.is_enabled(), stale.is_present()) == (False, True)


def test_creating_the_task_asks_for_the_two_things_that_matter(schtasks):
    control().set_enabled(True)
    (argv,) = schtasks.calls
    assert argv[0].lower().endswith(r"\system32\schtasks.exe")
    arguments = argv[1:]
    assert arguments[:2] == ["/Create", "/TN"]
    # HIGHEST 才提权（缺了它任务照样跑，只是没有权限做这个开关存在的那件事）；
    # /IT 让它用登录用户的交互式令牌跑（缺了它托盘图标可能根本不出现，且 schtasks
    # 会开始索要密码）。
    assert arguments[arguments.index("/RL") + 1] == "HIGHEST"
    assert "/IT" in arguments
    assert arguments[arguments.index("/SC") + 1] == "ONLOGON"
    assert "/F" in arguments, "没有 /F 时残留的同名任务会让创建直接失败"
    assert arguments[arguments.index("/TR") + 1] == f'"{INSTALLED}" --autostart'
    assert arguments[arguments.index("/RU") + 1] == "ravenclaw"


@pytest.mark.windows_only
def test_no_console_window_flashes_on_the_way(schtasks):
    """打包成窗口程序后启动控制台程序会闪一个黑框，而设置页每打开一次就查一次任务。"""
    control().is_enabled()
    assert schtasks.kwargs[0]["creationflags"] == logon_task.CREATE_NO_WINDOW
    assert logon_task.CREATE_NO_WINDOW != 0, "Windows 上这个常量必须真的存在"


@pytest.mark.windows_only
def test_the_task_launches_exactly_what_the_registry_entry_would():
    """两条机制启动的必须是同一个东西（含 ``--autostart``），否则"换成登录任务"会顺带
    改掉程序对"我是被自启拉起来的"的判断。"""
    assert logon_task.LogonTaskAutostart(is_elevated=False).command.endswith("--autostart")


def test_deleting_uses_force_and_does_not_mind_a_missing_task(schtasks):
    """任务不存在时 schtasks 返回非零。那不是失败——用户要的状态已经达到了。"""
    schtasks.code = 1
    schtasks.output = "找不到任务"
    control().set_enabled(False)
    assert schtasks.verbs == ["/Delete", "/Query"]
    assert "/F" in schtasks.calls[0]


def test_a_real_failure_carries_the_message_schtasks_printed(schtasks):
    schtasks.code = 1
    schtasks.output = "拒绝访问。"
    with pytest.raises(OSError, match="拒绝访问"):
        control().set_enabled(True)


def test_schtasks_is_called_by_full_path():
    """这个调用发生在已提权的进程里：让 ``PATH`` 决定执行哪个 schtasks.exe 是白送一次
    以管理员权限运行任意程序的机会（``elevation._explorer_path`` 同理）。"""
    path = logon_task.schtasks_path({"SystemRoot": r"D:\Windows"})
    assert path == r"D:\Windows\System32\schtasks.exe"
    assert logon_task.schtasks_path({}).lower().endswith(r"\system32\schtasks.exe")


def test_the_task_name_is_ascii():
    """任务名要经 schtasks 的命令行来回一趟，而那一趟的编码取决于控制台代码页：
    中文名字在 cp936 的机器上能用，在别的代码页上会变成一个查不到的名字。"""
    assert logon_task.TASK_NAME.isascii()
