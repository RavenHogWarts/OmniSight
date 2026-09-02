"""托盘图标与菜单。

两处沿用旧实现里正确的做法、一处是新增的必需能力：

* 沿用 KeyTrace 的 ``icon.update_menu()``（TimeLens 是重建 ``icon.menu``，
  前者才是 pystray 的正确用法）。
* 沿用"图标资源缺失就用生成的纯色图标兜底"，不让一个 PNG 拖垮启动。
* 新增：**托盘不可用时的无托盘运行路径**。托盘是唯一退出入口的设计会让任何一次
  失败都变成"进程杀不掉"的投诉（10 文档 §5.1）。

菜单项按 10 文档 §5 的清单，M6 补齐其中三项：

* **暂停记录**（勾选态）：08 文档 §5 要求的一键停止。需要暂停的时候用户往往不想
  先开浏览器，托盘是它唯一合理的位置；图标同时切成灰度，让"还在记录吗"在托盘上
  直接有答案。
* **打开日志目录**：崩溃报告与运行日志都在那里（10 文档 §8），出问题时这是让用户
  自己拿到材料的最短路径。
* **关于与隐私说明**：把首启说明重新打开一次（08 文档 §6.1），而不是只在第一次
  运行时出现一次就再也找不到。
"""

from __future__ import annotations

import logging
import threading
import webbrowser
from collections.abc import Callable
from pathlib import Path

from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)

ICON_SIZE = 64
ACCENT = (47, 141, 251, 255)
MUTED = (140, 140, 148, 255)


def load_icon_image(asset: Path | None = None, *, paused: bool = False) -> Image.Image:
    """加载托盘图标；文件缺失或损坏时生成一个。

    暂停状态用灰度版本，让"还在记录吗"这个问题在托盘上直接有答案，不必打开页面。
    """
    if asset is not None and asset.exists():
        try:
            image = Image.open(asset).convert("RGBA")
            return _to_grayscale(image) if paused else image
        except OSError:
            logger.warning("托盘图标 %s 无法读取，改用生成的图标", asset)
    return _generate_icon(paused=paused)


def _generate_icon(*, paused: bool) -> Image.Image:
    image = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    color = MUTED if paused else ACCENT
    draw.ellipse((4, 4, ICON_SIZE - 4, ICON_SIZE - 4), fill=color)
    draw.ellipse((22, 22, ICON_SIZE - 22, ICON_SIZE - 22), fill=(255, 255, 255, 255))
    return image


def _to_grayscale(image: Image.Image) -> Image.Image:
    grey = image.convert("LA").convert("RGBA")
    return grey


class TrayIcon:
    """托盘封装。``available`` 为 False 时所有方法都是安全的空操作。"""

    __slots__ = ("_asset", "_icon", "_paused", "_shutdown", "actions", "available")

    def __init__(
        self,
        *,
        dashboard_url: Callable[[], str],
        on_quit: Callable[[], None],
        autostart_state: Callable[[], bool] | None = None,
        on_toggle_autostart: Callable[[bool], None] | None = None,
        paused_state: Callable[[], bool] | None = None,
        on_toggle_pause: Callable[[bool], None] | None = None,
        open_data_dir: Callable[[], None] | None = None,
        open_logs_dir: Callable[[], None] | None = None,
        on_about: Callable[[], None] | None = None,
        asset: Path | None = None,
        available: bool = True,
    ) -> None:
        self.actions = {
            "dashboard_url": dashboard_url,
            "on_quit": on_quit,
            "autostart_state": autostart_state,
            "on_toggle_autostart": on_toggle_autostart,
            "paused_state": paused_state,
            "on_toggle_pause": on_toggle_pause,
            "open_data_dir": open_data_dir,
            "open_logs_dir": open_logs_dir,
            "on_about": on_about,
        }
        self.available = available
        self._asset = asset
        self._paused = bool(paused_state()) if paused_state is not None else False
        self._icon: object | None = None
        self._shutdown = threading.Event()

    # ── 生命周期 ────────────────────────────────────────────────────────
    def run(self) -> None:
        """阻塞当前线程。无托盘时阻塞在退出事件上，仍然可被 :meth:`stop` 唤醒。"""
        if not self.available:
            logger.warning("托盘不可用，程序继续在后台运行：%s", self.actions["dashboard_url"]())
            self._shutdown.wait()
            return
        icon = self._build_icon()
        self._icon = icon
        icon.run()

    def stop(self) -> None:
        self._shutdown.set()
        icon = self._icon
        if icon is not None:
            try:
                icon.stop()  # type: ignore[attr-defined]
            except Exception:  # pragma: no cover - 托盘已被系统回收
                logger.debug("托盘停止时抛出异常，忽略")

    def set_paused(self, paused: bool) -> None:
        self._paused = paused
        icon = self._icon
        if icon is None:
            return
        icon.icon = load_icon_image(self._asset, paused=paused)  # type: ignore[attr-defined]
        icon.title = self._title()  # type: ignore[attr-defined]
        icon.update_menu()  # type: ignore[attr-defined]

    @property
    def paused(self) -> bool:
        return self._paused

    # ── 菜单 ────────────────────────────────────────────────────────────
    def _build_icon(self):
        import pystray

        menu = pystray.Menu(
            pystray.MenuItem("打开 OmniSight", self._open_dashboard, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "暂停记录",
                self._toggle_pause,
                checked=lambda _item: self._paused,
                enabled=self.actions["on_toggle_pause"] is not None,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "开机自启",
                self._toggle_autostart,
                checked=lambda _item: self._autostart_checked(),
                enabled=self.actions["on_toggle_autostart"] is not None,
            ),
            pystray.MenuItem(
                "打开数据目录",
                self._open_data_dir,
                enabled=self.actions["open_data_dir"] is not None,
            ),
            pystray.MenuItem(
                "打开日志目录",
                self._open_logs_dir,
                enabled=self.actions["open_logs_dir"] is not None,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "关于与隐私说明",
                self._about,
                enabled=self.actions["on_about"] is not None,
            ),
            pystray.MenuItem("退出", self._quit),
        )
        return pystray.Icon(
            "OmniSight",
            icon=load_icon_image(self._asset, paused=self._paused),
            title=self._title(),
            menu=menu,
        )

    def _title(self) -> str:
        """悬浮提示。暂停时必须能看出来——图标灰度在某些主题下不明显。"""
        return "OmniSight（记录已暂停）" if self._paused else "OmniSight"

    def _autostart_checked(self) -> bool:
        getter = self.actions["autostart_state"]
        if getter is None:
            return False
        try:
            return bool(getter())
        except Exception:
            logger.exception("读取开机自启状态失败")
            return False

    # ── 回调 ────────────────────────────────────────────────────────────
    def _open_dashboard(self, *_args: object) -> None:
        webbrowser.open(self.actions["dashboard_url"]())

    def _toggle_autostart(self, icon, _item) -> None:
        toggle = self.actions["on_toggle_autostart"]
        if toggle is None:
            return
        try:
            toggle(not self._autostart_checked())
        except Exception:
            logger.exception("切换开机自启失败")
        icon.update_menu()

    def _toggle_pause(self, icon, _item) -> None:
        """暂停/恢复。**先让服务层真的改状态，再按结果更新图标**。

        反过来做（先改 UI 再调服务）会在服务抛错时留下一个撒谎的托盘：图标是灰的、
        记录还在继续。这正是 08 文档 §5 那条"暂停必须是真的暂停"最容易破的地方。
        """
        toggle = self.actions["on_toggle_pause"]
        if toggle is None:
            return
        wanted = not self._paused
        try:
            toggle(wanted)
        except Exception:
            logger.exception("切换暂停状态失败")
            return
        self.set_paused(wanted)
        icon.update_menu()

    def _open_data_dir(self, *_args: object) -> None:
        opener = self.actions["open_data_dir"]
        if opener is not None:
            opener()

    def _open_logs_dir(self, *_args: object) -> None:
        opener = self.actions["open_logs_dir"]
        if opener is not None:
            opener()

    def _about(self, *_args: object) -> None:
        handler = self.actions["on_about"]
        if handler is not None:
            handler()

    def _quit(self, *_args: object) -> None:
        self.actions["on_quit"]()
