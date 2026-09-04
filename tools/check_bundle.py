"""前端产物的门禁（15 文档 §3.1、§3.2）。

**为什么需要它**：产物（`static/dist`）是提交进版本库的——`pip install` 路径上没有
Node，wheel 必须自带打包好的前端。代价是版本库里存在一份"可以过期"的东西：改了
`frontend/src` 却忘了 `pnpm build`，页面加载的仍然是旧代码，而**测试全绿、页面正常**。
那是最难发现的一类不一致。

三件事，各自独立：

1. `--exists`：产物在不在（纯 Python，任何机器上都跑）。打包与发布前的硬门禁——
   缺了它 wheel 与 EXE 装出来只有"产物缺失"那张卡。
2. `--stale`：产物比源码旧吗（纯 Python，比 mtime）。这一条**只警告不失败**：
   git 检出的 mtime 是检出时间，顺序没有意义，在 CI 上必然误报。
3. `--check`：重新构建一次，比对产物是否逐字节相同（需要 Node）。这是唯一能真正
   回答"产物与源码一致吗"的检查，因此它是 CI 的门禁；本地没装 Node 时跳过。

`--check` 用临时目录构建再比对，不动工作区里的产物：否则一次检查就会把 `git status`
弄脏，而"检查"不该有副作用。
"""

from __future__ import annotations

import filecmp
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "frontend"
DIST = ROOT / "src" / "omnisight" / "presentation" / "static" / "dist"
MANIFEST = DIST / "manifest.json"
#: pnpm 装出来的 Vite 入口。走 `node <这个文件>` 而不是 .bin 里的包装器：那边在
#: Windows 上是 vite / vite.CMD / vite.ps1 三件套，subprocess 得挑对哪一件。
LOCAL_VITE = ROOT / "node_modules" / "vite" / "bin" / "vite.js"


def exists() -> list[str]:
    """产物齐全吗。返回问题列表，空列表表示没问题。"""
    problems: list[str] = []
    if not MANIFEST.is_file():
        problems.append(f"缺少产物清单 {MANIFEST.relative_to(ROOT)}——跑 `pnpm build`")
        return problems
    try:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except ValueError as error:
        problems.append(f"产物清单不是合法 JSON：{error}")
        return problems
    entries = [record for record in manifest.values() if isinstance(record, dict)]
    if not any(record.get("isEntry") for record in entries):
        problems.append("产物清单里没有入口（isEntry）——构建配置被改坏了？")
    for record in entries:
        name = record.get("file")
        if name and not (DIST / name).is_file():
            problems.append(f"清单里有 {name}，但文件不在")
    return problems


def newest(root: Path, patterns: tuple[str, ...]) -> float:
    stamps = [path.stat().st_mtime for pattern in patterns for path in root.rglob(pattern)]
    return max(stamps, default=0.0)


def stale() -> str | None:
    """产物看起来比源码旧吗。**只警告**——理由见模块文档。"""
    if not MANIFEST.is_file():
        return None
    source_at = max(
        newest(SOURCE, ("*.js", "*.ts", "*.tsx", "*.css")),
        (ROOT / "vite.config.ts").stat().st_mtime,
    )
    if source_at > newest(DIST, ("*.js", "*.css", "*.json")):
        return "产物比 frontend/ 里的源码旧——大概该跑一次 `pnpm build`"
    return None


def resolve_command() -> list[str] | None:
    node = shutil.which("node")
    if node and LOCAL_VITE.is_file():
        return [node, str(LOCAL_VITE)]
    on_path = shutil.which("vite")
    return [on_path] if on_path else None


def rebuild_into(out_dir: Path) -> tuple[int, str]:
    """把前端重新构建到 `out_dir`。返回 ``(退出码, 输出)``；``-1`` 表示没有 Vite。"""
    command = resolve_command()
    if command is None:
        return -1, "未找到 vite（装了 Node 的话跑 `pnpm install`）"
    result = subprocess.run(
        [*command, "build", "--outDir", str(out_dir), "--emptyOutDir"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
    )
    return result.returncode, (result.stdout or "") + (result.stderr or "")


def _differences(left: Path, right: Path) -> list[str]:
    """两棵目录树的差异。只报"哪些文件不一样"，不做逐行 diff。"""
    left_files = {p.relative_to(left).as_posix() for p in left.rglob("*") if p.is_file()}
    right_files = {p.relative_to(right).as_posix() for p in right.rglob("*") if p.is_file()}
    problems = [f"提交的产物里多了 {name}" for name in sorted(left_files - right_files)]
    problems += [f"提交的产物里少了 {name}" for name in sorted(right_files - left_files)]
    # **没有豁免**：产物里不产 sourcemap（vite.config.ts 里写了理由），因此每个文件
    # 都逐字节可比。留一个 .map 例外会让「产物与源码一致」变成「除了那部分之外一致」。
    for name in sorted(left_files & right_files):
        if not filecmp.cmp(left / name, right / name, shallow=False):
            problems.append(f"{name} 与重新构建的结果不一致")
    return problems


def check() -> tuple[int, list[str]]:
    """重新构建并比对。返回 ``(退出码, 问题列表)``；``-1`` 表示跳过（没有 Node）。"""
    with tempfile.TemporaryDirectory(prefix="omnisight-bundle-") as temporary:
        out = Path(temporary) / "dist"
        code, output = rebuild_into(out)
        if code == -1:
            return -1, [output]
        if code != 0:
            return 1, ["重新构建失败：", output.rstrip()]
        return 0, _differences(DIST, out)


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    wants = {flag for flag in argv if flag.startswith("--")} or {"--exists", "--stale"}

    if "--exists" in wants:
        problems = exists()
        if problems:
            print("前端产物不完整：", file=sys.stderr)
            for problem in problems:
                print(f"  {problem}", file=sys.stderr)
            return 1
        print(f"前端产物齐全（{MANIFEST.relative_to(ROOT)}）")

    if "--stale" in wants and (warning := stale()):
        print(f"提醒：{warning}")

    if "--check" in wants:
        code, problems = check()
        if code == -1:
            print(problems[0])
            if "--require" in wants:
                return 1
            return 0
        if code != 0 or problems:
            print("产物与源码不一致：", file=sys.stderr)
            for problem in problems:
                print(f"  {problem}", file=sys.stderr)
            print("跑 `pnpm build` 并提交产物。", file=sys.stderr)
            return 1
        print("前端产物与源码一致（重新构建后逐字节相同）")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _console import use_utf8_output

    use_utf8_output()
    sys.exit(main())
