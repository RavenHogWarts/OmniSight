"""应用装配（组合根）。

它只做两件事：解析命令行、把 :class:`~omnisight.core.lifecycle.Lifecycle` 跑起来。
任何"谁依赖谁"的决定都在 lifecycle 里，这里不放业务逻辑——组合根一旦开始承担
逻辑，就会变成第二个隐形的上帝对象。
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from . import __version__
from .core.lifecycle import Lifecycle


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="omnisight",
        description="本地应用使用时长与键盘统计工具",
    )
    parser.add_argument("--version", action="version", version=f"OmniSight {__version__}")
    parser.add_argument(
        "--autostart",
        action="store_true",
        help="由开机自启项调用（当前与手动启动行为相同，保留用于区分场景）",
    )
    parser.add_argument(
        "--takeover",
        action="store_true",
        help=(
            "接管正在退出的旧实例：加锁前多等一会儿。"
            "由托盘「以管理员身份重启」内部使用，不必手工输入（10 文档 §5.2）"
        ),
    )
    return parser


def run(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return Lifecycle(autostart_invocation=args.autostart, takeover=args.takeover).start()
