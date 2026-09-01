"""平台泄漏检查器自身的测试（11 文档 §8.3）。

**一个永远不会失败的检查器比没有检查器更糟**——它会让人误以为约束在生效。
因此这里既断言仓库当前是干净的，也断言植入一处违规必须被检出。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[2] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from check_platform_leaks import ALLOWLIST, check_platform_leaks  # noqa: E402


def test_repository_core_layers_are_clean():
    violations = check_platform_leaks()
    assert violations == [], "\n".join(str(v) for v in violations)


@pytest.mark.parametrize(
    "source",
    [
        "import win32api\n",
        "from winreg import OpenKey\n",
        "import sys\nif sys.platform == 'win32':\n    pass\n",
        "import os\nprint(os.name)\n",
        "import ctypes\nctypes.windll.user32.MessageBoxW(None, '', '', 0)\n",
        "import pynput\n",
        "from Xlib import display\n",
    ],
)
def test_planted_violation_is_caught(tmp_path: Path, source: str):
    package = tmp_path / "omnisight"
    (package / "services").mkdir(parents=True)
    (package / "services" / "bad.py").write_text(source, encoding="utf-8")
    assert check_platform_leaks(package) != []


def test_adapters_directory_is_not_guarded(tmp_path: Path):
    """平台代码本该住在 adapters/ 里，检查器不能连它一起报。"""
    package = tmp_path / "omnisight"
    (package / "adapters" / "windows").mkdir(parents=True)
    (package / "adapters" / "windows" / "ok.py").write_text("import win32api\n", encoding="utf-8")
    assert check_platform_leaks(package) == []


def test_allowlist_entries_carry_a_reason():
    """豁免必须写明理由，否则它会慢慢变成一张"随便加"的名单。"""
    assert ALLOWLIST
    for path, reason in ALLOWLIST.items():
        assert reason.strip(), f"{path} 的豁免没有写理由"


def test_allowlisted_file_is_skipped(tmp_path: Path):
    package = tmp_path / "omnisight"
    (package / "core").mkdir(parents=True)
    (package / "core" / "paths.py").write_text(
        "import sys\nprint(sys.platform)\n", encoding="utf-8"
    )
    assert check_platform_leaks(package) == []
