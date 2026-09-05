"""前端静态检查作为测试跑（07 文档 §10、11 文档 §8.4）。

`tools/check_frontend.py` 是实现，这里是**执行机制**：CI 跑 pytest，于是"前端不许
判断平台""不许用 innerHTML""分层单向依赖"这三条架构约束每次提交都被验证一次。

单独列出每一类检查而不是只调一次 `check_all()`：失败时能一眼看出违反了哪条规则，
而不是"前端检查失败，共 7 处"。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import check_frontend  # noqa: E402

STATIC = check_frontend.STATIC
JS = check_frontend.JS
STYLES = check_frontend.STYLES


def _format(problems) -> str:
    return "\n".join(f"  {problem}" for problem in problems)


def test_every_import_resolves_to_a_real_export():
    """没有打包器，就没有人替我们发现"导入了一个不存在的导出"。"""
    problems = check_frontend.check_imports()
    assert not problems, "存在无法解析的导入：\n" + _format(problems)


def test_layers_only_depend_downward():
    problems = check_frontend.check_layers()
    assert not problems, "分层依赖被打破：\n" + _format(problems)


def test_no_platform_detection_and_no_inner_html():
    """前端一旦出现平台判断，跨平台抽象就漏了（07 文档 §10 第 4 行）。"""
    problems = check_frontend.check_patterns()
    assert not problems, "出现被禁止的写法：\n" + _format(problems)


def test_no_second_copy_of_the_category_rules_ships_in_the_frontend():
    """分类规则的单一真源不是"两份对齐"，而是只有一份（11 文档 §3.5）。"""
    problems = check_frontend.check_category_copy()
    assert not problems, "疑似分类规则副本：\n" + _format(problems)


def test_templates_have_no_inline_script_or_handlers():
    """CSP 是 script-src 'self'：内联脚本会被浏览器拒掉，而报错发生在运行时。"""
    problems = check_frontend.check_templates()
    assert not problems, "模板里有内联脚本或事件属性：\n" + _format(problems)


def test_the_checker_actually_sees_files():
    """探针测试：目录改名或路径写错时，上面五条会全部"通过"。"""
    modules = check_frontend._sources(JS)
    styles = list(STYLES.rglob("*.css"))
    assert len(modules) >= 20, f"只找到 {len(modules)} 个 JS 模块，检查路径是否正确"
    assert len(styles) >= 15, f"只找到 {len(styles)} 个样式文件，检查 STYLES 路径"


def test_layer_rules_cover_every_directory_under_js():
    """新增一层目录时必须同时给它写规则，否则它悄悄地不受约束。"""
    directories = {path.name for path in JS.iterdir() if path.is_dir()}
    assert directories == set(check_frontend.LAYER_RULES), (
        f"js/ 下的目录 {sorted(directories)} 与 LAYER_RULES "
        f"{sorted(check_frontend.LAYER_RULES)} 不一致"
    )


def test_only_entries_sit_at_the_source_root():
    """源码根只放**入口**：一页一个（18 文档 批 1）。多出来的文件就是没归层的代码。

    三个入口都短得能一眼读完——接令牌、挂外壳、取这一页要的数据、画。共用的开场在
    `pages/shell.tsx`，页面正文在 `pages/`，因此"根目录里的文件"与"页面"是一一对应的。
    """
    files = sorted(path.name for path in JS.iterdir() if path.is_file())
    assert files == ["about.tsx", "main.tsx", "settings.tsx"], files


def test_the_theme_is_rendered_server_side_and_static_js_is_gone():
    """防闪白从阻塞脚本换成服务端渲染（15 文档 §11.3）。

    原先 `static/js/theme.js` 是一个**普通脚本**：模块天然 defer，所以 Vite 的产物
    占不了这个位置（06 文档 §3.2 要它在首次绘制前跑完）。服务端本来就知道 `ui.theme`
    ——前端切换时双写进配置——于是模板直接渲染 `<html data-theme>`，那个文件与它跟
    `core/theme.ts` 重复的两个 localStorage 键名一起消失。

    这条盯模板与目录那一半；"服务端真的按配置渲染"由
    `tests/integration/test_web.py::test_shell_renders_the_configured_theme` 验。

    **三个页面共用一个模板基座**（`_shell.html`，18 文档 批 1），因此这几行只该出现在那里
    ——每一处复制都是一个漏改点，而漏改的症状（某一页闪白、某一页没有脚本）只在那一页上
    看得见。热力色同理（`data-heat`，18 文档 批 3）。
    """
    template = (check_frontend.TEMPLATES / "_shell.html").read_text(encoding="utf-8")
    assert '{% if theme %} data-theme="{{ theme }}"{% endif %}' in template
    assert '{% if heat %} data-heat="{{ heat }}"{% endif %}' in template
    assert "/static/js/" not in template, "模板不该再引用 static/js"
    assert not (STATIC / "js").exists(), "static/js 整个目录应该已经删除"
    # 入口的文件名带内容哈希，所以模板里是 Jinja 变量而不是字面路径（15 文档 §3.1）。
    assert 'type="module" src="{{ bundle.entry }}"' in template
    # 三个页面模板各自只填自己那部分，不许再自带 <html>/<head>/<script>。
    for name in ("dashboard.html", "settings.html", "about.html"):
        page = (check_frontend.TEMPLATES / name).read_text(encoding="utf-8")
        assert page.startswith('{% extends "_shell.html" %}'), name
        assert "<html" not in page and "<script" not in page, name


def test_relative_imports_carry_a_real_extension():
    """相对导入写真实扩展名（15 文档 §3.6）。

    这条保的是 `tests/frontend/*.test.ts` 那条路：Node 的 ESM 只认磁盘上的真路径，
    无后缀与 `.js` -> `.ts` 的回退它都不做。tsc 与 Vite 都能自己回退，因此少一个后缀
    只会在**跑 node 测试的那台机器上**红——这条把它提前到提交前。
    """
    problems = check_frontend.check_import_extensions()
    assert not problems, "导入缺少扩展名（跑 tools/fix_imports.py）：\n" + _format(problems)
