"""macOS 开机自启（``AutostartControl`` 的 macOS 实现，19 文档 §2.1）。

用 **LaunchAgent plist**（``~/Library/LaunchAgents/com.ravenhogwarts.omnisight.plist``，
``RunAtLoad``）而不是 ``SMAppService``：后者要求 macOS 13+ 且对 app 的安装位置有
要求（VM 与开发者目录里跑的包经常不满足），而 plist 在所有版本上都工作、内容是
纯文本可以用 :mod:`plistlib` 生成与校验，也能在 Windows 上完整测试。将来真需要
SMAppService 的体验（系统设置里的登录项页能管理它）再升级，接口不变。

``is_enabled`` 必须**精确比对指向的路径**（与 Windows 的 ``RegistryAutostart``
同一条要求，10 文档 §4）：用户把 ``.app`` 搬去别处之后，旧 plist 存在但指向的
是死路径——界面照旧显示"已启用"就是谎报。
"""

from __future__ import annotations

import logging
import plistlib
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

LABEL = "com.ravenhogwarts.omnisight"


def plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def render_plist(program: str) -> bytes:
    """plist 内容（纯函数，可测试）。"""
    return plistlib.dumps(
        {
            "Label": LABEL,
            "ProgramArguments": [program],
            "RunAtLoad": True,
            # 不做 KeepAlive：崩溃循环重启一个记录键盘的程序比"坏了就坏了"更糟。
            "KeepAlive": False,
        }
    )


class LaunchAgentAutostart:
    """实现 :class:`~omnisight.adapters.ports.AutostartControl`。"""

    __slots__ = ()

    def is_enabled(self) -> bool:
        try:
            with plist_path().open("rb") as handle:
                content = plistlib.load(handle)
        except (OSError, plistlib.InvalidFileException):
            return False
        arguments = content.get("ProgramArguments") or []
        # 精确比对：存在但指向别处 = 没启用（搬家后的残留），照实说。
        return bool(content.get("RunAtLoad")) and bool(arguments) and arguments[0] == _program()

    def set_enabled(self, enabled: bool) -> None:
        target = plist_path()
        if not enabled:
            target.unlink(missing_ok=True)
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(render_plist(_program()))
        logger.info("已写入开机自启 LaunchAgent：%s", target)


def _program() -> str:
    """自启项要拉起的程序：打包后是 .app 内的主程序。"""
    return sys.executable


__all__ = ["LABEL", "LaunchAgentAutostart", "plist_path", "render_plist"]
