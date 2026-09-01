"""平台端口契约：核心层与操作系统之间唯一的接口（13 文档 §5）。

三条不可违反的规则：

1. **核心层只依赖本文件。** 任何 ``import win32gui`` / ``import Quartz`` /
   ``import Xlib`` 都只能出现在 ``adapters/<platform>/`` 里。
2. **能力探测，不做平台判断。** 需要"做不做某件事"时查 :class:`Capabilities`，
   不查平台名。唯一知道自己在哪个平台的函数是 ``adapters.detect()``。
3. **降级必须可见。** 任何缺失的能力都要产出一条 :class:`DegradedNotice`，
   它会同时出现在 ``/api/v1/status``、托盘提示与仪表盘横幅上。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal, Protocol, runtime_checkable

PlatformId = Literal["windows", "macos", "linux_x11", "linux_wayland", "generic"]
IdentityKind = Literal["process", "bundle", "desktop", "wm_class"]
Severity = Literal["error", "warning"]

#: 未知前台（空闲、锁屏、被排除的应用）时按键的归属，见 README 命名约定。
UNKNOWN_APP_ID = 0


class UnsupportedOperation(RuntimeError):
    """当前环境不具备该能力。调用方应查 :class:`Capabilities` 以避免触发。"""


class CaptureUnavailable(RuntimeError):
    """采集后端无法启动。**不应导致整个程序退出**（10 文档 §6）。"""


@dataclass(frozen=True, slots=True)
class AppIdentity:
    """应用身份。``app_key`` 的语义由 ``identity_kind`` 决定（03 文档 §2.2）。"""

    app_key: str
    identity_kind: IdentityKind
    display_name: str
    process_name: str = ""
    exe_path: str = ""


@dataclass(frozen=True, slots=True)
class ForegroundInfo:
    """一次前台窗口探测的结果。除前两个字段外都允许为空（04 文档 §2.1）。"""

    identity: AppIdentity
    window_title: str = ""


@dataclass(frozen=True, slots=True)
class RawKeyEvent:
    """已归一化到 ``key_id`` 的单次按下或抬起。

    ``key_id`` 是标准，原生码是输入（04 文档 §3.2）：适配器负责
    ``native → HID → key_id`` 的映射，核心层永远看不到原生码的语义。
    ``native_code`` 等字段仅作诊断与重放之用。
    """

    key_id: str
    pressed: bool
    wall_ts_ns: int
    mono_ts_ns: int
    hid_usage: int | None = None
    native_code: int | None = None
    native_code2: int | None = None


@dataclass(frozen=True, slots=True)
class DegradedNotice:
    """一条对用户可见的能力缺失说明（05 文档 §7）。

    文案必须同时讲清三件事：缺什么、什么仍然正常、怎么解决（或无法解决）。
    """

    code: str
    severity: Severity
    title: str
    detail: str
    hint: str | None = None
    docs: str | None = None


@dataclass(frozen=True, slots=True)
class Capabilities:
    """当前环境**能采集到什么**。装配、API、UI、数据可解释性四处共用同一份。"""

    platform_id: PlatformId
    tier: int
    os_version: str = ""
    keyboard: bool = False
    keyboard_backend: str = "none"
    keyboard_durations: bool = False
    #: key_id 是否基于物理位置。False 时热力图不可区分左右修饰键，UI 必须明示。
    key_position_stable: bool = False
    #: 应用归因是否可用 ← 决定合并的核心价值能否交付。
    foreground: bool = False
    window_titles: bool = False
    idle: bool = False
    icons: bool = False
    autostart: bool = False
    tray: bool = False
    permissions_required: tuple[str, ...] = ()
    permissions_granted: tuple[str, ...] = ()
    setup_hint: str | None = None
    degraded: tuple[DegradedNotice, ...] = ()

    @property
    def supported(self) -> bool:
        return self.tier > 0

    def to_dict(self) -> dict[str, object]:
        """``/api/v1/status`` 的 ``capabilities`` 段（不含 platform 与 degraded）。"""
        return {
            "keyboard": self.keyboard,
            "keyboard_backend": self.keyboard_backend,
            "keyboard_durations": self.keyboard_durations,
            "key_position_stable": self.key_position_stable,
            "foreground": self.foreground,
            "window_titles": self.window_titles,
            "idle": self.idle,
            "icons": self.icons,
            "autostart": self.autostart,
            "tray": self.tray,
            "permissions_required": list(self.permissions_required),
            "permissions_granted": list(self.permissions_granted),
            "setup_hint": self.setup_hint,
        }


@runtime_checkable
class ForegroundSource(Protocol):
    """识别用户此刻正在使用的应用。"""

    def current(self) -> ForegroundInfo | None:
        """返回当前前台应用；不可用或被过滤时返回 ``None``。"""

    def list_running(self) -> list[AppIdentity]:
        """拥有可见窗口的应用，供应用选择器使用。"""


@runtime_checkable
class KeyboardSource(Protocol):
    """投递全局按键事件，能力以操作系统允许的为限。

    端口**不承诺回调线程的归属**：Windows 由适配器自己的消息泵驱动，macOS 的
    event tap 必须挂在主线程 runloop 上。装配层据 :attr:`needs_main_loop`
    决定托盘是否让出主线程（02 文档 §3）。
    """

    def start(self, sink: Callable[[RawKeyEvent], None]) -> None:
        """开始投递。失败时抛 :class:`CaptureUnavailable`。"""

    def stop(self) -> None: ...

    @property
    def running(self) -> bool: ...

    @property
    def backend_name(self) -> str: ...

    @property
    def needs_main_loop(self) -> bool:
        """True 表示调用方必须在主线程驱动一个 runloop。"""


@runtime_checkable
class IdleSource(Protocol):
    def idle_seconds(self) -> float: ...


@runtime_checkable
class IconSource(Protocol):
    def icon_png(self, identity: AppIdentity, size: int) -> bytes | None: ...


@runtime_checkable
class AutostartControl(Protocol):
    def is_enabled(self) -> bool:
        """自启项存在**且**指向当前程序（10 文档 §4）。"""

    def set_enabled(self, enabled: bool) -> None: ...


@runtime_checkable
class InstanceLock(Protocol):
    def acquire(self) -> bool: ...

    def notify_existing(self) -> bool:
        """把已运行的实例带到前台；不支持时返回 False。"""

    def release(self) -> None: ...


@runtime_checkable
class Notifier(Protocol):
    """启动期错误告知。兜底实现写日志 + stderr + STARTUP_ERROR.txt（10 文档 §6）。"""

    def error(self, title: str, message: str) -> None: ...


@dataclass(frozen=True, slots=True)
class AdapterSet:
    """一个平台的全部实现。能力缺失的端口为 ``None``，装配处据此跳过。"""

    capabilities: Capabilities
    instance_lock: InstanceLock
    notifier: Notifier
    autostart: AutostartControl | None = None
    foreground: ForegroundSource | None = None
    keyboard: KeyboardSource | None = None
    idle: IdleSource | None = None
    icons: IconSource | None = None
    tray_factory: Callable[..., object] | None = None
    extra: dict[str, object] = field(default_factory=dict)
