"""发布前扫描留证（12 文档 M6 判据 2、R2）。

这份工具的正确性几乎全在**判定**上：MpCmdRun 的退出码 2 同时表示"发现威胁"与
"命令失败"，而本机实测到的恰好是后者（Defender 被停用）。只看退出码的实现会把
"什么都没扫"记成"报出威胁"——记录里的一句假话比没有记录更坏，因此这里逐个钉住。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT / "tools", ROOT / "src"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

import scan_record  # noqa: E402

#: 本机真实抓到的输出：Defender 被停用时 MpCmdRun 返回 2 且只说"未指定的错误"。
DISABLED_OUTPUT = """MpCmdRun: Command Line: MpCmdRun.exe -Scan -ScanType 3 -File OmniSight.exe
WARN: Product/Feature disabled
[Failed][0x80004005] 未指定的错误
CmdTool: Failed with hr = 0x80004005."""

CLEAN_OUTPUT = """Scan starting...
Scan finished.
Scanning dist\\OmniSight.exe found no threats."""

DETECTED_OUTPUT = """Scan finished.
Scanning dist\\OmniSight.exe found 1 threats.
Threat: Trojan:Win32/Fake.A"""


@pytest.mark.parametrize(
    ("returncode", "output", "state"),
    [
        (2, DISABLED_OUTPUT, "unavailable"),  # 退出码与"检出"相同，必须靠输出区分
        (2, DETECTED_OUTPUT, "detected"),
        (0, CLEAN_OUTPUT, "clean"),
        (0, "Scanning finished. found 0 threats.", "clean"),  # "found" 子串的陷阱
        (5, "something else entirely", "error"),
    ],
)
def test_interpret_separates_unavailable_from_detected(returncode, output, state):
    assert scan_record.interpret(returncode, output).state == state


def test_only_a_real_detection_blocks_publishing():
    """"扫不了"是留证的缺口，不是证据——它不该把构建判红。"""
    assert scan_record.interpret(2, DETECTED_OUTPUT).blocking is True
    assert scan_record.interpret(2, DISABLED_OUTPUT).blocking is False
    assert scan_record.interpret(0, CLEAN_OUTPUT).blocking is False


def test_unavailable_result_quotes_the_reason():
    result = scan_record.interpret(2, DISABLED_OUTPUT)
    assert "Product/Feature disabled" in result.detail
    assert result.label.startswith("未执行")

def test_decode_prefers_utf8_over_the_locale_encoding(monkeypatch):
    """MpCmdRun 在中文 Windows 上输出 UTF-8，而 locale 首选编码是 cp936。

    按 locale 解码会把"未指定的错误"变成"鏈�鎸囧畾"，而这段文字会被原样抄进
    发布记录——乱码的留证不是留证。
    """
    monkeypatch.setattr(scan_record.locale, "getpreferredencoding", lambda *_: "cp936")
    assert scan_record._decode("未指定的错误".encode()) == "未指定的错误"


def test_decode_falls_back_when_bytes_are_not_utf8(monkeypatch):
    monkeypatch.setattr(scan_record.locale, "getpreferredencoding", lambda *_: "cp936")
    assert scan_record._decode("错误".encode("cp936")) == "错误"


def test_defender_cli_picks_the_newest_engine(tmp_path: Path):
    """版本目录按数值排序。字典序会把 4.18.9999 排在 4.18.26080 之后，
    于是脚本挑一个旧引擎去扫——结论看着一样，用的特征库老了几个月。
    """
    platform_root = tmp_path.joinpath("Microsoft", "Windows Defender", "Platform")
    for name in ("4.18.9999.1-0", "4.18.26080.3-0"):
        directory = platform_root / name
        directory.mkdir(parents=True)
        (directory / scan_record.CLI_NAME).write_text("stub", encoding="utf-8")
    cli, version = scan_record.defender_cli({"ProgramData": str(tmp_path)})
    assert version == "4.18.26080.3-0"
    assert cli is not None and cli.name == scan_record.CLI_NAME


def test_defender_cli_reads_environment_case_insensitively(tmp_path: Path):
    """``dict(os.environ)`` 在 Windows 上把键变成大写，按 ``ProgramData`` 查恒为空——
    症状是脚本安静地报告"本机没装 Defender"（实现时踩到）。"""
    legacy = tmp_path / "Windows Defender"
    legacy.mkdir()
    (legacy / scan_record.CLI_NAME).write_text("stub", encoding="utf-8")
    for key in ("ProgramFiles", "PROGRAMFILES"):
        cli, version = scan_record.defender_cli({key: str(tmp_path)})
        assert cli is not None and version == "系统内置"


def test_defender_cli_reports_absence_instead_of_guessing(tmp_path: Path):
    assert scan_record.defender_cli({"ProgramData": str(tmp_path)}) == (None, "")

@pytest.fixture
def dist(tmp_path: Path) -> Path:
    """两件产物都在的临时 ``dist/``。"""
    directory = tmp_path / "dist"
    directory.mkdir()
    for index, name in enumerate(scan_record.build.artifact_names()):
        (directory / name).write_bytes(b"payload" * (index + 1))
    return directory


def test_collect_hashes_every_artifact_and_can_skip_scanning(dist: Path):
    scanned, engine = scan_record.collect(dist, run_scan=False)
    assert [item.name for item in scanned] == list(scan_record.build.artifact_names())
    assert engine == ""
    for item in scanned:
        assert item.result.state == "skipped"
        assert item.digest == scan_record.build.sha256_of(dist / item.name)
        assert item.size == (dist / item.name).stat().st_size
        assert item.digest in item.lookup  # 查询是按哈希查，不是上传


def test_collect_ignores_artifacts_that_were_not_built(dist: Path):
    """``--no-installer`` 组装出来的 ``dist/`` 里没有安装包，记录里就不该凭空多一行。"""
    (dist / scan_record.build.installer_name()).unlink()
    scanned, _ = scan_record.collect(dist, run_scan=False)
    assert [item.name for item in scanned] == [
        scan_record.build._executable_name(),
        scan_record.build.portable_name(),
    ]


def test_render_records_the_facts_a_user_can_check(dist: Path):
    scanned, _ = scan_record.collect(dist, run_scan=False)
    text = scan_record.render(scanned, version="9.9.9", engine="4.18.1-0")
    assert "9.9.9" in text
    assert all(item.digest in text for item in scanned)
    assert "Get-FileHash" in text
    assert "查询不上传文件" in text  # 否则读者会以为查一下就把产物交出去了
    assert "未提交" in text  # VirusTotal 是人工步骤，不能默认写成已扫
    # 自建产物的哈希对不上是 PyInstaller 的常态，不写清楚会被读成"被篡改"。
    assert "不是逐字节" in text and "不会" in text


def test_render_carries_a_submitted_virustotal_result(dist: Path):
    scanned, _ = scan_record.collect(dist, run_scan=False)
    text = scan_record.render(
        scanned, virustotal="2/72（两个启发式引擎）", virustotal_url="https://example.invalid/r"
    )
    assert "2/72（两个启发式引擎）" in text
    assert "https://example.invalid/r" in text
    assert "未提交" not in text.split("## VirusTotal")[1].splitlines()[1]


def test_the_record_says_which_files_are_actually_published(dist: Path):
    """发布物是便携 zip 与安装包；裸 EXE 仍要被扫（杀软报的是它），但核对下载用的是
    那两件的校验值——混在一起会让用户去核对一个他没下载的文件。"""
    scanned, _ = scan_record.collect(dist, run_scan=False)
    published = [item for item in scanned if item.published]
    assert [item.name for item in published] == list(scan_record.build.published_names())
    text = scan_record.render(scanned)
    assert "发布两件产物" in text
    for item in published:
        assert f"Get-FileHash .\\{item.name}" in text
    assert "内含的可执行文件" in text

def test_main_writes_the_record_and_reports_missing_artifacts(dist: Path, tmp_path: Path, capsys):
    out = tmp_path / "docs" / "scan-record.md"
    assert scan_record.main(["--dist", str(dist), "--out", str(out), "--no-scan"]) == 0
    assert out.exists() and "SHA-256" in out.read_text(encoding="utf-8")

    empty = tmp_path / "empty"
    empty.mkdir()
    assert scan_record.main(["--dist", str(empty), "--out", str(out), "--no-scan"]) == 1
    assert "没有产物" in capsys.readouterr().err


def test_main_fails_when_the_local_scan_detects_something(dist: Path, tmp_path: Path, monkeypatch):
    """检出的产物不该被静默发出去——脚本的退出码要能让发布流程停下来。"""
    monkeypatch.setattr(scan_record, "defender_cli", lambda *_: (Path("stub"), "4.18.1-0"))
    monkeypatch.setattr(
        scan_record, "scan", lambda *_args, **_kwargs: scan_record.interpret(2, DETECTED_OUTPUT)
    )
    out = tmp_path / "record.md"
    assert scan_record.main(["--dist", str(dist), "--out", str(out)]) == 1
    assert "报出威胁" in out.read_text(encoding="utf-8")


def test_argument_parsing_accepts_both_spellings():
    assert scan_record._argument(["--virustotal", "0/70"], "--virustotal") == "0/70"
    assert scan_record._argument(["--virustotal=0/70"], "--virustotal") == "0/70"
    assert scan_record._argument([], "--virustotal") == ""
