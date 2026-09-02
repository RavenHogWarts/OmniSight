"""发布物组装（10 文档 §10）。

``assemble`` 被设计成**可脱离真实构建单独调用**（``--assemble-only``），测试正是
这么用它的：假 EXE + 临时目录。几条硬判据：

* **发布物两件**：便携 zip 与安装包，裸 EXE 不发布——它带不走许可正文与说明；
* ``portable.marker`` **只进 zip**，不留 ``dist/``、更不进安装包——留一份就意味着手动
  双击 ``dist/OmniSight.exe`` 会以便携模式跑（M3 偏离 74 的教训），而装进 Program Files
  的那一份带上它只会让程序往一个不可写的目录写数据；
* 每件发布物的 ``.sha256`` 内容与产物实际摘要一致（它是用户核对下载的唯一手段）；
* ``README.txt`` 是 CRLF（读者用记事本），且**两种形态各一份**——数据位置与卸载步骤
  完全不同，把两套说明并排写进同一份文件等于让用户先猜自己装的是哪一种；
* 清单四件套随两件产物分发（缺一件就不是"少个附件"，是分发义务缺失）。

**除专门测安装包的那几条，其余用例一律 ``installer=False``**：编译安装包要 Inno Setup
的 ISCC.exe，而测试不该依赖一个可选的外部工具链（非 Windows 上更是根本没有）。

代码签名（10 文档 §2.3）的三条判据在文件末尾：默认不签名也能构建、签名**发生在
算摘要之前**、以及口令不进构建日志。
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
for entry in (TOOLS, ROOT / "src"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

import build  # noqa: E402


@pytest.fixture
def release_tree(tmp_path: Path, monkeypatch) -> Path:
    """一个自足的"仓库"：根目录、build/、dist/（含假 EXE）全在临时目录里。

    必须整体替换 ``ROOT``——``assemble`` 从仓库根拷贝随产物分发的文件，让它读
    真仓库的话，CI 的全新检出上（许可清单尚未生成）这些用例会假失败。
    """
    root = tmp_path / "repo"
    dist = root / "dist"
    (root / "build").mkdir(parents=True)
    dist.mkdir(parents=True)
    for name in build.RELEASE_FILES:
        (root / name).write_text(f"content of {name}\n", encoding="utf-8")
    exe = dist / build._executable_name()
    exe.write_bytes(b"MZ fake exe payload")
    monkeypatch.setattr(build, "ROOT", root)
    monkeypatch.setattr(build, "BUILD", root / "build")
    monkeypatch.setattr(build, "DIST", dist)
    return root


def test_render_readme_answers_the_four_questions():
    """怎么启动、数据在哪、怎么暂停、怎么彻底卸载——便携包读者的自足性（§10）。"""
    text = build.render_readme(port=6100)
    assert "6100" in text
    assert "完全卸载" in text
    assert "portable.marker" in text
    assert "%LOCALAPPDATA%" in text
    assert "暂停记录" in text
    assert "只支持 Windows" in text and "尚未实现" in text
    assert "Get-FileHash" in text  # 校验手段必须写在离产物最近的地方


def test_render_readme_takes_the_port_from_the_default_config():
    """端口不写死：改默认端口那天 README 不能剩一个错的。"""
    default_port = build.render_readme()
    assert str(build._default_port()) in default_port


def test_assemble_without_an_installer_produces_just_the_portable_zip(release_tree: Path):
    dist = release_tree / "dist"
    artifacts = build.assemble(dist=dist, regenerate_licenses=False, installer=False)
    exe_name = build._executable_name()
    zip_name = build.portable_name()

    # 裸 EXE 不发布，也就没有它的校验值文件。
    assert [item.path.name for item in artifacts] == [zip_name]
    assert not (dist / f"{exe_name}.sha256").exists()

    # zip 内容：EXE、标记、README、四件套，且**不含任何多余文件**。
    with zipfile.ZipFile(dist / zip_name) as bundle:
        names = set(bundle.namelist())
    assert {exe_name, build.PORTABLE_MARKER, "README.txt", *build.RELEASE_FILES} == names

    # dist/ 里只留要发出去的东西 + 构建产物本身：说明与清单随 zip 走，不摊在这儿。
    assert not (dist / build.PORTABLE_MARKER).exists()
    assert not (dist / "README.txt").exists()
    assert not (dist / "LICENSE").exists()
    assert {path.name for path in dist.iterdir()} == {exe_name, zip_name, f"{zip_name}.sha256"}

    # README.txt 面向 Windows 记事本：显式 CRLF。
    readme = (build.BUILD / "portable" / "README.txt").read_bytes()
    assert b"\r\n" in readme and b"\n" not in readme.replace(b"\r\n", b"")

    # 校验值与产物实际摘要一致，格式可被 sha256sum / Get-FileHash 使用。
    for item in artifacts:
        content = (dist / f"{item.path.name}.sha256").read_text(encoding="utf-8")
        assert content.startswith(item.digest)
        assert item.path.name in content
        assert build.sha256_of(item.path) == item.digest

    # EXE 本身不被组装过程改动。
    assert (dist / exe_name).read_bytes() == b"MZ fake exe payload"


def test_assemble_refuses_to_run_without_an_exe(tmp_path: Path, monkeypatch):
    root = tmp_path / "repo"
    (root / "dist").mkdir(parents=True)
    monkeypatch.setattr(build, "ROOT", root)
    monkeypatch.setattr(build, "BUILD", root / "build")
    with pytest.raises(SystemExit, match="找不到构建产物"):
        build.assemble(dist=root / "dist", regenerate_licenses=False, installer=False)


def test_assemble_refuses_when_release_files_are_missing(release_tree: Path):
    (release_tree / "LICENSE").unlink()
    with pytest.raises(SystemExit, match="LICENSE"):
        build.assemble(dist=release_tree / "dist", regenerate_licenses=False, installer=False)


def test_clean_dist_preserves_user_data(release_tree: Path):
    """M3 偏离 74 的钉子：``dist/data/`` 是用户数据（便携实例落进去的），构建清理
    必须永远绕路——删掉它等于静默毁掉用户已采集的数据。"""
    dist = release_tree / "dist"
    (dist / "data").mkdir()
    (dist / "data" / "omnisight.db").write_bytes(b"user data")
    (dist / "stale.txt").write_text("构建残留", encoding="utf-8")
    build._clean_dist()
    assert (dist / "data" / "omnisight.db").exists()
    assert not (dist / "stale.txt").exists()


def test_artifact_describe_mentions_size_and_digest(release_tree: Path):
    dist = release_tree / "dist"
    (artifact := next(iter(build.assemble(dist=dist, regenerate_licenses=False, installer=False))))
    line = artifact.describe()
    assert artifact.path.name in line
    assert "sha256=" in line
    assert "MB" in line


# ── 命令行：组装是发布动作，本地构建不做 ────────────────────────────────


def test_a_plain_build_does_not_assemble_a_release(monkeypatch):
    """本地一天构建好几次；每次都重算许可清单、打 zip、算大文件摘要纯属白等。"""
    calls: list[bool] = []
    monkeypatch.setattr(build, "build", lambda **kwargs: calls.append(kwargs["assemble_release"]))
    build.main([])
    build.main(["--release"])
    assert calls == [False, True]


def test_assemble_only_skips_pyinstaller(monkeypatch):
    """``--assemble-only`` 用现有 EXE 重新组装，不该再跑一次 PyInstaller。"""
    seen: list[str] = []
    monkeypatch.setattr(build, "assemble", lambda **_kwargs: seen.append("assemble"))
    monkeypatch.setattr(build, "build", lambda **_kwargs: seen.append("build"))
    assert build.main(["--assemble-only"]) == 0
    assert seen == ["assemble"]


def test_no_installer_reaches_both_paths(monkeypatch):
    """没装 Inno Setup 的人也要能组装出便携 zip——那个开关必须真的传下去。"""
    seen: list[bool] = []
    monkeypatch.setattr(build, "assemble", lambda **kwargs: seen.append(kwargs["installer"]))
    monkeypatch.setattr(build, "build", lambda **kwargs: seen.append(kwargs["installer"]))
    build.main(["--assemble-only", "--no-installer"])
    build.main(["--release", "--no-installer"])
    build.main(["--release"])
    assert seen == [False, False, True]


def test_help_lists_the_release_flag(capsys):
    assert build.main(["--help"]) == 0
    printed = capsys.readouterr().out
    assert "--release" in printed and "--assemble-only" in printed
    assert "--no-installer" in printed
    assert "便携 zip" in printed and "安装包" in printed


# ── 代码签名（10 文档 §2.3）──────────────────────────────────────────────


def test_signing_is_off_unless_a_certificate_is_configured():
    """签名是可选项：没有证书的人也要能自行构建（§2.3 的表格）。"""
    assert build.signing_from_env({}) is None
    assert build.signing_from_env({"OMNISIGHT_SIGNTOOL": "signtool.exe"}) is None
    assert build.signing_from_env({"OMNISIGHT_SIGN_THUMBPRINT": "AB12"}) is not None
    assert build.signing_from_env({"OMNISIGHT_SIGN_PFX": "cert.pfx"}) is not None


def test_signing_command_uses_sha256_for_both_digest_and_timestamp():
    """只给 ``/fd sha256`` 而漏掉 ``/td sha256``，时间戳仍按 SHA-1 处理。"""
    config = build.signing_from_env({"OMNISIGHT_SIGN_THUMBPRINT": "AB12"})
    command = config.command(Path("dist/OmniSight.exe"))
    assert command[:4] == ["signtool", "sign", "/fd", "sha256"]
    assert "/sha1" in command and "AB12" in command
    assert command[command.index("/tr") + 1] == build.DEFAULT_TIMESTAMP_URL
    assert command[command.index("/td") + 1] == "sha256"
    assert command[-1].endswith("OmniSight.exe")


def test_signing_never_prints_the_certificate_password():
    """构建日志会被贴进 issue。"""
    config = build.signing_from_env(
        {"OMNISIGHT_SIGN_PFX": "cert.pfx", "OMNISIGHT_SIGN_PASSWORD": "s3cret"}
    )
    described = config.describe(Path("dist/OmniSight.exe"))
    assert "s3cret" not in described
    assert "***" in described
    assert "s3cret" in config.command(Path("dist/OmniSight.exe"))  # 真命令里当然要有


def test_assemble_signs_before_zipping_and_hashing(release_tree: Path, monkeypatch):
    """顺序颠倒就会发出一份**校验不上**的产物，而用户核对失败的第一反应是"被篡改了"。"""
    dist = release_tree / "dist"
    config = build.Signing(thumbprint="AB12")
    monkeypatch.setattr(build, "signing_from_env", lambda *_args: config)
    # 假签名：像真 signtool 一样改写 EXE 的字节。
    monkeypatch.setattr(
        build, "sign", lambda exe, _config: exe.write_bytes(exe.read_bytes() + b" signature")
    )
    artifacts = build.assemble(dist=dist, regenerate_licenses=False, installer=False)
    exe_name = build._executable_name()

    # 进 zip 的必须是签过名的那份字节。
    with zipfile.ZipFile(artifacts[0].path) as bundle:
        assert bundle.read(exe_name).endswith(b" signature")

    # 记下来的校验值是 zip 自己的摘要，且与磁盘上的文件一致。
    recorded = (dist / f"{artifacts[0].path.name}.sha256").read_text(encoding="utf-8")
    assert recorded.startswith(build.sha256_of(artifacts[0].path))


def test_readme_stops_claiming_unsigned_when_the_build_is_signed(release_tree: Path, monkeypatch):
    """"本程序未做代码签名"在签名构建里是假话，而它出现在信任成本最高的那一屏上。"""
    unsigned = build.render_readme(signed=False)
    signed = build.render_readme(signed=True)
    assert "未做代码签名" in unsigned and "未做代码签名" not in signed
    assert "数字签名" in signed
    assert "Get-FileHash" in signed  # 签名之后校验值仍然要给

    monkeypatch.setattr(build, "signing_from_env", lambda *_args: build.Signing(thumbprint="AB12"))
    monkeypatch.setattr(build, "sign", lambda *_args: None)
    artifacts = build.assemble(
        dist=release_tree / "dist", regenerate_licenses=False, installer=False
    )
    with zipfile.ZipFile(artifacts[0].path) as bundle:
        shipped = bundle.read("README.txt").decode("utf-8")
    assert "未做代码签名" not in shipped


def test_the_readme_points_at_the_artifact_it_ships_with(release_tree: Path):
    """校验说明必须对着**用户手上那个文件**说——让人去核对一个他没下载的东西最伤信任。"""
    portable = build.render_readme(portable=True)
    installed = build.render_readme(portable=False)
    assert build.portable_name() in portable
    assert build.installer_name() not in portable
    assert build.installer_name() in installed
    assert "不单独发布" in portable and "不单独发布" in installed


def test_the_installed_readme_answers_the_two_questions_that_differ(release_tree: Path):
    """安装版与便携版真正不同的只有两件事：数据在哪、怎么卸载。"""
    installed = build.render_readme(portable=False)
    assert "%LOCALAPPDATA%" in installed
    assert "portable.marker），数据在解压目录里" not in installed
    assert "已安装的应用" in installed and "卸载" in installed
    # 卸载会问要不要删数据，且**默认保留**——静默删掉几个月的记录是不可接受的。
    assert "默认保留" in installed
    # 「开始」菜单才是安装版的入口，双击 EXE 是便携版的说法。
    assert "开始" in installed


def test_a_failed_signature_aborts_instead_of_shipping_unsigned(monkeypatch, tmp_path: Path):
    """配置了证书却发出未签名产物是最坏的失败：校验值照样对得上，属性页却是空的。"""
    exe = tmp_path / "OmniSight.exe"
    exe.write_bytes(b"MZ")
    monkeypatch.setattr(
        build.subprocess, "run", lambda *_args, **_kwargs: SimpleNamespace(returncode=1)
    )
    with pytest.raises(SystemExit, match="signtool 失败"):
        build.sign(exe, build.Signing(thumbprint="AB12"))


def test_a_missing_signtool_says_which_variable_points_at_it(monkeypatch, tmp_path: Path):
    exe = tmp_path / "OmniSight.exe"
    exe.write_bytes(b"MZ")

    def missing(*_args, **_kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(build.subprocess, "run", missing)
    with pytest.raises(SystemExit, match="OMNISIGHT_SIGNTOOL"):
        build.sign(exe, build.Signing(tool="nope.exe", thumbprint="AB12"))


# ── 安装包（10 文档 §10.1）──────────────────────────────────────────────


def test_find_iscc_prefers_the_environment_variable(tmp_path: Path):
    """自动发现只能覆盖常见位置；"我把 Program Files 放在 D 盘"这类机器全靠这个变量。"""
    iscc = tmp_path / "ISCC.exe"
    iscc.write_bytes(b"MZ")
    assert build.find_iscc({build.ISCC_ENV: str(iscc)}) == iscc
    # 给目录也行：谁都会顺手粘一个安装目录进去。
    assert build.find_iscc({build.ISCC_ENV: str(tmp_path)}) == iscc
    # 带引号的路径同样常见（从属性页复制过来就带着引号）。
    assert build.find_iscc({build.ISCC_ENV: f'"{iscc}"'}) == iscc


def test_a_wrong_iscc_path_does_not_fall_back_silently(tmp_path: Path):
    """显式指定却写错时回退到另一个编译器，会让用户以为自己指定的那个生效了。"""
    assert build.find_iscc({build.ISCC_ENV: str(tmp_path / "nope" / "ISCC.exe")}) is None


def test_find_iscc_looks_inside_program_files(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(build.shutil, "which", lambda _name: None)
    target = tmp_path / "Inno Setup 7" / build.ISCC_NAME
    target.parent.mkdir(parents=True)
    target.write_bytes(b"MZ")
    assert build.find_iscc({"ProgramFiles": str(tmp_path)}) == target


def test_a_missing_compiler_names_the_variable_and_the_way_out(monkeypatch):
    """``--release`` 缺一件产物必须让构建红掉——"这次只有便携版"与"忘了装 Inno"
    在 ``dist/`` 里长得一模一样。
    """
    monkeypatch.setattr(build, "find_iscc", lambda *_args: None)
    with pytest.raises(SystemExit, match="OMNISIGHT_ISCC"):
        build.build_installer()
    monkeypatch.setattr(build, "find_iscc", lambda *_args: None)
    with pytest.raises(SystemExit, match="--no-installer"):
        build.build_installer()


def test_the_installer_is_signed_and_hashed_like_the_zip(release_tree: Path, monkeypatch):
    """安装包才是用户真正双击的那个文件，SmartScreen 首先看的也是它。"""
    dist = release_tree / "dist"
    setup = dist / build.installer_name()

    def fake_iscc(target_dist: Path, **_kwargs) -> Path:
        setup.write_bytes(b"MZ fake setup")
        return setup

    monkeypatch.setattr(build, "build_installer", fake_iscc)
    monkeypatch.setattr(build, "signing_from_env", lambda *_args: build.Signing(thumbprint="AB12"))
    monkeypatch.setattr(
        build, "sign", lambda path, _config: path.write_bytes(path.read_bytes() + b" signature")
    )
    artifacts = build.assemble(dist=dist, regenerate_licenses=False, installer=True)

    assert [item.path.name for item in artifacts] == [
        build.portable_name(),
        build.installer_name(),
    ]
    # 签名排在算摘要之前：顺序颠倒就会发出一份校验不上的安装包。
    assert setup.read_bytes().endswith(b" signature")
    for item in artifacts:
        recorded = (dist / f"{item.path.name}.sha256").read_text(encoding="utf-8")
        assert recorded.startswith(build.sha256_of(item.path))


def test_the_installer_stage_is_not_the_portable_one(release_tree: Path):
    """装进 Program Files 的那一份带上 ``portable.marker`` 只会让程序往不可写的目录
    写数据，然后启动失败。``LICENSE`` 还要换成 Inno 能显示的 ``LICENSE.txt``。
    """
    stage = build._stage_installer_files()
    names = {path.name for path in stage.iterdir()}
    assert build.PORTABLE_MARKER not in names
    assert "LICENSE.txt" in names and "LICENSE" not in names
    assert {"README.txt", "THIRD_PARTY_NOTICES.md", "config.example.json"} <= names
    # Inno 用 RichEdit 显示许可，只有 LF 的文本会挤成一行。
    license_text = (stage / "LICENSE.txt").read_bytes()
    assert b"\r\n" in license_text
    readme = (stage / "README.txt").read_bytes()
    assert b"\r\n" in readme and b"\n" not in readme.replace(b"\r\n", b"")


# ── 安装脚本本身（installer/omnisight.iss）─────────────────────────────


def _iss_text() -> str:
    return build.INSTALLER_SCRIPT.read_text(encoding="utf-8-sig")


def test_the_installer_script_is_saved_with_a_bom():
    """Inno 只在见到 BOM 时才按 UTF-8 解析 .iss。没有它，向导上的中文全是乱码——
    而这件事在编译时**不报错**，只有真的运行一次安装包才看得出来。
    """
    assert build.INSTALLER_SCRIPT.read_bytes().startswith(b"\xef\xbb\xbf")


def test_the_installer_waits_for_the_running_instance():
    """``AppMutex`` 必须与程序自己的单实例互斥体同名，否则升级时会去覆盖一个正在
    运行的 EXE：Windows 拒绝写入，安装报错，而原因完全看不出来。
    """
    import re

    source = (
        ROOT / "src" / "omnisight" / "adapters" / "windows" / "single_instance.py"
    ).read_text(encoding="utf-8")
    match = re.search(r'DEFAULT_MUTEX_NAME = r"([^"]+)"', source)
    assert match, "单实例锁的名字变了形态，这条断言要跟着改"
    assert f"AppMutex={match.group(1)}" in _iss_text()


def test_the_installer_asks_for_admin_because_program_files_is_the_point():
    """装到普通用户不可写的目录是安装版**存在的理由**（10 文档 §5.2 的取舍表），
    不是顺手要的权限。
    """
    text = _iss_text()
    assert "PrivilegesRequired=admin" in text
    assert "DefaultDirName={autopf}" in text


def test_the_installer_never_ships_the_portable_marker():
    """便携标记进了 Program Files 就是让程序往一个不可写的目录写数据。"""
    sources = [line for line in _iss_text().splitlines() if line.strip().startswith("Source:")]
    assert sources, "[Files] 段空了？"
    assert not any(build.PORTABLE_MARKER in line for line in sources)


def test_the_installer_launches_the_app_without_its_own_admin_token():
    """安装器是提权的：不加 ``runasoriginaluser``，装完启动的程序会继承管理员权限，
    用户会莫名其妙看到托盘写着"管理员模式"。
    """
    run_lines = _iss_text().split("[Run]")[1].split("[")[0]
    assert "runasoriginaluser" in run_lines


def test_the_installer_output_name_matches_the_artifact_list():
    """名字在两处各写一遍，改名那天扫描记录与校验值会静默少一件。"""
    stem = build.installer_name().removesuffix(".exe")
    assert "OutputBaseFilename={#AppName}-Setup" in _iss_text()
    assert stem.endswith("-Setup")



def test_the_uninstaller_removes_the_logon_task():
    """任务名在 .iss 与 logon_task.py 里各写一遍，两处必须一致（``AppMutex`` 同理）。

    不一致的后果是卸载后留下一条**指向已删除 EXE 的静默提权启动项**——它启动不了任何
    东西，但"卸载后再无残留"这句承诺要清的正是这种东西，而没人会去任务计划里核对。
    """
    import re

    source = (ROOT / "src" / "omnisight" / "adapters" / "windows" / "logon_task.py").read_text(
        encoding="utf-8"
    )
    match = re.search(r'TASK_NAME = "([^"]+)"', source)
    assert match, "任务名变了形态，这条断言要跟着改"
    text = _iss_text()
    assert "[UninstallRun]" in text
    assert f'/Delete /TN ""{match.group(1)}"" /F' in text


def test_the_windows_build_carries_the_com_modules_for_de_elevation():
    """``pythoncom`` / ``win32com.client.dynamic`` 是惰性导入的，漏了它们不会让程序崩——
    只会让管理员模式下的浏览器悄悄跟着提权（elevation.shell_dispatch 退回 None）。
    这种缺失谁都发现不了，所以打包参数里显式写上。
    """
    windows_args = build.PLATFORM["win32"]
    assert "--hidden-import=pythoncom" in windows_args
    assert "--hidden-import=win32com.client.dynamic" in windows_args
