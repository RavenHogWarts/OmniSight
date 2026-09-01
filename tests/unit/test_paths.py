"""路径解析。

重点不是"拼对了字符串"，而是三条会让用户丢数据的行为：便携标记必须生效、
旧位置必须沿用、资源目录与数据目录必须分开。
"""

from __future__ import annotations

from pathlib import Path

from omnisight.core import paths


def test_portable_marker_redirects_to_adjacent_data(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(paths, "exe_dir", lambda: tmp_path)
    (tmp_path / paths.PORTABLE_MARKER).touch()
    assert paths.is_portable() is True
    assert paths.app_root() == tmp_path
    assert paths.data_dir(paths.app_root()) == tmp_path / "data"


def test_platform_convention_used_without_marker(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(paths, "exe_dir", lambda: tmp_path)
    monkeypatch.setattr(paths, "_platform_app_dir", lambda: tmp_path / "conventional")
    assert paths.app_root() == tmp_path / "conventional"


def test_existing_adjacent_database_is_never_abandoned(tmp_path: Path, monkeypatch):
    """升级场景：旧版把库写在 exe 同级，改用惯例目录会让用户以为记录全丢了。"""
    monkeypatch.setattr(paths, "exe_dir", lambda: tmp_path)
    monkeypatch.setattr(paths, "_platform_app_dir", lambda: tmp_path / "conventional")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / paths.DATABASE_FILENAME).touch()
    assert paths.app_root() == tmp_path


def test_config_override_wins_over_convention(tmp_path: Path):
    assert paths.data_dir(tmp_path, override=str(tmp_path / "elsewhere")) == tmp_path / "elsewhere"


def test_resource_dir_is_not_the_data_dir(tmp_path: Path, monkeypatch):
    """``_MEIPASS`` 是每次运行重建的临时目录，写进去的数据会消失。"""
    monkeypatch.setattr(paths, "exe_dir", lambda: tmp_path)
    monkeypatch.setattr(paths, "_platform_app_dir", lambda: tmp_path / "conventional")
    assert paths.resource_dir() != paths.data_dir(paths.app_root())


def test_describe_covers_every_path_users_may_need():
    keys = set(paths.describe())
    assert {"app_root", "config", "data_dir", "logs_dir", "resource_dir"} <= keys
