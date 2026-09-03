"""前端类型检查（07 文档 §2.1、11 文档 §8.4）。

``static/js`` 下的 ``.js`` 就是浏览器加载的那份文件——tsc 只**读**它，`noEmit` 为真，
因此"零构建"这条性质没有变：仓库里没有构建产物，PyInstaller 照旧拷整个 static 目录。

**它补的是哪个洞**：``types/api.d.ts`` 声明了后端每个响应的形状，视图读
``state.data.appsPeriod`` 时字段拼错、少判一次 null 都会在这里红。没有它的时候，
后端改一个字段名前端只是静默显示空值，而"这段时间没有记录"恰好也是合法状态。
``tools/check_frontend.py`` 查不到这类错误（它只做导入解析与文本模式），
``tests/frontend/dom-shim.js`` 也测不到（它断言渲染结构）。

**Node 不在就跳过**，与 ``tests/unit/test_frontend_js.py`` 同一条原则：Node 是"有就用"
的开发期便利，不是运行依赖。装了的机器会跑到。版本由 ``package.json`` 的
devDependencies 钉住，``pnpm-lock.yaml`` 锁死具体产物。

发布流水线传 ``--require``：那里刚 ``pnpm install`` 过，"找不到 tsc"只可能是安装
出了问题，静静跳过等于把门禁悄悄拆掉。
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TSCONFIG = ROOT / "tsconfig.json"
PACKAGE_JSON = ROOT / "package.json"
#: pnpm 装出来的入口。走 `node <这个文件>` 而不是 .bin 里的包装器：那边在 Windows 上
#: 是 tsc / tsc.CMD / tsc.ps1 三件套，subprocess 得挑对哪一件。
LOCAL_TSC = ROOT / "node_modules" / "typescript" / "bin" / "tsc"


def pinned_version() -> str | None:
    """package.json 里钉住的 TypeScript 版本。**这里不留第二个字面量**。"""
    try:
        payload = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    version = payload.get("devDependencies", {}).get("typescript")
    return str(version) if version else None


def resolve_command() -> list[str] | None:
    """跑 tsc 的命令行，找不到编译器时给 None（调用方据此跳过）。"""
    node = shutil.which("node")
    if node and LOCAL_TSC.is_file():
        return [node, str(LOCAL_TSC)]
    on_path = shutil.which("tsc")
    if on_path:
        return [on_path]
    return None


def run() -> tuple[int, str]:
    """跑一次类型检查。返回 ``(退出码, 输出)``；``退出码 == -1`` 表示没有编译器。"""
    command = resolve_command()
    if command is None:
        return -1, "未找到 tsc（装了 Node 的话跑 `pnpm install`）"
    result = subprocess.run(
        [*command, "-p", str(TSCONFIG), "--pretty", "false"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )
    return result.returncode, (result.stdout or "") + (result.stderr or "")


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    require = "--require" in argv
    code, output = run()
    if code == -1:
        if require:
            print(output, file=sys.stderr)
            return 1
        print(output)
        return 0
    if code == 0:
        js = ROOT / "src" / "omnisight" / "presentation" / "static" / "js"
        modules = len(list(js.rglob("*.js")))
        declarations = len(list((js / "types").glob("*.d.ts")))
        print(f"前端类型检查通过（{modules} 个 JS 模块、{declarations} 份类型声明）")
        return 0
    print("类型检查失败：", file=sys.stderr)
    print(output.rstrip(), file=sys.stderr)
    return 1


if __name__ == "__main__":
    # 见 tools/_console.py：runner 上 stdout 是管道，按 locale 挑到 cp1252，
    # 一行中文输出就能让进程死在 UnicodeEncodeError 上。
    from _console import use_utf8_output

    use_utf8_output()
    sys.exit(main())
