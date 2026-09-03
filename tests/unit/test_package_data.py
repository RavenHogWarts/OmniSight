"""``pip install .`` 出来的包必须带着整个前端（10 文档 §1）。

**这条测试的由来**：``package-data`` 原先写的是 ``presentation/static/js/*.js``，
而 setuptools 的 ``*`` 不跨目录分隔符——wheel 里因此只有 ``main.js`` 与 ``theme.js``，
``js/core/``、``css/components/`` 等八个子目录一个文件都没进去。装出来的仪表盘是
一片空白：首页仍然 200，但 ``app.css`` 的 @import 与 ``main.js`` 的 import 全部 404。

一直没人发现是因为实际分发走 PyInstaller（``OmniSight.spec`` 拷整个 static 目录），
``pip install`` 只在开发时用，而开发时源码就在旁边。

**不真的去构建 wheel**：那要跑一次构建后端（十几秒），而 setuptools 自 62.3 起对
``package_data`` 就是用 ``glob(..., recursive=True)`` 展开的，这里照它的规则展开一遍
即可。另有一条测试核对"展开出来的确实是一批真文件"，防止规则写错时空跑通过。
"""

from __future__ import annotations

import glob
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "src" / "omnisight"
#: 必须随包分发的资源目录。少一个文件就是少一块界面。
RESOURCE_DIRS = ("presentation/static", "presentation/templates")


def _patterns() -> list[str]:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return config["tool"]["setuptools"]["package-data"]["omnisight"]


def _covered() -> set[str]:
    """package-data 的通配展开成一组包内相对路径（POSIX 分隔符）。"""
    found: set[str] = set()
    for pattern in _patterns():
        for match in glob.glob(pattern, root_dir=PACKAGE, recursive=True):
            if (PACKAGE / match).is_file():
                found.add(Path(match).as_posix())
    return found


def _resources() -> set[str]:
    found: set[str] = set()
    for relative in RESOURCE_DIRS:
        for path in (PACKAGE / relative).rglob("*"):
            if path.is_file():
                found.add(path.relative_to(PACKAGE).as_posix())
    return found


def test_every_frontend_file_is_declared_as_package_data():
    missing = sorted(_resources() - _covered())
    assert not missing, (
        "这些文件不会进 wheel（`pip install .` 后仪表盘会空白）：\n  "
        + "\n  ".join(missing)
    )


def test_the_patterns_are_recursive():
    """探针：有人把 ``**`` 改回 ``*`` 时，上面那条会红，但这条给出原因。"""
    patterns = _patterns()
    assert any("**" in pattern for pattern in patterns), (
        f"package-data 里没有递归通配：{patterns}。setuptools 的 `*` 不跨目录分隔符，"
        "而前端有八层子目录"
    )


def test_the_expansion_actually_found_files():
    """探针：路径或读取写错时，上面两条会在空集合上通过。"""
    covered = _covered()
    resources = _resources()
    assert len(resources) >= 50, f"只找到 {len(resources)} 个前端文件，检查 RESOURCE_DIRS"
    assert len(covered) >= 50, f"通配只展开出 {len(covered)} 个文件，检查 package-data"
    assert "presentation/templates/dashboard.html" in covered
    assert "presentation/static/js/core/store.js" in covered
    assert "presentation/static/css/components/card.css" in covered
