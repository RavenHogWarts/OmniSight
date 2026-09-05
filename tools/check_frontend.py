"""前端静态检查（07 文档 §10、11 文档 §8.4）。

没有构建工具，就没有打包器替我们发现"导入了一个不存在的导出"。这个脚本补上那一层，
外加四条**架构约束的执行机制**——写在文档里不由工具强制的规则，三个月内必然失效：

与 ``tools/check_types.py`` 的分工：那一条查**类型**（字段名、null、接口契约），需要
Node 才能跑，缺了就跳过；这一条查**结构与禁令**，纯 Python、永远会跑。因此下面第 1
到第 4 条不迁到 tsc 上去——它们必须在任何机器上都拦得住。

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
#: 源码根。15 文档选了方案 A 之后源码不再是浏览器加载的那份文件——`frontend/src` 经 Vite
#: 编译进 `static/dist`。这个脚本查的是**源码**，因此指向 frontend/src；`static/dist`
#: 下的产物不查（那是编译结果，规则要在源头上拦）。
JS = ROOT / "frontend" / "src"
#: 样式源码。15 文档 §11.4 把它从 `static/css` 搬到这里并接进 Vite——`static/css` 下现在
#: 只剩 `shell.css`（产物缺失时的兜底，刻意不进构建图）。
STYLES = ROOT / "frontend" / "styles"
TEMPLATES = ROOT / "src" / "omnisight" / "presentation" / "templates"

#: 要扫的源码后缀。迁移期 .js 与 .ts/.tsx 并存（15 文档 §8 的分批原则），三者同规则。
SOURCE_SUFFIXES = ("*.js", "*.ts", "*.tsx")


def _sources(root: Path) -> list[Path]:
    """`root` 下所有前端源码，按路径排序。`.d.ts` 只有类型、没有运行时代码，一并收。"""
    found: list[Path] = []
    for pattern in SOURCE_SUFFIXES:
        found.extend(root.rglob(pattern))
    return sorted(found)

#: 每层允许 import 的目标。键是目录，值是允许的路径前缀（相对源码根）。
#:
#: 后缀写 `.ts`：15 文档方案 A 之后源码是 TS，而说明符带真实扩展名（见 fix_imports.py）。
LAYER_RULES: dict[str, tuple[str, ...]] = {
    # 只有 .d.ts，没有运行时代码。类型引用编译期就被擦掉，不产生 import 语句。
    "types": (),
    "core": ("core/",),
    # domain 的实质约束是"不取数、不读状态"：可以算、可以格式化，但不许碰
    # api/store/loader。React 化之后它连 DOM 都不碰了——原先 keyboard-layout.js 在这里
    # 建 DOM（07 文档 §6.4 与 §3 的分层规则互相矛盾过），那部分已搬进
    # components/KeyboardView.tsx。
    "domain": ("domain/", "core/store.ts"),
    # charts/ 只接收数据与容器，不知道 store 存在。允许 core/bus.ts：主题切换要重绘
    # canvas，而那是一次性通知而不是状态（06 文档 §11 第 2 点）。
    "charts": ("charts/", "domain/", "core/bus.ts"),
    "components": ("components/", "charts/", "domain/", "core/"),
    "views": ("views/", "components/", "charts/", "domain/", "core/"),
    # pages/ 是**页面装配层**（18 文档 批 1）：三个入口共用的外壳、设置页与关于页的正文。
    # 与 views/ 同一档权限，且**同样不许 import views/**——视图是仪表盘那一页的内部结构，
    # 设置页不该认识它们；反过来 views/ 也不许 import pages/（那会把两页绑在一起）。
    "pages": ("pages/", "components/", "charts/", "domain/", "core/"),
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
    r"^\s*export\s+(?:async\s+)?(?:function|const|let|var|class|interface|type)\s+(?P<name>\w+)",
    re.MULTILINE,
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
    """报错里的路径。`frontend/src` 与 `src/omnisight/...` 分居两棵树，各自相对仓库根。"""
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:  # pragma: no cover - 只会在有人把这脚本挪出仓库时发生
        return path.as_posix()


def _line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


#: `.js` 说明符要落到哪些真实文件上。TS 的约定是**写 `.js`、落 `.ts`**（因为浏览器里
#: 只有 `.js` 是合法路径），Vite 与 tsc 都走这条回退，所以这里也必须走。
_JS_FALLBACKS = (".ts", ".tsx", ".d.ts")


def _resolve(source: Path, target: str) -> Path:
    """相对路径解析，带 TS 的扩展名回退。

    三类都要认：`./core/store.js`（TS 风格，落 `store.ts`）、`./types/api.js`
    （JSDoc 的类型引用，落 `api.d.ts`）、`./core/store`（无后缀）。找不到时返回
    原始候选，让调用方报"文件不存在"。
    """
    base = source.parent
    resolved = (base / target).resolve()
    if resolved.is_file():
        return resolved
    if target.endswith(".js"):
        for suffix in _JS_FALLBACKS:
            candidate = (base / (target[:-3] + suffix)).resolve()
            if candidate.is_file():
                return candidate
    else:
        for suffix in (".ts", ".tsx", ".js", ".d.ts"):
            candidate = (base / (target + suffix)).resolve()
            if candidate.is_file():
                return candidate
    return resolved


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


#: 允许的裸模块名。**白名单而不是"一律禁止"**：15 文档选了方案 A 之后运行时确实有依赖，
#: 但"有依赖"和"随便加依赖"是两件事——每加一个包都要在这里写一行，于是依赖增长在
#: code review 里是可见的，而不是藏在某个文件的 import 里。
#:
#: 每一项都要能回答"它进了产物、因此进了许可清单吗"：三个都是 MIT，由
#: `tools/npm_licenses.py` 采集进 THIRD_PARTY_NOTICES.md。
ALLOWED_BARE_IMPORTS = frozenset({"react", "react-dom", "lucide-react"})


def _bare_allowed(target: str) -> bool:
    """裸模块名在白名单里吗。子路径（`react-dom/client`）按包名判定。"""
    package = "/".join(target.split("/")[:2]) if target.startswith("@") else target.split("/")[0]
    return package in ALLOWED_BARE_IMPORTS


def check_imports() -> list[Problem]:
    """每个 import 的目标文件存在，且确实导出了被引用的名字。"""
    problems: list[Problem] = []
    for path in _sources(JS):
        text = path.read_text(encoding="utf-8")
        for match in _IMPORT.finditer(text):
            target = match.group("path")
            if not target.startswith("."):
                if not _bare_allowed(target):
                    problems.append(Problem(_relative(path), _line_of(text, match.start()),
                                            f"裸模块名 {target!r} 不在 ALLOWED_BARE_IMPORTS 里："
                                            "新增运行时依赖要同时进许可清单"))
                continue
            resolved = _resolve(path, target)
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
            if target.startswith(".") and not _resolve(path, target).is_file():
                problems.append(Problem(_relative(path), _line_of(text, match.start()),
                                        f"动态导入的文件不存在：{target}"))
    return problems


def check_import_extensions() -> list[Problem]:
    """相对导入必须写**真实存在的**扩展名（15 文档 §3.6）。

    这不是风格洁癖：`tests/frontend/*.test.ts` 用
    `node --test --experimental-strip-types` 直接跑源码，而 Node 的 ESM 只认磁盘上的
    真路径——无后缀与 `.js` -> `.ts` 的回退它都不做。少一个后缀的症状是
    ERR_MODULE_NOT_FOUND，而那只在跑 node 测试时才出现（tsc 与 Vite 都能自己回退），
    也就是"只在装了 Node 的机器上才红"。这条把它提前到提交前。

    `tools/fix_imports.py` 能一把补齐。
    """
    problems: list[Problem] = []
    for path in _sources(JS):
        text = path.read_text(encoding="utf-8")
        for match in _IMPORT.finditer(text):
            target = match.group("path")
            if not target.startswith("."):
                continue
            if (path.parent / target).is_file():
                continue
            resolved = _resolve(path, target)
            hint = resolved.name if resolved.is_file() else "对应的真实文件名"
            problems.append(Problem(_relative(path), _line_of(text, match.start()),
                                    f"导入 {target!r} 缺少扩展名：写成 {hint}"
                                    "（跑 `python tools/fix_imports.py`）"))
    return problems


def check_layers() -> list[Problem]:
    """分层单向依赖。main.js 不受限（它就是装配点）。"""
    problems: list[Problem] = []
    for path in _sources(JS):
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
            resolved = _resolve(path, target)
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
    for path in _sources(JS):
        text = path.read_text(encoding="utf-8")
        for pattern, detail in FORBIDDEN_PATTERNS:
            for match in re.finditer(pattern, text):
                problems.append(Problem(_relative(path), _line_of(text, match.start()), detail))
    return problems


def check_category_copy() -> list[Problem]:
    """分类规则的单一真源不是"两份对齐"，而是**只有一份**（11 文档 §3.5）。"""
    problems: list[Problem] = []
    for path in [*_sources(JS), *sorted(STATIC.rglob("*.js"))]:
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
        *check_import_extensions(),
        *check_layers(),
        *check_patterns(),
        *check_category_copy(),
        *check_templates(),
    ]


def main() -> int:
    problems = check_all()
    if not problems:
        js_count = len(_sources(JS))
        css_count = len(list(STYLES.rglob("*.css")))
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
