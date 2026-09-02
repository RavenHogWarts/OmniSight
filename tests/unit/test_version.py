"""版本号的一致性（M6）。

版本串有**两个消费者**、**两处字面量**：用户看的（EXE 属性页、关于页、发布物名，
``src/omnisight/__init__.py``）与打包元数据（``pyproject.toml``，PEP 440 规范形式）。
两处字面量不可能靠纪律对齐，只能靠测试——这正是 ``__init__.py`` 注释里引用的那条。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
for entry in (TOOLS, ROOT / "src"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from omnisight import __version__  # noqa: E402
from version_info import file_version, is_prerelease, render  # noqa: E402


def _pyproject_version() -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, flags=re.MULTILINE)
    assert match, "pyproject.toml 里找不到 version"
    return match.group(1)


def test_the_two_version_literals_normalize_to_the_same_version():
    """``0.1.0-alpha.1`` 与 ``0.1.0a1`` 按 PEP 440 是同一个版本。"""
    from packaging.version import InvalidVersion, Version

    try:
        left, right = Version(__version__), Version(_pyproject_version())
    except InvalidVersion as exc:  # pragma: no cover - 字面量写坏时给出可读的失败
        pytest.fail(f"版本串不是合法的 PEP 440：{exc}")
    assert left == right, f"__version__={__version__} 与 pyproject 版本漂移了"


def test_current_version_is_a_prerelease():
    """M6 发布的是 ``0.1.0-alpha.1``：属性页与 About 必须把它标成预发布。"""
    assert is_prerelease(__version__)


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("0.1.0-alpha.1", (0, 1, 0, 0)),
        ("0.1.0a1", (0, 1, 0, 0)),
        ("1.2", (1, 2, 0, 0)),
        ("1.2.3", (1, 2, 3, 0)),
        ("1.2.3.4", (1, 2, 3, 4)),
        ("2.0.0.dev0", (2, 0, 0, 0)),
        ("1.0.0-rc.2+local", (1, 0, 0, 0)),
    ],
)
def test_file_version_drops_non_numeric_segments(version, expected):
    """四元组只放得下整数：非数字段（dev/alpha/local）一律丢弃而不是报错。"""
    assert file_version(version) == expected


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("0.1.0-alpha.1", True),
        ("0.1.0a1", True),
        ("1.0.0.dev0", True),
        ("1.0.0-rc.1", True),
        ("1.0.0", False),
        ("1.2.3", False),
    ],
)
def test_is_prerelease_recognizes_every_pep440_spelling(version, expected):
    """漏判的后果是属性页把 alpha 显示成正式产品——正是 version_info 要避免的不诚实。"""
    assert is_prerelease(version) is expected


def test_render_carries_the_version_string_and_prerelease_flag():
    text = render("0.4.1-beta.2")
    assert "'0.4.1-beta.2'" in text  # FileVersion / ProductVersion 用原始串
    assert "OmniSight（预发布）" in text  # ProductName 的用户可见标记
    assert "OmniSight.exe" in text


def test_render_of_a_stable_version_has_no_prerelease_traces():
    text = render("1.0.0")
    assert "OmniSight（预发布）" not in text


def _load_with_pyinstaller(path: Path):
    """让 PyInstaller 自己的加载器解析产物——它对版本文件是整体 ``eval()``，
    结构或语法不合法在这里就会炸，而不是在用户构建时。"""
    from PyInstaller.utils.win32 import versioninfo

    return versioninfo.load_version_info_from_text_file(str(path))


def test_generated_file_round_trips_through_pyinstallers_loader(tmp_path: Path):
    pytest.importorskip("PyInstaller")
    from version_info import write

    target = write(tmp_path / "version_info.txt", "0.4.1-beta.2")
    info = _load_with_pyinstaller(target)
    fixed = info.ffi
    # FixedFileInfo 把四元组拆成 MS/LS 两个 32 位字段：(0, 4, 1, 0)。
    assert fixed.fileVersionMS == (0 << 16) | 4
    assert fixed.fileVersionLS == (1 << 16) | 0
    # 结构：VSVersionInfo.kids = [StringFileInfo([StringTable([StringStruct...])]), VarFileInfo]
    strings = {struct.name: struct.val for struct in info.kids[0].kids[0].kids}
    assert strings["FileVersion"] == "0.4.1-beta.2"
    assert strings["ProductName"] == "OmniSight（预发布）"
    assert strings["OriginalFilename"] == "OmniSight.exe"
