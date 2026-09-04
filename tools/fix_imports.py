"""给 frontend/src 里的相对导入补上**真实存在的**扩展名（15 文档 §3.6）。

三个消费者对说明符的要求不同，这一种是唯一同时满足三者的写法：

* **Vite**：都能解析，不挑。
* **tsc**：`./x.ts` 需要 `allowImportingTsExtensions`（`noEmit` 下允许），已在
  tsconfig.json 里开。
* **Node**（`node --test --experimental-strip-types`）：ESM 只认磁盘上真实存在的
  路径，无后缀与 `.js`→`.ts` 的回退它都不做。

第三条决定了写法：`tests/frontend/*.test.ts` 直接跑源码，因此源码里的每个说明符都
必须是真路径。**这条路值得保住**——它让"零依赖也能测纯函数"在引入构建工具之后仍然
成立（15 文档 §3.6 曾判定这条路会关闭，Node 22 的类型剥离之后不成立了）。

`tools/check_frontend.py` 有一条对应的检查，所以漂移会在提交前被发现，而不是等到
某次 `pnpm test` 报 ERR_MODULE_NOT_FOUND。

用法：``python tools/fix_imports.py``（幂等，改了多少个文件会打出来）
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "frontend" / "src"

#: 引号里以 `.` 开头的相对说明符。静态导入/导出、动态 import()、JSDoc 的类型引用同形。
SPECIFIER = re.compile(r"(?P<quote>['\"])(?P<path>\.[^'\"]*)(?P=quote)")

#: 候选后缀，按优先级。`.d.ts` 在最后：只有类型声明才落到它上面。
CANDIDATES = (".ts", ".tsx", ".js", ".jsx", ".d.ts")


def resolve(source: Path, target: str) -> str | None:
    """`target` 应该写成什么。已经正确时返回 None。"""
    base = source.parent
    stem = target
    for suffix in (".ts", ".tsx", ".js", ".jsx"):
        if target.endswith(suffix):
            stem = target[: -len(suffix)]
            break
    if (base / target).is_file() and target != stem:
        return None  # 已经带着一个真实存在的后缀
    for suffix in CANDIDATES:
        candidate = base / (stem + suffix)
        if candidate.is_file():
            return stem + suffix
    # 目录形式的 `./components`：落到它的 index。
    for suffix in CANDIDATES:
        candidate = base / stem / f"index{suffix}"
        if candidate.is_file():
            return f"{stem}/index{suffix}"
    return None


def fix(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")

    def replace(match: re.Match[str]) -> str:
        target = match.group("path")
        fixed = resolve(path, target)
        if fixed is None or fixed == target:
            return match.group(0)
        quote = match.group("quote")
        return f"{quote}{fixed}{quote}"

    replaced = SPECIFIER.sub(replace, text)
    if replaced == text:
        return False
    path.write_text(replaced, encoding="utf-8")
    return True


def main() -> int:
    changed = [
        path.relative_to(ROOT).as_posix()
        for path in sorted(SOURCE.rglob("*"))
        if path.suffix in {".ts", ".tsx", ".js", ".jsx"} and fix(path)
    ]
    if not changed:
        print("所有相对导入都已带上真实扩展名")
        return 0
    print(f"补齐了 {len(changed)} 个文件的导入扩展名：")
    for name in changed:
        print(f"  {name}")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _console import use_utf8_output

    use_utf8_output()
    sys.exit(main())
