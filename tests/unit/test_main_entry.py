"""打包入口的早期崩溃护栏（main.py）。

护栏存在的理由是一次真机踩坑：mac 虚拟机上双击 .app 只在 Dock 弹一下就没了——
死在导入期（早于 ``core.crash`` 的钩子装配），而 ``--windowed`` 下 stderr 不存在，
于是数据目录、日志、崩溃报告一个都没留下。护栏用纯标准库把这种死法写成
``STARTUP_ERROR.txt``，让"完全静默的死"变成"一个能贴给开发者的文件"。
"""

from __future__ import annotations

import builtins
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import main  # noqa: E402


def _block_import_of(monkeypatch, *prefixes: str):
    """让 ``builtins.__import__`` 对指定前缀抛 ImportError。

    注意匹配得用前缀：``from omnisight.core import paths`` 进钩子时的名字是
    ``omnisight.core``，而父包导入多半不走钩子（importlib 内部处理），所以按
    "name 以某个前缀开头"判，而不是等值。
    """
    real_import = builtins.__import__

    def guarded(name, *args, **kwargs):
        if any(name == prefix or name.startswith(f"{prefix}.") for prefix in prefixes):
            raise ImportError(f"no module named {name!r}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)


def test_early_crash_lands_in_the_startup_error_file(tmp_path: Path, monkeypatch, capsys):
    """第一落点是数据目录的 STARTUP_ERROR.txt——所有文档指引用户去看的那个文件。"""
    from omnisight.core import paths

    monkeypatch.setattr(paths, "app_root", lambda: tmp_path)
    main._report_early_crash(ValueError("boom"))

    text = (tmp_path / "STARTUP_ERROR.txt").read_text(encoding="utf-8")
    assert "ValueError: boom" in text
    assert "启动早期崩溃" in text
    # 从终端拉起时 stderr 是活的——先印一份。
    assert "ValueError: boom" in capsys.readouterr().err


def test_early_crash_falls_back_to_the_temp_dir(tmp_path: Path, monkeypatch):
    """连 paths 都导入不了（护栏自己就在打包漏收的火力线上）时，临时目录兜底。"""
    _block_import_of(monkeypatch, "omnisight.core")
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    main._report_early_crash(RuntimeError("early"))

    text = (tmp_path / "omnisight-startup-error.txt").read_text(encoding="utf-8")
    assert "RuntimeError: early" in text


def test_the_entry_import_stays_inside_the_guard():
    """护栏要接得住的第一类死法就是 ``from omnisight.app import run`` 这一行本身
    （打包漏收模块）——所以它必须留在 try 块里，不许被"顺手"挪回模块顶层。"""
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    assert "from omnisight.app import run" in source
    assert "from omnisight.app import run\n" not in source.split("if __name__")[0]


def test_guard_catches_import_failures(tmp_path: Path, monkeypatch, capsys):
    """端到端走一遍护栏：模拟打包漏收 omnisight.app 时，__main__ 路径留下
    STARTUP_ERROR.txt 并原样重抛。"""
    from omnisight.core import paths

    monkeypatch.setattr(paths, "app_root", lambda: tmp_path)
    monkeypatch.setattr(sys, "argv", ["OmniSight"])
    _block_import_of(monkeypatch, "omnisight.app")

    with pytest.raises(ImportError):
        exec(
            compile((ROOT / "main.py").read_text(encoding="utf-8"), "main.py", "exec"),
            {"__name__": "__main__"},
        )
    assert "ImportError" in (tmp_path / "STARTUP_ERROR.txt").read_text(encoding="utf-8")
