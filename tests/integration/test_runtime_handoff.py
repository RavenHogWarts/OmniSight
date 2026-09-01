"""``runtime.json`` 的端口/令牌交接（08 文档 §3.2b 的实现补充）。

它让本机工具（冒烟测试、第二个实例）能访问自己的 API，而不削弱威胁模型：
令牌防的是**网页**，而网页读不到本地文件；能读到这个文件的程序本来就能直接读
数据库（08 文档 §3.1 已接受这一点）。
"""

from __future__ import annotations

import json
import stat
import sys
from pathlib import Path

from omnisight.presentation import security


def test_roundtrip(tmp_path: Path):
    security.write_runtime_file(tmp_path, port=6100, token="abc")
    payload = security.read_runtime_file(tmp_path)
    assert payload["port"] == 6100
    assert payload["token"] == "abc"
    assert payload["pid"] > 0


def test_missing_file_reads_as_none(tmp_path: Path):
    assert security.read_runtime_file(tmp_path) is None


def test_corrupt_file_reads_as_none_instead_of_raising(tmp_path: Path):
    (tmp_path / security.RUNTIME_FILENAME).write_text("{not json", encoding="utf-8")
    assert security.read_runtime_file(tmp_path) is None


def test_removed_on_shutdown(tmp_path: Path):
    security.write_runtime_file(tmp_path, port=6100, token="abc")
    security.remove_runtime_file(tmp_path)
    assert not (tmp_path / security.RUNTIME_FILENAME).exists()
    security.remove_runtime_file(tmp_path)  # 幂等


def test_permissions_restricted_to_owner(tmp_path: Path):
    path = security.write_runtime_file(tmp_path, port=6100, token="abc")
    if sys.platform == "win32":
        # Windows 的 ACL 不映射到 POSIX 权限位，收紧由数据目录本身的 ACL 承担
        # （08 文档 §3.2e）；这里只断言文件确实写出来了。
        assert json.loads(path.read_text(encoding="utf-8"))["token"] == "abc"
        return
    mode = path.stat().st_mode
    assert not mode & stat.S_IRGRP
    assert not mode & stat.S_IROTH


def test_new_token_is_unpredictable_and_long_enough():
    tokens = {security.new_token() for _ in range(50)}
    assert len(tokens) == 50
    assert all(len(token) >= 32 for token in tokens)
