r"""开发期仪表盘服务器：只为"把前端页面调出来"存在（11 文档 §5、14 文档 §8.3）。

与 ``python -m omnisight`` 的区别有三条，都是刻意的：

1. **不采集、不起托盘。** 只装配 ``presentation`` + ``services`` + 一个库。调 UI 不需要
   真实采集，而真实采集要管理员权限、会写真实数据目录、还会让页面上的数字每秒都在动
   ——那样任何两张截图都不可比，而"两张截图可比"是改版对照的前提。
2. **数据是合成的，落在仓库内 ``.dev/``。** 绝不碰 ``%LOCALAPPDATA%\OmniSight\``：
   调 UI 时会切设置、会点导入向导，这些都写库与配置。真实数据不该承担这个风险，
   所以 :func:`_refuse_production_dir` 直接把那条路堵死。
3. **能力（``Capabilities``）可以从命令行伪造。** 06 文档 §4.2 的三级降级表达在本机
   只看得到 tier 1 那一档，而降级态恰恰是最容易画错、也最少被人看见的部分——
   ``--preset linux-wayland`` 之类是唯一能把那些分支调出来的办法。

用法::

    python tools/devserver.py                       # 起服务并打印带令牌的 URL
    python tools/devserver.py --open                # 顺带用默认浏览器打开
    python tools/devserver.py --open --watch        # 再带上 vite watch：改完 frontend/ 页面自己刷新
    python tools/devserver.py --days 400 --fresh    # 重播一年数据
    python tools/devserver.py --preset no-keyboard  # 看键盘不可用时的降级态
"""

from __future__ import annotations

import argparse
import random
import sys
import threading
import webbrowser
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

from flask import request  # noqa: E402

import _devlive  # noqa: E402
from omnisight.adapters.ports import Capabilities  # noqa: E402
from omnisight.core import paths  # noqa: E402
from omnisight.core.config import default_config  # noqa: E402
from omnisight.presentation import security  # noqa: E402
from omnisight.presentation.web import AppContext, WebServer, create_app  # noqa: E402
from omnisight.services import Services  # noqa: E402
from omnisight.storage.database import Database  # noqa: E402
from omnisight.storage.migrations import TARGET_VERSION, migrate  # noqa: E402

#: 开发数据的落点。**不放 .bench/**：那个目录是基准库的地盘，而基准库动辄几个 GB、
#: 播一次十分钟，不该被"我想看一眼键盘页"顺手删掉。
DEV_DIR = ROOT / ".dev"
DEV_DB = DEV_DIR / "dev.db"

#: 刻意避开生产的 6100：开着真实实例时仍然能起开发服务器，两边互不打扰。
DEV_PORT = 6180

#: **固定令牌**，因为 URL 要能被人贴进浏览器、被 agent 拼出来，而每次重启都变的令牌
#: 让这两件事都得先去读一个文件。这不削弱 08 文档 §3 的威胁模型：那套机制防的是
#: *任意网页*（靠自定义头触发 CORS 预检 + Host 校验，两者在这里一字未改），而不是
#: 本机进程——能读到 runtime.json 的程序本来就能直接打开数据库文件。
#: 令牌校验本身没有关掉：请求照样要带头，只是这一份的值是已知的。
DEV_TOKEN = "omnisight-dev-token"

_BASE = Capabilities(
    platform_id="windows",
    tier=1,
    os_version="10.0.26200",
    keyboard=True,
    keyboard_backend="raw_input",
    keyboard_durations=True,
    key_position_stable=True,
    foreground=True,
    window_titles=True,
    idle=True,
    icons=True,
    autostart=True,
    tray=True,
)

#: 降级预设。名字对齐 13 文档 §4.1 的平台分级，外加几个单点缺失——
#: 单点缺失比"整个平台降级"更常见，也更容易在实现时被漏掉。
PRESETS: dict[str, Capabilities] = {
    "full": _BASE,
    # 二级平台：能采，但按键时长与物理键位拿不到（13 文档 §4.1）。
    "macos": replace(
        _BASE,
        platform_id="macos",
        tier=2,
        os_version="15.5",
        keyboard_backend="event_tap",
        keyboard_durations=False,
        permissions_required=("accessibility", "input_monitoring"),
        permissions_granted=("accessibility",),
        setup_hint="在「系统设置 › 隐私与安全性 › 输入监控」中勾选 OmniSight",
    ),
    # 三级平台：合并的核心价值（按键归因到应用）在这里就是拿不到。
    "linux-wayland": replace(
        _BASE,
        platform_id="linux",
        tier=3,
        os_version="6.11 / Wayland",
        keyboard_backend="evdev",
        keyboard_durations=False,
        key_position_stable=True,
        foreground=False,
        window_titles=False,
        icons=False,
        autostart=False,
    ),
    "no-keyboard": replace(
        _BASE, keyboard=False, keyboard_backend="none", keyboard_durations=False
    ),
    "no-foreground": replace(_BASE, foreground=False, window_titles=False),
    "no-icons": replace(_BASE, icons=False),
    "no-titles": replace(_BASE, window_titles=False),
}


class _IdleCapture:
    """假的采集快照：只让状态点显示"正常"。

    开发服务器不采集，而 ``context.capture is None`` 会让 ``/api/v1/status`` 如实上报
    "采集没在跑"——于是每一张截图右上角都挂着一枚「采集异常」的红点，把状态点自己那
    三档表达（06 文档 §4.2 第二级）永久钉在最差的那一档上。调版面时要看的是**常态**，
    所以默认给一份"一切正常"的快照；想看真实的异常态用 ``--capture-down``。

    字段形状照抄 ``core/lifecycle.py`` 的 ``snapshot()``：多一个少一个字段，前端读到的
    就是 undefined，而那种坏法在页面上是安静的。
    """

    __slots__ = ("backend",)

    def __init__(self, backend: str) -> None:
        self.backend = backend

    def snapshot(self) -> dict[str, object]:
        return {
            "foreground": {"running": True, "backend": "win32"},
            "keyboard": {"running": True, "backend": self.backend},
            "writer": {"running": True, "queue_depth": 0, "dropped_events": 0},
            "paused": False,
            "queue_depth": 0,
            "dropped_events": 0,
        }


def _refuse_production_dir(data_dir: Path) -> None:
    """开发服务器绝不在真实数据目录上跑。

    调 UI 会切设置、会点导入向导、会改主题——全都落库与落配置。真实数据目录里是
    用户几个月的记录，不该由一个"我想看一眼布局"的命令来承担这个风险。
    """
    try:
        production = paths.data_dir().resolve()
    except OSError:  # pragma: no cover - 取不到就没有可比对象，放过
        return
    if data_dir.resolve() == production:
        raise SystemExit(
            f"拒绝在生产数据目录上启动开发服务器：{production}\n"
            f"用 --data-dir 指向别处（默认就是仓库内的 {DEV_DIR}）。"
        )


def ensure_database(
    db_path: Path, *, days: int, fresh: bool, gap_days: int, tz: str, quiet: bool = False
) -> Database:
    """准备好一个有数据的库。已经存在就直接用——每次都重播会让启动慢到没人愿意用。

    播种走 ``tools/seed.py``，也就是**生产写入路径**（``EventQueue`` → ``StorageWriter``）。
    不另写一份 INSERT：那样造出的库形态与真实的不同，而 UI 上"聚合缺一档"与"没有数据"
    长得一模一样，用假形态的库看不出来（11 文档 §5）。
    """
    import seed as seed_tool

    if fresh:
        for suffix in ("", "-wal", "-shm"):
            db_path.with_name(db_path.name + suffix).unlink(missing_ok=True)
    existed = db_path.exists()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = Database(db_path)
    migrate(db)
    if existed:
        _apply_auto_categories(db, quiet=quiet)
        return db
    zone = ZoneInfo(tz)
    if not quiet:
        print(f"正在播种 {days} 天的合成数据 → {db_path}")
    report = seed_tool.seed(
        db,
        days=days,
        end=datetime.now(zone).date(),
        tz=zone,
        rng=random.Random(20260901),
        store_raw=True,
        gap_days=gap_days,
        titles=True,
        progress=days >= 200,
    )
    if not quiet:
        print(f"播种完成：{report.render()}")
    _apply_auto_categories(db, quiet=quiet)
    return db


def _apply_auto_categories(db: Database, *, quiet: bool = False) -> None:
    """补自动分类——**生产里这一步在 ``Lifecycle._refresh_categories``**，开发服务器
    不跑生命周期，于是不做就每个应用都是"未分类"。

    后果不是"少一列元数据"而是**整屏配色失真**：类别构成条只有一段灰、活动带上面板
    也只有一层，看起来像功能没做（14 文档 §4.3 的类别堆叠就是这样被瞒过去的）。
    只改 ``category_source = 'auto'`` 的行，和生产同一条规则。
    """
    from omnisight.services import categories as category_rules
    from omnisight.storage.repositories.apps import AppDirectory

    changed = AppDirectory(db).apply_auto_categories(category_rules.categorize)
    if changed and not quiet:
        print(f"按当前规则补了 {changed} 个应用的自动分类")


def build_app(
    db: Database,
    capabilities: Capabilities,
    *,
    port: int,
    data_dir: Path,
    tz: str,
    capture_down: bool = False,
    onboarding: bool = False,
    live_reload: bool = False,
):
    """装配 Flask 应用。与生产的差别只有两处，都写在下面。"""
    config = replace(
        default_config(),
        server=replace(default_config().server, port=port),
        # SSE 关掉：没有采集就没有事件可推，开着只会让前端敲一个必然 404 的端点，
        # 而那条 404 会出现在 tools/page.mjs 的失败请求清单里——一个每次都在的假警报
        # 比没有清单更糟。关掉后 main.js 直接走 30 秒轮询（见 core/stream.js）。
        privacy=replace(default_config().privacy, realtime_stream=False),
    )
    context = AppContext(
        config=config,
        database=db,
        capabilities=capabilities,
        token=DEV_TOKEN,
        started_at=datetime.now(ZoneInfo(tz)).isoformat(timespec="seconds"),
        data_dir=data_dir,
        schema_version=TARGET_VERSION,
        capture=None if capture_down else _IdleCapture(capabilities.keyboard_backend),
    )
    def on_config_change(new_config) -> None:
        """设置改完后表现层要看到新配置——生产里由 `lifecycle.py:on_config_change` 做。

        **少了它，主题切换在开发服务器上看起来是坏的**：`ui.theme` 由设置服务写进它自己
        那份配置，而页面外壳的 `<html data-theme>` 读的是 `AppContext.config`
        （web.py:index，15 文档 §11.3）。两份不同步的症状是"在设置里切成深色，刷新又变回
        跟随系统"——而那正是防闪白要修的东西，于是这个缺口会伪装成 §11.3 的 bug。
        """
        context.config = new_config
        context.paused = new_config.capture.paused

    context.services = Services.build(
        database=db,
        config=config,
        capabilities=capabilities,
        config_path=data_dir / "config.json",
        data_dir=data_dir,
        on_config_change=on_config_change,
    )
    app = create_app(context)
    _disable_static_cache(app)
    if live_reload:
        # 产物变了就让页面自己刷新（见 tools/_devlive.py）。默认不开：它给页面加了一段
        # 生产没有的脚本，而截图与版面报告应该拍到与生产一致的那张页面。
        _devlive.install(app, token=DEV_TOKEN)
    if not onboarding:
        # 首启说明是个铺满全屏的模态（08 文档 §6.1）。库是新播的，所以它每次都会出现，
        # 于是每张截图拍到的都是那张说明而不是仪表盘。默认先替它按下"我看过了"——
        # 想看那一屏本身用 --onboarding，或者 `#about` 那条 hash（main.js 认它）。
        context.services.onboarding.acknowledge()
    return app, context


def _disable_static_cache(app) -> None:
    """页面外壳与静态资源一律 no-store。

    产物文件名带内容哈希，所以 chunk 本身取不到旧的；**要紧的是页面外壳**——``/`` 的名字
    是固定的，而外壳里写着入口 chunk 的文件名（``web.py:index`` 读清单渲染它）。重建之后
    外壳若还是缓存里那份，页面加载的就仍然是上一次的 chunk，症状是"我明明重新构建了"。
    开发期直接掐掉，代价是每次刷新多几十毫秒。
    """
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

    @app.after_request
    def _no_store(response):
        if request.path.startswith("/static/") or request.path == "/":
            response.headers["Cache-Control"] = "no-store, must-revalidate"
        return response


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="OmniSight 开发期仪表盘服务器（不采集、不起托盘、用合成数据）"
    )
    parser.add_argument("--port", type=int, default=DEV_PORT, help=f"监听端口（默认 {DEV_PORT}）")
    parser.add_argument(
        "--data-dir", type=Path, default=DEV_DIR, help=f"开发数据目录（默认 {DEV_DIR}）"
    )
    parser.add_argument(
        "--days", type=int, default=45, help="播种天数（默认 45，够看到日/周/月三档）"
    )
    parser.add_argument(
        "--gap-days", type=int, default=2, help="完全没有数据的天数，用来看采集空档"
    )
    parser.add_argument("--tz", default="Asia/Shanghai")
    parser.add_argument("--fresh", action="store_true", help="先删掉已有的库再重播")
    parser.add_argument(
        "--preset",
        default="full",
        choices=sorted(PRESETS),
        help="伪造的能力集，用来调出降级态（06 文档 §4.2）",
    )
    parser.add_argument(
        "--capture-down", action="store_true",
        help="如实上报采集没在跑（状态点显示异常态），默认给一份正常的假快照",
    )
    parser.add_argument(
        "--onboarding", action="store_true",
        help="保留首启说明那张模态，默认自动确认掉",
    )
    parser.add_argument(
        "--watch", action="store_true",
        help="同一进程内起 vite build --watch，并在产物更新后让页面自己刷新（需 Node）",
    )
    parser.add_argument(
        "--live-reload", action="store_true",
        help="只开自动刷新，不起 vite——watch 你自己在别处跑（pnpm dev）",
    )
    parser.add_argument("--open", action="store_true", help="启动后用默认浏览器打开")
    parser.add_argument("--quiet", action="store_true", help="只打印 URL，供脚本捕获")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    data_dir = args.data_dir
    _refuse_production_dir(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    db = ensure_database(
        data_dir / DEV_DB.name,
        days=args.days,
        fresh=args.fresh,
        gap_days=args.gap_days,
        tz=args.tz,
        quiet=args.quiet,
    )
    capabilities = PRESETS[args.preset]
    app, context = build_app(
        db,
        capabilities,
        port=args.port,
        data_dir=data_dir,
        tz=args.tz,
        capture_down=args.capture_down,
        onboarding=args.onboarding,
        live_reload=args.watch or args.live_reload,
    )
    server = WebServer(app, "127.0.0.1", args.port)
    server.start()
    # 与生产同一个文件、同一个写法：tools/page.py 与 tools/smoke.py 都靠它找端口与令牌。
    security.write_runtime_file(data_dir, port=server.port, token=DEV_TOKEN)
    # 服务先起来再起 vite：第一次构建要几百毫秒，这期间页面已经能开（哪怕产物还缺，
    # 注入的脚本会在构建完成时把它刷成仪表盘）。
    vite = _devlive.start_vite_watch(ROOT, quiet=args.quiet) if args.watch else None

    url = context.config.dashboard_url(DEV_TOKEN)
    if args.quiet:
        print(url, flush=True)
    else:
        print()
        print(f"  仪表盘   {url}")
        print(
            f"  能力集   {args.preset}"
            f"（platform={capabilities.platform_id} tier={capabilities.tier}）"
        )
        print(f"  数据     {db.path}")
        static_root = paths.resource_dir() / "presentation" / "static"
        print(f"  静态资源 {static_root}（不缓存）")
        if args.watch:
            print("  前端     vite build --watch 已在本进程内，保存即重建 + 页面自动刷新")
        elif args.live_reload:
            print("  前端     自动刷新已开；重建要你自己跑 `pnpm dev`")
        else:
            print("  前端     改了 frontend/ 要 `pnpm build` 才生效（或用 --watch）")
        print()
        print("  Ctrl+C 停止")
        print(flush=True)
    if args.open:
        webbrowser.open(url)

    stop = threading.Event()
    try:
        stop.wait()
    except KeyboardInterrupt:
        if not args.quiet:
            print("\n正在停止……")
    finally:
        _devlive.stop_vite_watch(vite)
        server.stop()
        security.remove_runtime_file(data_dir)
        db.close()
    return 0


if __name__ == "__main__":  # pragma: no cover
    # 见 tools/_console.py：runner 上 stdout 是管道，按 locale 挑到 cp1252，
    # 一行中文输出就能让进程死在 UnicodeEncodeError 上。
    from _console import use_utf8_output

    use_utf8_output()
    raise SystemExit(main())
