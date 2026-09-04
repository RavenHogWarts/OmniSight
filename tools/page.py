r"""读仪表盘页面：截图 + 可量化的版面报告（14 文档 §8.3）。

``tools/page.mjs`` 是干活的那一半（Playwright 驱动已装的 Edge）；这个文件是门面，
存在的理由只有一个：**把"先起服务器"这一步吃掉**。否则每次看一眼布局都是三条命令
（起服务器 → 等它就绪 → 跑浏览器 → 记得关掉），而三条命令的工具没人会用第二次。

服务器已经在跑就直接用（读 ``.dev/runtime.json`` 再探一次 ``/healthz``）；没在跑就起
一个临时的，退出时收掉——``--keep`` 留着它，接下来要连着看好几轮时用这个。

用法::

    python tools/page.py                              # 总览 @1440 浅色
    python tools/page.py --view keyboard --width 1024 --theme dark
    python tools/page.py --all                        # 四视图 × 四宽度 × 深浅 = 32 张
    python tools/page.py --view overview --forced-colors --reduced-motion
    python tools/page.py --preset no-keyboard --view keyboard   # 降级态
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from omnisight.presentation.security import read_runtime_file  # noqa: E402

DEV_DIR = ROOT / ".dev"
STARTUP_TIMEOUT = 90.0
#: 播种一年数据要几十秒，而 --fresh 会重播。超时给宽一点，卡住时的报错比截断更有用。


def _alive(port: int) -> bool:
    """探活走 ``/healthz``：它免令牌、只回一个字面量（web.py 的 PUBLIC_ENDPOINTS）。"""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=2) as response:
            return response.status == 200
    except (urllib.error.URLError, OSError):
        return False


def _running_server() -> int | None:
    runtime = read_runtime_file(DEV_DIR)
    if not runtime:
        return None
    port = int(runtime.get("port") or 0)
    return port if port and _alive(port) else None


def start_server(extra: list[str]) -> subprocess.Popen:
    """起一个开发服务器，等到它真的能应答再返回。

    ``--quiet`` 让它只把 URL 打到 stdout，但**不靠读那行来判断就绪**：进程可能死在
    播种阶段，那时 stdout 里什么都没有，而"一直读不到"和"还没写出来"分不开。
    探 ``/healthz`` 是唯一不会误判的信号。
    """
    command = [sys.executable, str(ROOT / "tools" / "devserver.py"), "--quiet", *extra]
    process = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    deadline = time.monotonic() + STARTUP_TIMEOUT
    while time.monotonic() < deadline:
        if _running_server() is not None:
            return process
        if process.poll() is not None:
            output = (process.stdout.read() or b"").decode("utf-8", "replace")
            raise SystemExit(f"开发服务器启动失败（退出码 {process.returncode}）：\n{output}")
        time.sleep(0.4)
    process.terminate()
    raise SystemExit(f"开发服务器在 {STARTUP_TIMEOUT:.0f} 秒内没有就绪")


def _require_playwright() -> None:
    """playwright-core 是 devDependency，缺了要给出能照着做的一句话，而不是 Node 的堆栈。"""
    if (ROOT / "node_modules" / "playwright-core" / "package.json").exists():
        return
    raise SystemExit(
        "缺少 playwright-core（开发期依赖，产物里没有 npm 包）。装它：\n"
        "  pnpm install\n"
        "它是 1 个包、0 个传递依赖，且**不下载浏览器**——驱动的是机器上已装的 Edge。"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="用无头浏览器读仪表盘：截图 + 版面报告（需要时自己起开发服务器）"
    )
    parser.add_argument(
        "--view", action="append", default=[],
        help="overview / apps / keyboard / insights，可重复",
    )
    parser.add_argument(
        "--width", action="append", default=[], help="视口宽度，可重复（默认 1440）"
    )
    parser.add_argument(
        "--theme", action="append", default=[], choices=["light", "dark"], help="可重复"
    )
    parser.add_argument("--range", default="week", help="周期（day / week / month / year / total）")
    parser.add_argument("--all", action="store_true", help="四视图 × 1024/1280/1440/1920 × 深浅")
    parser.add_argument("--settings", action="store_true", help="打开设置抽屉后再截")
    parser.add_argument(
        "--onboarding", action="store_true", help="保留首启说明那张模态（默认点掉）"
    )
    parser.add_argument("--forced-colors", action="store_true", help="强制颜色模式（14 §8.3）")
    parser.add_argument(
        "--reduced-motion", action="store_true", help="prefers-reduced-motion（14 §8.3）"
    )
    parser.add_argument("--full-page", action="store_true", help="整页截图而不是只截视口")
    parser.add_argument("--out", default=str(DEV_DIR / "shots"), help="输出目录")
    parser.add_argument(
        "--keep", action="store_true", help="用完不关开发服务器（接着看好几轮时用）"
    )
    parser.add_argument(
        "--preset", default=None, help="起服务器时用的能力集（见 devserver.py --preset）"
    )
    parser.add_argument("--days", type=int, default=None, help="起服务器时的播种天数")
    parser.add_argument("--fresh", action="store_true", help="起服务器时重播数据")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _require_playwright()

    server: subprocess.Popen | None = None
    port = _running_server()
    if port is None:
        extra: list[str] = []
        if args.preset:
            extra += ["--preset", args.preset]
        if args.days is not None:
            extra += ["--days", str(args.days)]
        if args.fresh:
            extra.append("--fresh")
        print("开发服务器没在跑，正在起一个……")
        server = start_server(extra)
        port = _running_server()
    else:
        # 复用时**不能**套用 --preset：那份能力集是启动时装配进去的，改不了。
        for name in ("preset", "days"):
            if getattr(args, name) is not None:
                print(f"注意：已有服务器在 {port} 上跑着，--{name} 被忽略（重启才生效）")
        if args.fresh:
            print(f"注意：已有服务器在 {port} 上跑着，--fresh 被忽略（重启才生效）")

    forward = ["--range", args.range, "--out", args.out]
    for view in args.view:
        forward += ["--view", view]
    for width in args.width:
        forward += ["--width", str(width)]
    for theme in args.theme:
        forward += ["--theme", theme]
    for flag in ("all", "settings", "onboarding", "forced_colors", "reduced_motion", "full_page"):
        if getattr(args, flag):
            forward.append("--" + flag.replace("_", "-"))

    try:
        completed = subprocess.run(
            ["node", str(ROOT / "tools" / "page.mjs"), *forward], cwd=ROOT, check=False
        )
    except FileNotFoundError:
        raise SystemExit("找不到 node。装 Node 22+ 后重试（前端工具链的唯一前置）。") from None
    finally:
        if server is not None and not args.keep:
            server.terminate()
            server.wait(timeout=10)
        elif server is not None:
            print(f"开发服务器留在 {port} 上继续跑（--keep）。停它：结束那个 python 进程。")
    return completed.returncode


if __name__ == "__main__":  # pragma: no cover
    # 见 tools/_console.py：runner 上 stdout 是管道，按 locale 挑到 cp1252，
    # 一行中文输出就能让进程死在 UnicodeEncodeError 上。
    from _console import use_utf8_output

    use_utf8_output()
    raise SystemExit(main())
