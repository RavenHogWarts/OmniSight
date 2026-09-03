"""随仓库分发的文档里，相对链接必须指向**也在仓库里**的文件。

这条是被一次真实的坏链推出来的：`dev/` 与 `refer/` 刻意不进版本库（`.gitignore`
第一条），而 README 与 `docs/` 里有六七处 `](../dev/...)`。在检出的工作区里它们都能
打开——**本地看一切正常，GitHub 上全是 404**，而 README 是陌生人读到的第一份文件。

因此这里核对的不是"文件存在"，而是"**git 里有这个文件**"：前者在维护者的机器上永远
为真，正是它让这类坏链活了下来。
"""

from __future__ import annotations

import posixpath
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

#: Markdown 的行内链接。图片（``![]()``）一并抓：坏掉的图片同样是坏链。
LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")


def _tracked_files() -> set[str]:
    listed = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, check=True
    ).stdout.decode("utf-8")
    return {line.strip() for line in listed.splitlines() if line.strip()}


@pytest.fixture(scope="module")
def tracked() -> set[str]:
    if shutil.which("git") is None or not (ROOT / ".git").exists():
        pytest.skip("不在 git 检出里")
    return _tracked_files()


def test_every_relative_link_in_the_shipped_docs_points_at_a_tracked_file(tracked: set[str]):
    # 跟踪的 .md 就是"随仓库分发的文档"的全集——`dev/` 不在里面，正是因为它不进版本库。
    documents = sorted(name for name in tracked if name.endswith(".md"))
    assert documents, "一份随仓库分发的 Markdown 都没有？"
    broken: list[str] = []
    for name in documents:
        base = posixpath.dirname(name)
        for target in LINK.findall((ROOT / name).read_text(encoding="utf-8")):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            path = target.split("#")[0]
            if not path:
                continue
            # 用 posixpath 归一化而不是碰文件系统：``docs/../README.md`` 要变成
            # ``README.md`` 才能与 git 的路径比对，而"文件在不在"恰恰是不能问磁盘的。
            directory = path.endswith("/")
            relative = posixpath.normpath(posixpath.join(base, path))
            if directory:
                # 目录形式的链接：git 不跟踪目录，看有没有文件在它下面。
                if not any(item.startswith(f"{relative}/") for item in tracked):
                    broken.append(f"{name} → {target}")
            elif relative not in tracked:
                broken.append(f"{name} → {target}")
    assert not broken, "指向仓库里没有的东西（本地能打开，GitHub 上 404）：\n  " + "\n  ".join(
        broken
    )


def test_the_design_docs_are_deliberately_not_shipped(tracked: set[str]):
    """这条钉住上面那条的**前提**。哪天 `dev/` 进了版本库，链接就该加回去，而不是
    继续写成没有链接的纯文本。
    """
    assert not [name for name in tracked if name.startswith(("dev/", "refer/"))]
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "dev" in ignored and "refer" in ignored
