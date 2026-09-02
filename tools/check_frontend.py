"""前端静态检查（07 文档 §10、11 文档 §8.4）。

没有构建工具，就没有打包器替我们发现"导入了一个不存在的导出"。这个脚本补上那一层，
外加四条**架构约束的执行机制**——写在文档里不由工具强制的规则，三个月内必然失效：

1. **分层单向依赖**。`core/` 不认识上层；`domain/` 不 fetch、不读 store；
   `charts/` 不知道 store 存在；`components/` 不 import `views/`。
2. **前端不判断平台**。`navigator.platform` / `navigator.userAgent` / 与 `platform.id`
   的字符串比较一律禁止——否则每加一个平台都要改前端，而这正是端口抽象要避免的。
3. **没有第二份分类规则**。`static/` 下出现进程名映射，就意味着 07 文档 §10 删掉的
   那份副本回来了。
4. **不用 innerHTML**。应用名与窗口标题来自操作系统，任何进程都能把自己的窗口命名成
   一段 HTML。`h()` 只走 textContent，这条检查盯住绕过它的写法。

模板侧另有两条：无内联脚本、无内联事件属性（CSP 是 `script-src 'self'`，二者都会被
浏览器直接拒掉，但报错发生在运行时而不是提交时）。
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "omnisight" / "presentation" / "static"
JS = STATIC / "js"
TEMPLATES = ROOT / "src" / "omnisight" / "presentation" / "templates"

#: 每层允许 import 的目标。键是目录，值是允许的路径前缀（相对 js/）。
LAYER_RULES: dict[str, tuple[str, ...]] = {
    "core": ("core/",),
    # domain 的实质约束是"不取数、不读状态"。07 文档写的是"无 DOM"，但同一份文档的
    # §6.4 把键盘渲染器放在 domain/keyboard-layout.js 并直接构造 DOM——两句话冲突。
    # 这里执行实质的那一半：domain 可以用 core/dom.js 建节点，但不许碰 api/store/loader。
    "domain": ("domain/", "core/dom.js"),
    "charts": ("charts/", "domain/", "core/dom.js", "core/bus.js"),
    "components": ("components/", "charts/", "domain/", "core/"),
    "views": ("views/", "components/", "charts/", "domain/", "core/"),
}

FORBIDDEN_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bnavigator\s*\.\s*platform\b", "前端不许读 navigator.platform，请读 capabilities 的布尔值"),
    (r"\bnavigator\s*\.\s*userAgent", "前端不许读 navigator.userAgent"),
    (r"\bnavigator\s*\.\s*userAgentData", "前端不许读 navigator.userAgentData"),
    (r"platform\s*\.\s*id\s*[=!]==?", "前端不许比较 platform.id，请读 capabilities 的布尔值"),
    (r"\.innerHTML\s*=", "禁止 innerHTML 赋值：窗口标题与应用名是不可信输入，请用 h()/textContent"),
    (r"\.outerHTML\s*=", "禁止 outerHTML 赋值，理由同 innerHTML"),
    (r"insertAdjacentHTML", "禁止 insertAdjacentHTML，理由同 innerHTML"),
    (r"document\s*\.\s*write", "禁止 document.write"),
    (r"\beval\s*\(", "禁止 eval"),
)

#: 分类规则副本的探针。取自 services/categories.py 里最有代表性的几个进程名。
CATEGORY_PROBES = ("pycharm64", "steamwebhelper", "startmenuexperiencehost", "explorer.exe")

_IMPORT = re.compile(
    r"^\s*import\s+(?:(?P<names>\{[^}]*\})|(?P<star>\*\s+as\s+\w+)|(?P<default>\w+))?"
    r"\s*(?:from\s*)?['\"](?P<path>[^'\"]+)['\"]",
    re.MULTILINE,
)
_DYNAMIC_IMPORT = re.compile(r"import\(\s*['\"](?P<path>[^'\"]+)['\"]\s*\)")
_EXPORT_NAMED = re.compile(
    r"^\s*export\s+(?:async\s+)?(?:function|const|let|var|class)\s+(?P<name>\w+)", re.MULTILINE
)
_EXPORT_LIST = re.compile(r"^\s*export\s*\{(?P<names>[^}]*)\}", re.MULTILINE)


@dataclass(frozen=True, slots=True)
class Problem:
    path: str
    line: int
    detail: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}  {self.detail}"


def _relative(path: Path) -> str:
    return path.relative_to(STATIC.parent).as_posix()


def _line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def exports_of(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    names = {match.group("name") for match in _EXPORT_NAMED.finditer(text)}
    for match in _EXPORT_LIST.finditer(text):
        for part in match.group("names").split(","):
            piece = part.strip()
            if not piece:
                continue
            # `export { set as setTheme }` 导出的是 as 后面那个名字。
            names.add(piece.split(" as ")[-1].strip())
    return names


def check_imports() -> list[Problem]:
    """每个 import 的目标文件存在，且确实导出了被引用的名字。"""
    problems: list[Problem] = []
    for path in sorted(JS.rglob("*.js")):
        text = path.read_text(encoding="utf-8")
        for match in _IMPORT.finditer(text):
            target = match.group("path")
            if not target.startswith("."):
                problems.append(Problem(_relative(path), _line_of(text, match.start()),
                                        f"禁止裸模块名 {target!r}：本项目零依赖、零构建"))
                continue
            resolved = (path.parent / target).resolve()
            if not resolved.is_file():
                problems.append(Problem(_relative(path), _line_of(text, match.start()),
                                        f"导入的文件不存在：{target}"))
                continue
            names = match.group("names")
            if not names:
                continue
            available = exports_of(resolved)
            for piece in names.strip("{}").split(","):
                item = piece.strip()
                if not item:
                    continue
                wanted = item.split(" as ")[0].strip()
                if wanted and wanted not in available:
                    problems.append(Problem(_relative(path), _line_of(text, match.start()),
                                            f"{resolved.name} 没有导出 {wanted!r}"))
        for match in _DYNAMIC_IMPORT.finditer(text):
            target = match.group("path")
            if target.startswith(".") and not (path.parent / target).resolve().is_file():
                problems.append(Problem(_relative(path), _line_of(text, match.start()),
                                        f"动态导入的文件不存在：{target}"))
    return problems


def check_layers() -> list[Problem]:
    """分层单向依赖。main.js 不受限（它就是装配点）。"""
    problems: list[Problem] = []
    for path in sorted(JS.rglob("*.js")):
        relative = path.relative_to(JS).as_posix()
        layer = relative.split("/")[0]
        allowed = LAYER_RULES.get(layer)
        if allowed is None:
            continue
        text = path.read_text(encoding="utf-8")
        for match in _IMPORT.finditer(text):
            target = match.group("path")
            if not target.startswith("."):
                continue
            resolved = (path.parent / target).resolve()
            try:
                target_relative = resolved.relative_to(JS).as_posix()
            except ValueError:
                problems.append(Problem(_relative(path), _line_of(text, match.start()),
                                        f"导入越出 js/ 目录：{target}"))
                continue
            if not any(target_relative.startswith(prefix) for prefix in allowed):
                problems.append(Problem(
                    _relative(path), _line_of(text, match.start()),
                    f"{layer}/ 不允许依赖 {target_relative}（允许：{'、'.join(allowed)}）",
                ))
    return problems


def check_patterns() -> list[Problem]:
    problems: list[Problem] = []
    for path in sorted(JS.rglob("*.js")):
        text = path.read_text(encoding="utf-8")
        for pattern, detail in FORBIDDEN_PATTERNS:
            for match in re.finditer(pattern, text):
                problems.append(Problem(_relative(path), _line_of(text, match.start()), detail))
    return problems


def check_category_copy() -> list[Problem]:
    """分类规则的单一真源不是"两份对齐"，而是**只有一份**（11 文档 §3.5）。"""
    problems: list[Problem] = []
    for path in sorted(STATIC.rglob("*.js")):
        lowered = path.read_text(encoding="utf-8", errors="ignore").casefold()
        hits = [probe for probe in CATEGORY_PROBES if probe in lowered]
        if hits:
            names = "、".join(hits)
            problems.append(Problem(_relative(path), 1,
                                    f"疑似分类规则副本（命中 {names}）：分类只在后端算一次"))
    return problems


def check_templates() -> list[Problem]:
    """CSP 是 script-src 'self'：内联脚本与内联事件属性都会被浏览器拒掉。"""
    problems: list[Problem] = []
    inline_handler = re.compile(r"\son[a-z]+\s*=\s*['\"]")
    # Jinja 注释块里会引用被禁止的写法（说明为什么不用它），扫描前先剔掉——
    # 否则这个检查会因为自己的说明文字而失败。
    jinja_comment = re.compile(r"\{#.*?#\}", re.DOTALL)
    for path in sorted(TEMPLATES.rglob("*.html")):
        text = jinja_comment.sub("", path.read_text(encoding="utf-8"))
        for match in inline_handler.finditer(text):
            problems.append(Problem(_relative(path), _line_of(text, match.start()),
                                    "禁止内联事件属性，请用 data-action + 事件委托"))
        for match in re.finditer(r"<script(?![^>]*\bsrc=)[^>]*>", text):
            problems.append(Problem(_relative(path), _line_of(text, match.start()),
                                    "禁止内联脚本（CSP script-src 'self' 会拒掉它）"))
        for match in re.finditer(r"<style[^>]*>", text):
            problems.append(Problem(_relative(path), _line_of(text, match.start()),
                                    "禁止内联样式表（CSP style-src 'self'）"))
    return problems


def check_all() -> list[Problem]:
    return [
        *check_imports(),
        *check_layers(),
        *check_patterns(),
        *check_category_copy(),
        *check_templates(),
    ]


def main() -> int:
    problems = check_all()
    if not problems:
        js_count = len(list(JS.rglob("*.js")))
        css_count = len(list((STATIC / "css").rglob("*.css")))
        print(f"前端静态检查通过（{js_count} 个 JS 模块、{css_count} 个样式文件）")
        return 0
    print(f"发现 {len(problems)} 处问题：", file=sys.stderr)
    for problem in problems:
        print(f"  {problem}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    # 见 tools/_console.py：runner 上 stdout 是管道，按 locale 挑到 cp1252，
    # 一行中文输出就能让进程死在 UnicodeEncodeError 上。
    from _console import use_utf8_output

    use_utf8_output()
    sys.exit(main())
