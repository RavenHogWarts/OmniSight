"""平台泄漏静态检查（10 文档 §11）。

01 文档的非功能需求里有一条"平台无关性"：``core/`` ``capture/`` ``storage/``
``services/`` ``presentation/`` 五层不得判断平台。本脚本是那条要求的**执行机制**
——写在文档里的架构约束，不由工具强制就会在三个月内失效。

它现在检出的问题应当为零，这正是最容易通过的时候。等到真正加第二个平台时才引入
这个检查，会一次性冒出几十处违规，而每一处都要重新设计。

允许的例外只有两处，都在 ``ALLOWLIST`` 里显式列出并写明理由。
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "omnisight"

#: 受检目录：核心层。``adapters/`` 与 ``tray/`` 不在其中——前者就是平台实现，
#: 后者是薄薄一层 pystray 封装。
GUARDED_DIRS = ("core", "capture", "storage", "services", "presentation")

#: 显式豁免。每一条都必须写清"为什么搬进适配器不划算"。
ALLOWLIST: dict[str, str] = {
    # 路径必须在适配器装配之前就可用（日志、配置、锁文件都依赖它），
    # 而把三行路径拼接搬进适配器不划算。见 02 文档 §6 与该文件的模块注释。
    "core/paths.py": "平台数据目录解析，02 文档 §6 的显式豁免",
}

FORBIDDEN_MODULE_PREFIXES = (
    "win32",
    "winreg",
    "pywintypes",
    "pythoncom",
    "Quartz",
    "AppKit",
    "Cocoa",
    "Foundation",
    "objc",
    "Xlib",
    "xcffib",
    "evdev",
    "pynput",
    "msvcrt",
)

PLATFORM_ATTRS = frozenset({"platform", "name"})
PLATFORM_MODULES = frozenset({"sys", "os"})


@dataclass(frozen=True, slots=True)
class Violation:
    path: str
    line: int
    detail: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}  {self.detail}"


class _Visitor(ast.NodeVisitor):
    def __init__(self, relative: str) -> None:
        self.relative = relative
        self.found: list[Violation] = []

    def _flag(self, node: ast.AST, detail: str) -> None:
        self.found.append(Violation(self.relative, getattr(node, "lineno", 0), detail))

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if _is_forbidden_module(alias.name):
                self._flag(node, f"禁止在核心层导入平台模块 {alias.name!r}")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module and _is_forbidden_module(node.module):
            self._flag(node, f"禁止在核心层导入平台模块 {node.module!r}")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        # ctypes.windll.user32 / sys.platform / os.name
        if node.attr == "windll":
            self._flag(node, "禁止在核心层使用 ctypes.windll")
        if (
            isinstance(node.value, ast.Name)
            and node.value.id in PLATFORM_MODULES
            and node.attr in PLATFORM_ATTRS
        ):
            self._flag(node, f"禁止在核心层读取 {node.value.id}.{node.attr}——请查询 Capabilities")
        self.generic_visit(node)


def _is_forbidden_module(name: str) -> bool:
    head = name.split(".", 1)[0]
    return any(head == prefix or head.startswith(prefix) for prefix in FORBIDDEN_MODULE_PREFIXES)


def check_platform_leaks(package_root: Path | None = None) -> list[Violation]:
    """扫描核心层，返回全部违规。空列表 = 通过。"""
    package_root = package_root or PACKAGE
    violations: list[Violation] = []
    for directory in GUARDED_DIRS:
        base = package_root / directory
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            relative = path.relative_to(package_root).as_posix()
            if relative in ALLOWLIST:
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except SyntaxError as exc:
                violations.append(Violation(relative, exc.lineno or 0, f"无法解析：{exc.msg}"))
                continue
            visitor = _Visitor(relative)
            visitor.visit(tree)
            violations.extend(visitor.found)
    return violations


def main() -> int:
    violations = check_platform_leaks()
    if not violations:
        print(f"平台泄漏检查通过（受检目录：{', '.join(GUARDED_DIRS)}）")
        for path, reason in ALLOWLIST.items():
            print(f"  豁免 {path} —— {reason}")
        return 0
    print(f"发现 {len(violations)} 处平台泄漏：", file=sys.stderr)
    for violation in violations:
        print(f"  {violation}", file=sys.stderr)
    print(
        "\n平台差异应收敛在 adapters/ 内；核心层请改为查询 Capabilities（见 13 文档 §5）。",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    # 见 tools/_console.py：runner 上 stdout 是管道，按 locale 挑到 cp1252，
    # 一行中文输出就能让进程死在 UnicodeEncodeError 上。
    from _console import use_utf8_output

    use_utf8_output()
    sys.exit(main())
