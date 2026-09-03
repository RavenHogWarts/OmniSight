"""从 lucide-static 生成图标精灵表（14 文档 §3.5、15 文档 §6 的 B1）。

**图标真源从"手抄 path"换成一张名字映射表。** 在这之前，`dashboard.html` 里那 15 个
`<symbol>` 的路径数据是手工照着 lucide 抄进来的——规格（24×24 视框、`currentColor`、
1.5 笔重、圆头端点）本来就是 lucide 的约定，所以那份手抄稿的每一处差异都只是抄写误差，
不是设计意图。现在改成从 `node_modules/lucide-static/icons/*.svg` 读取几何，
`ICON_SOURCES` 是唯一需要人维护的东西。

**产物里仍然没有任何 npm 包。** lucide-static 是 devDependency，它的作用只是提供
SVG 源文件；生成结果是一份内联的 `<symbol>` 精灵表，运行时零请求、零依赖，因此
07 文档 §2 的三条性质（无构建产物进运行路径、PyInstaller 照旧拷目录、克隆即运行）
全部保留。**没装 Node 的机器照样能跑起来**——生成结果是提交进版本库的。

**为什么不用 lucide 自带的 `sprite.svg`**：那一份含全部 2057 个图标（约 1.5 MB），
而且每个 symbol 都带着 `stroke-width="2"` 等表现属性。我们要的是 15 个，且笔重必须
留给 `base.css` 的 `.icon` 规则控制（14 文档 §3.5 定的是 1.5）。

**为什么剥掉表现属性**：`.icon` 用 `fill: none; stroke: currentColor; stroke-width: 1.5`
统一控制所有图标。lucide 的每个文件都自带 `stroke-width="2"`，属性会盖过外部样式表，
于是笔重变粗、深浅色切换也不再跟随 `currentColor`。剥掉之后几何是唯一被搬过来的东西。

许可：lucide 是 ISC。生成文件里保留版权与许可声明，那份文件随产物分发，因此 ISC 的
"在所有副本中保留声明"就此满足。清单侧另有一条记录（`tools/licenses.py` 的
`EMBEDDED_ASSETS`）。

用法：

    python tools/icons.py            # 重新生成
    python tools/icons.py --check    # 只比对，有漂移就非零退出（tests 用它）
"""

from __future__ import annotations

import re
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LUCIDE = ROOT / "node_modules" / "lucide-static"
ICONS = LUCIDE / "icons"
SPRITE = ROOT / "src" / "omnisight" / "presentation" / "templates" / "_icon_sprite.html"

#: 精灵表 id（不含 `i-` 前缀）→ lucide 的图标文件名。**这张表是唯一的人工维护点。**
#:
#: 键的集合必须与 `static/js/components/icon.js` 的 `ICON_NAMES` 一致——
#: `tests/unit/test_icon_sprite.py` 断言这一点，不再靠 icon.js 里那句"改这里之前先改模板"。
#:
#: 几处选名的理由：`theme` 用 `contrast`（圆 + 半填充）而不是 `sun-moon`，因为主题按钮
#: 是三态循环（跟随系统 / 浅 / 深），日月图标会暗示只有两态；`insights` 用 `chart-column`
#: 而不是 `bar-chart-3`，后者是旧名，lucide 已改名（旧名仍在包里，但会随大版本消失）。
ICON_SOURCES: dict[str, str] = {
    "gear": "settings",
    "theme": "contrast",
    "left": "chevron-left",
    "right": "chevron-right",
    "info": "info",
    "keyboard": "keyboard",
    "apps": "layout-grid",
    "insights": "chart-column",
    "overview": "house",
    "download": "download",
    "pause": "pause",
    "more": "ellipsis-vertical",
    "search": "search",
    "close": "x",
    "warning": "triangle-alert",
}

#: lucide 的版权与许可声明，**逐字照抄，不重排**。
#:
#: 两个地方要用它：生成的精灵表里带一份（ISC 要求"副本保留声明"，而那份文件随产物
#: 分发），`tools/licenses.py` 的 `EMBEDDED_ASSETS` 也引它一份进清单四件套。所以它是
#: 常量而不是从 `node_modules/lucide-static/LICENSE` 读——**清单在发布流水线上生成，
#: 那里只跑 pip install，没有 node_modules**。
ISC_NOTICE = """Icons derived from lucide (https://lucide.dev) — ISC License.

Copyright (c) for portions of Lucide are held by Cole Bemis 2013-2022 as part of
Feather (MIT). All other copyright (c) for Lucide are held by Lucide Contributors 2022.

Permission to use, copy, modify, and/or distribute this software for any purpose
with or without fee is hereby granted, provided that the above copyright notice
and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH
REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND
FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT,
INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS
OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER
TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR PERFORMANCE OF
THIS SOFTWARE.
"""

#: 允许出现在 symbol 里的几何元素。lucide 用的不只有 `<path>`——`layout-grid` 是四个
#: `<rect>`，`ellipsis-vertical` 是三个 `<circle>`。白名单而不是"抄下所有子元素"：
#: 遇到没见过的元素（`<style>`、`<image>`）宁可失败，也别静默搬进产物。
GEOMETRY = ("path", "circle", "rect", "line", "polyline", "polygon", "ellipse")

#: 必须剥掉的表现属性，理由见模块文档。
STRIP_ATTRS = ("fill", "stroke", "stroke-width", "stroke-linecap", "stroke-linejoin", "class")

_ELEMENT = re.compile(r"<(?P<tag>[a-z]+)\b(?P<attrs>[^>]*?)/?>")
_ATTR = re.compile(r"(?P<name>[a-zA-Z-]+)\s*=\s*\"(?P<value>[^\"]*)\"")


class MissingSource(RuntimeError):
    """lucide-static 不在（没跑过 `pnpm install`），或者映射表点了一个不存在的图标。"""


def geometry_of(lucide_name: str) -> list[str]:
    """一个 lucide 图标里的几何元素，表现属性已剥掉。

    只做正则，不引 XML 解析器：lucide 的文件是机器生成的，形态单一（一层 `<svg>`
    包着若干自闭合的几何元素，无嵌套、无命名空间前缀）。遇到白名单外的元素直接抛，
    因此"形态变了"不会静默通过。
    """
    path = ICONS / f"{lucide_name}.svg"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise MissingSource(f"读不到 {path}（跑 `pnpm install` 装 lucide-static）") from error

    elements: list[str] = []
    for match in _ELEMENT.finditer(text):
        tag = match.group("tag")
        if tag == "svg":
            continue
        if tag not in GEOMETRY:
            raise MissingSource(f"{lucide_name}.svg 里有未预期的元素 <{tag}>")
        attrs = [
            (name, value)
            for name, value in _ATTR.findall(match.group("attrs"))
            if name not in STRIP_ATTRS
        ]
        rendered = " ".join(f'{name}="{value}"' for name, value in attrs)
        elements.append(f"<{tag} {rendered}/>" if rendered else f"<{tag}/>")
    if not elements:
        raise MissingSource(f"{lucide_name}.svg 里没有任何几何元素")
    return elements


def lucide_version() -> str:
    """装着的 lucide-static 版本。写进生成文件的头部，便于对照上游改动。"""
    import json

    try:
        payload = json.loads((LUCIDE / "package.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise MissingSource("读不到 lucide-static/package.json") from error
    return str(payload.get("version", "未知"))


def render() -> str:
    """整份精灵表。

    输出是 Jinja 片段而不是 `.svg` 文件：`<use href="#i-x">` 要求 symbol 与引用同文档，
    跨文件引用在部分浏览器里不生效，且会多一次请求（07 文档 §2 的"零出站网络"）。
    """
    version = lucide_version()
    symbols = []
    for key, source in ICON_SOURCES.items():
        body = "".join(geometry_of(source))
        symbols.append(f'  <symbol id="i-{key}" viewBox="0 0 24 24">{body}</symbol>')
    joined = "\n".join(symbols)
    # 取用清单要能一眼看完，所以按行宽折一下——它是给读文件的人看的，不是给机器的。
    names = textwrap.fill("、".join(ICON_SOURCES.values()), width=88, subsequent_indent="  ")
    # 声明缩进两格与周围标记对齐；正文一个字都不改（许可文本不允许被"排版"）。
    indented = "\n".join(f"  {line}".rstrip() for line in ISC_NOTICE.strip("\n").split("\n"))
    return f"""{{#
  **本文件由 tools/icons.py 从 lucide-static 生成，请勿手改。**
  改图标：改 tools/icons.py 的 ICON_SOURCES 与 static/js/components/icon.js 的
  ICON_NAMES，然后重新跑 `python tools/icons.py`。
  tests/unit/test_icon_sprite.py 会在两者不一致或此文件漂移时报错。

  为什么内联而不是图标字体或 CDN：无构建、无出站网络、CSP 只允许 'self'
  （07 文档 §2、08 文档 §3）。内联 <symbol> 零请求、笔重统一（由 base.css 的 .icon
  控制，因此这里的元素刻意不带 fill/stroke/stroke-width）、颜色跟随 currentColor，
  深浅色自动跟随。

  上游：lucide-static v{version}（ISC）。取用的图标：{names}。
#}}
<!--
{indented}
-->
<svg class="icon-sprite" aria-hidden="true" hidden>
{joined}
</svg>
"""


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    try:
        rendered = render()
    except MissingSource as error:
        print(f"生成失败：{error}", file=sys.stderr)
        return 1
    current = SPRITE.read_text(encoding="utf-8") if SPRITE.is_file() else None
    if "--check" in argv:
        if current == rendered:
            print(f"图标精灵表与 lucide-static 一致（{len(ICON_SOURCES)} 个图标）")
            return 0
        print(
            f"{SPRITE.relative_to(ROOT)} 与 lucide-static 不一致，跑 `python tools/icons.py`",
            file=sys.stderr,
        )
        return 1
    if current == rendered:
        print(f"图标精灵表无变化（{len(ICON_SOURCES)} 个图标）")
        return 0
    SPRITE.write_text(rendered, encoding="utf-8")
    print(
        f"已生成 {SPRITE.relative_to(ROOT)}"
        f"（{len(ICON_SOURCES)} 个图标，lucide v{lucide_version()}）"
    )
    return 0


if __name__ == "__main__":
    # 见 tools/_console.py：runner 上 stdout 是管道，按 locale 挑到 cp1252，
    # 一行中文输出就能让进程死在 UnicodeEncodeError 上。
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _console import use_utf8_output

    use_utf8_output()
    sys.exit(main())
