"""发布物组装（10 文档 §10）。

``assemble`` 被设计成**可脱离真实构建单独调用**（``--assemble-only``），测试正是
这么用它的：假 EXE + 临时目录。几条硬判据：

* **发布物只有便携 zip 一件**，裸 EXE 不发布——它带不走许可正文与说明；
* ``portable.marker`` **只进 zip**，不留 ``dist/``——留一份就意味着手动双击
  ``dist/OmniSight.exe`` 会以便携模式跑（M3 偏离 74 的教训）；
* zip 的 ``.sha256`` 内容与产物实际摘要一致（它是用户核对下载的唯一手段）；
* ``README.txt`` 是 CRLF（读者用记事本），且随 zip 走、不摊在 ``dist/`` 里；
* 清单四件套随 zip 分发（缺一件就不是"少个附件"，是分发义务缺失）。

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


def test_assemble_produces_one_artifact_the_portable_zip(release_tree: Path):
    dist = release_tree / "dist"
    artifacts = build.assemble(dist=dist, regenerate_licenses=False)
    exe_name = build._executable_name()
    zip_name = build.artifact_names()[1]

    # 发布物只有 zip 一件；裸 EXE 不发布，也就没有它的校验值文件。
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
        build.assemble(dist=root / "dist", regenerate_licenses=False)


def test_assemble_refuses_when_release_files_are_missing(release_tree: Path):
    (release_tree / "LICENSE").unlink()
    with pytest.raises(SystemExit, match="LICENSE"):
        build.assemble(dist=release_tree / "dist", regenerate_licenses=False)


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
    (artifact := next(iter(build.assemble(dist=dist, regenerate_licenses=False))))
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
    monkeypatch.setattr(build, "assemble", lambda: seen.append("assemble"))
    monkeypatch.setattr(build, "build", lambda **_kwargs: seen.append("build"))
    assert build.main(["--assemble-only"]) == 0
    assert seen == ["assemble"]


def test_help_lists_the_release_flag(capsys):
    assert build.main(["--help"]) == 0
    printed = capsys.readouterr().out
    assert "--release" in printed and "--assemble-only" in printed
    assert "便携 zip" in printed


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
    artifacts = build.assemble(dist=dist, regenerate_licenses=False)
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
    artifacts = build.assemble(dist=release_tree / "dist", regenerate_licenses=False)
    with zipfile.ZipFile(artifacts[0].path) as bundle:
        shipped = bundle.read("README.txt").decode("utf-8")
    assert "未做代码签名" not in shipped


def test_the_readme_points_at_the_zip_not_a_bare_exe():
    """发布只有 zip，校验说明必须对着 zip 说——让用户去核对一个不存在的下载最伤信任。"""
    text = build.render_readme()
    assert build.artifact_names()[1] in text
    assert "不单独发布" in text


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

