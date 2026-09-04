"""把前端类型检查接进 pytest（11 文档 §8.4）。

与 ``test_frontend_js.py`` 同一个套路：实现在 ``tools/`` 里，这里是**执行机制**。
没有这一层，类型检查就只能靠人记得手动跑，三个月后 ``types/api.d.ts`` 会和后端
默默漂开——而那正是引入它要解决的问题。

Node 不在时跳过而不是失败：项目不把 Node 当运行依赖（07 文档 §2）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import check_types  # noqa: E402

#: 源码根。15 文档选了方案 A 之后源码在 frontend/src，产物在 static/dist。
JS = ROOT / "frontend" / "src"


@pytest.mark.skipif(check_types.resolve_command() is None, reason="未装 tsc，跳过类型检查")
def test_frontend_type_check_passes():
    code, output = check_types.run()
    if code != 0:
        sys.stdout.write(output)
    assert code == 0, "前端类型检查失败（详见上方 tsc 输出）"


def test_tsconfig_covers_every_module_and_emits_nothing():
    """两条不能松的设定：检查范围盖住整个 js/，且**绝不产出文件**。

    ``noEmit`` 一旦为假，tsc 会把编译结果写到源码旁边，而浏览器加载的就是那些文件——
    "零构建"从此不成立，且没人会立刻发现。
    """
    # tsconfig 是 JSONC（带注释），按行剔掉 // 注释再解析。
    raw = (ROOT / "tsconfig.json").read_text(encoding="utf-8")
    stripped = "\n".join(
        line for line in raw.splitlines() if not line.lstrip().startswith("//")
    )
    config = json.loads(stripped)
    options = config["compilerOptions"]
    assert options["noEmit"] is True
    # checkJs 在迁移期是 false（见 tsconfig.json 里的理由）。这里断言"两者一致"
    # 而不是断言某个值：allowJs 关掉时 checkJs 就没有意义，两个一起删才对。
    assert options["checkJs"] is False
    assert options["allowJs"] is True
    # React 的类型要进来，所以不能再写 "types": []（那条随 15 文档方案 A 作废）。
    # 换成断言 jsx 的编译模式：写错这一处，每个 .tsx 都会报 "JSX 未启用"。
    assert options["jsx"] == "react-jsx"
    assert any("frontend/src" in pattern for pattern in config["include"])
    # 三种后缀都要在检查范围里：迁移期 .js / .ts / .tsx 并存（15 文档 §8）。
    patterns = " ".join(config["include"])
    for suffix in (".js", ".ts", ".tsx"):
        assert suffix in patterns, f"include 没盖住 *{suffix}：{config['include']}"


def test_the_pinned_typescript_version_is_the_installed_one():
    """package.json 与实际装上的版本对不上时，本地与流水线的检查结果会不一样。"""
    pinned = check_types.pinned_version()
    assert pinned, "package.json 没有钉住 typescript 版本"
    installed = ROOT / "node_modules" / "typescript" / "package.json"
    if not installed.is_file():
        pytest.skip("未安装 node_modules")
    actual = json.loads(installed.read_text(encoding="utf-8"))["version"]
    assert actual == pinned, f"package.json 钉的是 {pinned}，装上的是 {actual}"


def test_every_module_is_inside_the_checked_tree():
    """探针：include 写错时上面那条会空跑通过。"""
    modules = [*JS.rglob("*.js"), *JS.rglob("*.ts"), *JS.rglob("*.tsx")]
    assert len(modules) >= 20, f"只找到 {len(modules)} 个模块，检查路径"
    declarations = list((JS / "types").glob("*.d.ts"))
    assert declarations, "types/ 下没有类型声明——api.d.ts 是这套检查的核心"


@pytest.mark.skipif(check_types.resolve_command() is None, reason="未装 tsc")
def test_a_planted_type_error_is_caught():
    """自测：往一个模块里塞一处类型错误，检查必须红。

    没有这条，"类型检查通过"可能只是因为 tsc 根本没看那些文件（include 写错、
    checkJs 被关掉），而那种失败是静默的。
    """
    target = next(p for p in (JS / "core").iterdir() if p.stem == "store")
    original = target.read_text(encoding="utf-8")
    # 往 store 里塞一个不存在的切片名——正常情况下 keyof State 会拦住它。
    planted = original + "\nsetState('nonexistent_slice_for_selftest', 1);\n"
    try:
        target.write_text(planted, encoding="utf-8")
        code, output = check_types.run()
    finally:
        target.write_text(original, encoding="utf-8")
    # tsc 的失败码不止 1（有诊断时给 2），只断言非零。
    assert code > 0, "植入的类型错误没有被发现"
    assert "nonexistent_slice_for_selftest" in output
