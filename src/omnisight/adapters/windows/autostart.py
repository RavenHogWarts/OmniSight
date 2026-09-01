"""注册表开机自启（合并两个旧项目的 ``autostart.py``）。

两处沿用旧实现的正确做法、一处改进：

* 沿用：``is_enabled()`` **精确比对命令行**而非只判断键存在。用户移动了程序位置
  后，托盘菜单要显示"未启用"而不是谎报已启用。
* 沿用：只写 ``HKCU``，不碰 ``HKLM``——不需要管理员权限，也不影响其他用户。
* 改进：写入时附加 ``--autostart``，用于区分"用户手动启动"与"开机自启"
  （例如开机自启时不弹导入向导）。
"""

from __future__ import annotations

import logging
import sys
import winreg
from pathlib import Path

logger = logging.getLogger(__name__)

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "OmniSight"
AUTOSTART_FLAG = "--autostart"


def startup_command() -> str:
    """自启项应有的命令行。开发模式指向 ``python -m omnisight``。"""
    executable = Path(sys.executable).resolve()
    if getattr(sys, "frozen", False):
        return f'"{executable}" {AUTOSTART_FLAG}'
    return f'"{executable}" -m omnisight {AUTOSTART_FLAG}'


class RegistryAutostart:
    __slots__ = ("_command", "_value_name")

    def __init__(self, value_name: str = VALUE_NAME, command: str | None = None) -> None:
        self._value_name = value_name
        self._command = command or startup_command()

    @property
    def command(self) -> str:
        return self._command

    def _read(self) -> str | None:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                value, _ = winreg.QueryValueEx(key, self._value_name)
        except FileNotFoundError:
            return None
        except OSError as exc:  # pragma: no cover - 注册表被策略锁定
            logger.warning("读取自启项失败：%s", exc)
            return None
        return value if isinstance(value, str) else None

    def is_enabled(self) -> bool:
        return self._read() == self._command

    def is_present(self) -> bool:
        """自启项存在，但可能指向旧路径。用于启动时的自愈判断。"""
        return self._read() is not None

    def set_enabled(self, enabled: bool) -> None:
        if enabled:
            with winreg.CreateKeyEx(
                winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
            ) as key:
                winreg.SetValueEx(key, self._value_name, 0, winreg.REG_SZ, self._command)
            logger.info("已启用开机自启")
            return
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
            ) as key:
                winreg.DeleteValue(key, self._value_name)
        except FileNotFoundError:
            return
        logger.info("已关闭开机自启")

    def repair_if_stale(self) -> bool:
        """自启项存在但命令行不匹配时改写为当前命令，返回是否改写过。

        用户的意图是"要自启"，程序换了位置或从开发模式切到打包版这种细节变化
        不该让这个意图丢失（10 文档 §4）。
        """
        current = self._read()
        if current is None or current == self._command:
            return False
        logger.info("自启项命令行已过期，改写为当前程序路径")
        self.set_enabled(True)
        return True
