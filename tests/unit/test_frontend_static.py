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
    modules = list(JS.rglob("*.js"))
    styles = list((STATIC / "css").rglob("*.css"))
    assert len(modules) >= 20, f"只找到 {len(modules)} 个 JS 模块，检查路径是否正确"
    assert len(styles) >= 15, f"只找到 {len(styles)} 个样式文件"


def test_layer_rules_cover_every_directory_under_js():
    """新增一层目录时必须同时给它写规则，否则它悄悄地不受约束。"""
    directories = {path.name for path in JS.iterdir() if path.is_dir()}
    assert directories == set(check_frontend.LAYER_RULES), (
        f"js/ 下的目录 {sorted(directories)} 与 LAYER_RULES "
        f"{sorted(check_frontend.LAYER_RULES)} 不一致"
    )


def test_only_two_files_sit_at_the_js_root():
    """入口只能有 main.js 与阻塞的 theme.js。多出来的文件就是没归层的代码。"""
    files = sorted(path.name for path in JS.iterdir() if path.is_file())
    assert files == ["main.js", "theme.js"], files


def test_theme_boot_script_is_not_a_module():
    """它必须阻塞执行，否则深色偏好用户会看到一帧白底（06 文档 §3.2）。

    模块天然 defer，所以这个文件里不能出现 import/export——一旦有人给它加了
    import，浏览器就要把它当模块加载，闪白会回来而且没人会立刻发现。
    """
    text = (JS / "theme.js").read_text(encoding="utf-8")
    assert "import " not in text
    assert "export " not in text
    template = (check_frontend.TEMPLATES / "dashboard.html").read_text(encoding="utf-8")
    assert '<script src="/static/js/theme.js"></script>' in template
    assert 'type="module" src="/static/js/main.js"' in template
