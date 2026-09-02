"""提权那一层真正碰 Win32 的部分（10 文档 §5.2、11 文档 §1）。

整个文件都是 ``windows_only``：``ctypes.wintypes`` 在其他平台连导入都不行，所以模块
本身只在夹具里按需导入，收集阶段不会碰它。

**能自动测的与不能的，界线很清楚。** ``ShellExecuteExW("runas")`` 要么弹一个需要人点的
UAC 确认框、要么什么都不做，因此这里测的是它周围那些一旦写错就会静默伤人的东西：

* 重启用的命令行（错一个字，用户点下去只会看到程序没了）；
* "已经是管理员"时绝不再去弹框；
* ``file://`` 换本地路径（``explorer.exe`` 拿到一个自己看不懂的参数会静默无反应）；
* 提权状态的探测调得通、且缓存只查一次。

真人验收那一半（管理员模式的编辑器里敲键能不能统计到）在 ``dev/PROGRESS.md`` 的人工清单里。
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.windows_only


@pytest.fixture
def elevation():
    from omnisight.adapters.windows import elevation as module

    return module


@pytest.fixture
def control(elevation):
    return elevation.WindowsElevation()


# ── 重启用的命令行 ────────────────────────────────────────────────────────
def test_the_frozen_exe_relaunches_itself(elevation):
    program, arguments = elevation.relaunch_arguments(
        ["OmniSight.exe"], frozen=True, executable="C:/Apps/OmniSight.exe"
    )
    assert program.endswith("OmniSight.exe")
    assert arguments == [elevation.TAKEOVER_FLAG]


def test_module_invocation_relaunches_as_a_module(elevation):
    """``python -m omnisight`` 时 argv[0] 是包内 ``__main__.py``，而直接执行那个文件会
    因为相对导入失败——这正是仓库根有一个独立 ``main.py`` 的原因。
    """
    program, arguments = elevation.relaunch_arguments(
        ["E:/repo/src/omnisight/__main__.py"], frozen=False, executable="C:/py/python.exe"
    )
    assert program.endswith("python.exe")
    assert arguments == ["-m", "omnisight", elevation.TAKEOVER_FLAG]


def test_a_script_entry_relaunches_that_script(elevation):
    _program, arguments = elevation.relaunch_arguments(
        ["main.py"], frozen=False, executable="C:/py/python.exe"
    )
    assert arguments[0].endswith("main.py")
    assert arguments[0] != "main.py", "必须是绝对路径：新进程的工作目录未必相同"
    assert arguments[1:] == [elevation.TAKEOVER_FLAG]


def test_an_empty_argv_still_produces_a_runnable_command(elevation):
    _program, arguments = elevation.relaunch_arguments(
        [], frozen=False, executable="C:/py/python.exe"
    )
    assert arguments == ["-m", "omnisight", elevation.TAKEOVER_FLAG]


def test_the_relaunch_does_not_inherit_the_autostart_flag(elevation):
    """``--autostart`` 的语义是"我是被自启项拉起来的"。用户从托盘手动提权不是那回事。"""
    _program, arguments = elevation.relaunch_arguments(
        ["OmniSight.exe", "--autostart"], frozen=True, executable="C:/Apps/OmniSight.exe"
    )
    assert arguments == [elevation.TAKEOVER_FLAG]


def test_the_flag_is_the_one_the_command_line_actually_accepts(elevation):
    """适配器里的字面量与 ``app.py`` 的 argparse 各写一遍，这里钉住两处一致——
    不一致的话新实例会因为"未知参数"直接退出，而症状是"提权后程序没起来"。
    """
    from omnisight.app import build_parser

    assert build_parser().parse_args([elevation.TAKEOVER_FLAG]).takeover is True


# ── 降权打开 ──────────────────────────────────────────────────────────────
def test_explorer_is_taken_from_system_root_not_from_path(elevation, monkeypatch):
    """这个调用发生在已提权的进程里：让 PATH 决定执行哪个 explorer.exe 等于白送一次
    以管理员权限运行任意程序的机会。
    """
    monkeypatch.setenv("SYSTEMROOT", r"D:\Windows")
    assert elevation._explorer_path() == r"D:\Windows\explorer.exe"


def test_explorer_falls_back_to_the_conventional_location(elevation, monkeypatch):
    monkeypatch.delenv("SYSTEMROOT", raising=False)
    assert elevation._explorer_path() == r"C:\Windows\explorer.exe"


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        ("file:///E:/data/omnisight", r"E:\data\omnisight"),
        ("file:///E:/data%20dir/logs", r"E:\data dir\logs"),
        ("FILE:///C:/x", r"C:\x"),
        # 裸路径照原样：``urlparse`` 会把盘符当成单字母 scheme，别被它骗了。
        (r"E:\data\omnisight", r"E:\data\omnisight"),
        ("E:/data/omnisight", "E:/data/omnisight"),
    ],
)
def test_local_targets_are_resolved_to_paths(elevation, target: str, expected: str):
    """``webbrowser.open`` 收 URI，而 explorer.exe 对本地路径的处理最可靠。"""
    assert elevation._local_path(target) == expected


@pytest.mark.parametrize(
    "target",
    [
        "http://127.0.0.1:6100/?token=t",
        "http://127.0.0.1:6100/#about",
        "https://example.org",
    ],
)
def test_urls_are_refused_instead_of_being_handed_to_explorer(elevation, target: str):
    """实测踩到的那个坑（2026-09-02）：explorer.exe 拿到带查询串的 URL 会**打开"文档"
    文件夹**，而 ``Popen`` 照样成功——用户点「打开 OmniSight」看到的是资源管理器。
    静默送错比报错糟得多，所以这里直接挡回去，由调用方按常规方式打开。
    """
    assert elevation._local_path(target) is None


def test_a_url_launches_nothing_at_all_even_when_elevated(control, elevation, monkeypatch):
    launched: list[object] = []
    monkeypatch.setattr(elevation.subprocess, "Popen", lambda *a, **k: launched.append(a))
    control._elevated = True
    assert control.open_unelevated("http://127.0.0.1:6100/?token=t") is False
    assert launched == [], "宁可让调用方兜底，也不能打开一个错的东西"


def test_a_directory_is_opened_through_explorer_when_elevated(control, elevation, monkeypatch):
    launched: list[list[str]] = []
    monkeypatch.setattr(elevation.subprocess, "Popen", lambda args, **k: launched.append(args))
    control._elevated = True
    assert control.open_unelevated("file:///E:/data/omnisight") is True
    assert launched == [[elevation._explorer_path(), r"E:\data\omnisight"]]


def test_nothing_is_launched_when_there_is_nothing_to_de_elevate(control):
    """普通权限下没有降权可做，必须返回 False 让调用方走默认方式。"""
    control._elevated = False
    assert control.open_unelevated("http://127.0.0.1:6100/") is False


# ── 状态探测 ──────────────────────────────────────────────────────────────
def test_the_probe_answers_without_raising(elevation):
    """探测必须永不抛异常：托盘每次右键都要问一遍状态。"""
    assert isinstance(elevation.is_elevated(), bool)
    assert elevation.elevation_type() in {
        elevation.ELEVATION_TYPE_DEFAULT,
        elevation.ELEVATION_TYPE_FULL,
        elevation.ELEVATION_TYPE_LIMITED,
    }


def test_a_full_token_means_elevated(elevation):
    """两个 API 的答案必须自洽。反向不成立：UAC 关闭时令牌是完整的，类型却是 DEFAULT。"""
    if elevation.elevation_type() == elevation.ELEVATION_TYPE_FULL:
        assert elevation.is_elevated() is True


def test_the_state_is_probed_once_and_then_cached(elevation, monkeypatch):
    calls: list[int] = []

    def counted() -> bool:
        calls.append(1)
        return False

    monkeypatch.setattr(elevation, "is_elevated", counted)
    instance = elevation.WindowsElevation()
    assert instance.is_elevated() is False
    assert instance.is_elevated() is False
    assert len(calls) == 1, "进程的完整性级别不会中途改变，问一次就够"


def test_being_admin_already_offers_nothing_more(control):
    """已经是管理员时既不该显示"可以提权"，更不该真的再去弹一次 UAC。"""
    control._elevated = True
    assert control.can_elevate() is False
    assert control.relaunch_elevated() is False


def test_only_a_limited_admin_token_can_elevate_in_place(control, elevation):
    """标准用户账户提权会切换到**另一个账户**，``%LOCALAPPDATA%`` 随之改变——那等于
    对着一个空数据库运行，而用户以为自己只是换了权限。
    """
    control._elevated = False
    control._type = elevation.ELEVATION_TYPE_LIMITED
    assert control.can_elevate() is True
    control._type = elevation.ELEVATION_TYPE_DEFAULT
    assert control.can_elevate() is False


# ── 单实例锁跨权限层级（这条规则的存在完全是因为管理员模式）─────────────────
@pytest.fixture
def fake_kernel32(monkeypatch):
    """让 ``CreateMutexW`` 返回 NULL，并给出指定的错误码。"""
    import ctypes

    class Function:
        argtypes = None
        restype = None

        def __call__(self, *_args: object) -> int:
            return 0

    class FakeDll:
        def __getattr__(self, _name: str) -> Function:
            return Function()

    def install(error_code: int) -> None:
        monkeypatch.setattr(ctypes, "WinDLL", lambda *_a, **_k: FakeDll())
        monkeypatch.setattr(ctypes, "get_last_error", lambda: error_code)

    return install


def test_a_mutex_we_cannot_open_means_an_instance_is_already_running(fake_kernel32):
    """管理员模式的实例把互斥体建在更高的完整性级别上，普通权限的进程连打开都不行。

    ``ERROR_ACCESS_DENIED`` 在这里只有一种解释：同名对象被一个我们碰不到的进程占着。
    当成"首个实例"启动会得到两个记录器同时往一个库里写，那比多余地拦一次糟得多。
    """
    from omnisight.adapters.windows import single_instance

    fake_kernel32(single_instance.ERROR_ACCESS_DENIED)
    assert single_instance.NamedMutexInstanceLock(r"Local\OmniSight.Test").acquire() is False


def test_other_mutex_failures_still_let_the_program_start(fake_kernel32):
    """拿不到锁本身不是"已有实例在跑"——那种情况下拒绝启动就是白挡用户一次。"""
    from omnisight.adapters.windows import single_instance

    fake_kernel32(1450)  # ERROR_NO_SYSTEM_RESOURCES
    assert single_instance.NamedMutexInstanceLock(r"Local\OmniSight.Test").acquire() is True
