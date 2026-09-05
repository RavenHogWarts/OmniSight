"""托盘图标与菜单。

两处沿用旧实现里正确的做法、一处是新增的必需能力：

* 沿用 KeyTrace 的 ``icon.update_menu()``（TimeLens 是重建 ``icon.menu``，
  前者才是 pystray 的正确用法）。
* 沿用"图标资源缺失就用生成的纯色图标兜底"，不让一个 PNG 拖垮启动。
* 新增：**托盘不可用时的无托盘运行路径**。托盘是唯一退出入口的设计会让任何一次
  失败都变成"进程杀不掉"的投诉（10 文档 §5.1）。

菜单项按 10 文档 §5 的清单，M6 补齐其中三项，18 文档 批 4 又重排了一次：

```
打开 OmniSight            （默认项，双击图标）
打开设置                  （18 批 4 新增 → /settings?token=）
─────────────
暂停记录                  （勾选态，对应 capture.paused）
重新启动                  （18 批 5 新增）
以管理员身份重启          （文字随状态变，不是勾选框）
─────────────
打开数据目录
打开日志目录
退出
```

**这一版删掉了两项，各有去处**（18 文档 批 4）：

* **开机自启** → 设置页「系统」段。它的真源是操作系统（注册表项 / 登录计划任务），而
  Windows 上有两条互斥的机制——托盘那个勾选框只能显示两者的并集，说不出是哪一条开着，
  也说不出为什么另一条改不了。10 文档 §5.3 早就把"持久化提权那个决定"放在设置页，这一步
  只是让普通那一条跟过去。
* **关于与隐私说明** → `/about` 那一页。它原先只能重新打开首启那个模态；现在它有地址，
  托盘少一项，而"随时找得到"这条要求（08 文档 §6.1）反而更硬。

留下的两个目录入口不动：**页面打不开的时候，它们是用户拿到材料的唯一一键路径**，而那正是
托盘存在的场景（10 文档 §5.1）。

**暂停记录**（勾选态）：08 文档 §5 要求的一键停止。需要暂停的时候用户往往不想先开浏览器，
托盘是它唯一合理的位置；图标同时切成灰度，让"还在记录吗"在托盘上直接有答案。

**重新启动**与**以管理员身份重启**（10 文档 §5.2）并排：两者回答同一个问题"要不要换一个
进程接着记"，只是后者顺带换权限。两项都刻意**不做成勾选框**——重启不是一个状态，而提权
勾不掉（勾不掉的勾选框是在说谎）。
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from pathlib import Path

from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)

ICON_SIZE = 64
ACCENT = (47, 141, 251, 255)
MUTED = (140, 140, 148, 255)

#: 管理员模式那一项在三种状态下的文字。三种状态由装配层给出（见
#: ``omnisight.core.lifecycle._elevation_state``），托盘只负责把它翻译成一行字：
#:
#: * ``elevated``——已经在管理员模式里跑。写"本次"是因为它确实只对本次运行有效：
#:   下次启动回到普通权限（10 文档 §5.2）。
#: * ``available``——可以提权（管理员账户的受限令牌），点一下弹 UAC 确认框。
#: * ``unavailable``——当前账户不是管理员。提权会切换到**另一个账户**，数据目录随之
#:   改变，所以这一项是灰的，且必须在文字里说明原因——一个没有解释的灰按钮只会
#:   带来"为什么点不了"。
ELEVATION_LABELS = {
    "elevated": "本次已在管理员模式运行",
    "available": "以管理员身份重启",
    "unavailable": "以管理员身份重启（需要管理员账户）",
}


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
        open_dashboard: Callable[[], None],
        on_quit: Callable[[], None],
        open_settings: Callable[[], None] | None = None,
        paused_state: Callable[[], bool] | None = None,
        on_toggle_pause: Callable[[bool], None] | None = None,
        on_restart: Callable[[], None] | None = None,
        elevation_state: Callable[[], str] | None = None,
        on_elevate: Callable[[], None] | None = None,
        open_data_dir: Callable[[], None] | None = None,
        open_logs_dir: Callable[[], None] | None = None,
        asset: Path | None = None,
        available: bool = True,
    ) -> None:
        self.actions = {
            "dashboard_url": dashboard_url,
            "open_dashboard": open_dashboard,
            "on_quit": on_quit,
            "open_settings": open_settings,
            "paused_state": paused_state,
            "on_toggle_pause": on_toggle_pause,
            "on_restart": on_restart,
            "elevation_state": elevation_state,
            "on_elevate": on_elevate,
            "open_data_dir": open_data_dir,
            "open_logs_dir": open_logs_dir,
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
            pystray.MenuItem(
                "打开设置",
                self._open_settings,
                enabled=self.actions["open_settings"] is not None,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "暂停记录",
                self._toggle_pause,
                checked=lambda _item: self._paused,
                enabled=self.actions["on_toggle_pause"] is not None,
            ),
            pystray.MenuItem(
                "重新启动",
                self._restart,
                enabled=self.actions["on_restart"] is not None,
            ),
            pystray.MenuItem(
                # 文字随状态变，因此传的是可调用对象而不是字符串（pystray 支持）。
                self._elevation_label,
                self._elevate,
                # 只有"能提权"时可点。已经是管理员就无事可做；标准用户账户点下去会提权
                # 成另一个账户，数据目录随之改变——那不是用户要的东西。
                enabled=lambda _item: self._elevation_state() == "available",
                # 端口不存在的平台（macOS / Linux 尚未实现）干脆不显示这一项：一个永远
                # 灰着的菜单项只会带来"为什么点不了"。
                visible=self.actions["on_elevate"] is not None,
            ),
            pystray.Menu.SEPARATOR,
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
            pystray.MenuItem("退出", self._quit),
        )
        return pystray.Icon(
            "OmniSight",
            icon=load_icon_image(self._asset, paused=self._paused),
            title=self._title(),
            menu=menu,
        )

    def _title(self) -> str:
        """悬浮提示。两件事必须能看出来：记录停了没有、是不是管理员模式。

        暂停时图标虽然会变灰，但灰度在某些主题下不明显；而"我这个记录键盘的程序正以
        管理员权限跑着"更是应当能随时看见，托盘提示是它唯一的常驻位置。
        """
        marks = []
        if self._paused:
            marks.append("记录已暂停")
        if self._elevation_state() == "elevated":
            marks.append("管理员模式")
        return f"OmniSight（{' · '.join(marks)}）" if marks else "OmniSight"

    def _elevation_state(self) -> str:
        """``elevated`` | ``available`` | ``unavailable``。读不到就按最保守的一档。"""
        getter = self.actions["elevation_state"]
        if getter is None:
            return "unavailable"
        try:
            state = str(getter())
        except Exception:
            logger.exception("读取管理员模式状态失败")
            return "unavailable"
        return state if state in ELEVATION_LABELS else "unavailable"

    def _elevation_label(self, _item: object = None) -> str:
        return ELEVATION_LABELS[self._elevation_state()]

    # ── 回调 ────────────────────────────────────────────────────────────
    def _open_dashboard(self, *_args: object) -> None:
        """怎么打开由装配层决定：管理员模式下要降权，否则浏览器会继承管理员令牌
        （见 ``lifecycle._open_external``）。托盘只负责"用户点了这一项"。
        """
        self.actions["open_dashboard"]()

    def _open_settings(self, *_args: object) -> None:
        """打开设置页。**在浏览器里新开一个标签页**，与「打开 OmniSight」同一条路径
        （怎么打开由装配层决定，管理员模式下要降权）。
        """
        opener = self.actions["open_settings"]
        if opener is not None:
            opener()

    def _restart(self, _icon, _item) -> None:
        """重新启动（18 文档 批 5）。

        成功就意味着**本进程马上要退出了**（装配层确认接班实例活着之后安排停机），因此这里
        不刷新菜单；失败时装配层已经写了日志，而托盘没有说话的地方——设置页那个入口会把
        同一件事说给用户听。
        """
        handler = self.actions["on_restart"]
        if handler is None:
            return
        try:
            handler()
        except Exception:
            logger.exception("重新启动失败")

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

    def _elevate(self, _icon, _item) -> None:
        """以管理员身份重启。

        成功就意味着**本进程马上要退出了**（装配层收到"新实例已在启动"后立即停机），
        因此这里不刷新菜单；用户在 UAC 确认框上点了取消时什么都没变，也没什么可刷。
        """
        handler = self.actions["on_elevate"]
        if handler is None:
            return
        try:
            handler()
        except Exception:
            logger.exception("以管理员身份重启失败")

    def _open_data_dir(self, *_args: object) -> None:
        opener = self.actions["open_data_dir"]
        if opener is not None:
            opener()

    def _open_logs_dir(self, *_args: object) -> None:
        opener = self.actions["open_logs_dir"]
        if opener is not None:
            opener()

    def _quit(self, *_args: object) -> None:
        self.actions["on_quit"]()
