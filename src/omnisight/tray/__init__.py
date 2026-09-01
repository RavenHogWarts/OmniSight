"""系统托盘（合并两个旧项目 ``main.py`` 里的托盘逻辑）。"""

from .tray import TrayIcon, load_icon_image

__all__ = ["TrayIcon", "load_icon_image"]
