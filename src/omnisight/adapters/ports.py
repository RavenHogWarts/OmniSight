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
#: ``info`` 是 M3 加的：图标不可用这类"知道就行"的说明既不该上全局横幅，也不该
#: 被当成警告——前端只把 ``error`` 做成横幅，其余进设置页的能力说明。适配器里
#: 已经在用 ``info``（windows/factory.py 的 icons_unavailable），类型跟上实际。
Severity = Literal["error", "warning", "info"]

#: 未知前台（空闲、锁屏、被排除的应用）时按键的归属，见 README 命名约定。
UNKNOWN_APP_ID = 0


class UnsupportedOperation(RuntimeError):
    """当前环境不具备该能力。调用方应查 :class:`Capabilities` 以避免触发。"""


class CaptureUnavailable(RuntimeError):
    """采集后端无法启动。**不应导致整个程序退出**（10 文档 §6）。"""


@dataclass(frozen=True, slots=True)
class AdapterOptions:
    """装配适配器时需要的少量用户意图。

    刻意**不**直接传 ``Config``：适配器不该认识配置文件的结构，否则配置每加一个字段
    都可能悄悄成为某个平台实现的依赖。这里只列适配器真正需要知道的三件事。
    """

    #: ``auto`` | ``raw_input`` | ``pynput`` | ``none``。显式指定时不静默降级。
    keyboard_backend: str = "auto"
    #: 为假时适配器根本不返回窗口标题（08 文档 §2.1，默认关闭）。
    record_window_titles: bool = False
    #: 平台的会话结束信号（Windows 的 ``WM_ENDSESSION``）应当调用它。
    #: 关机/注销时若没有这条路径，当前前台会话与队列里的事件会一起丢掉。
    on_session_end: Callable[[], None] | None = None


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
class ElevatedAutostartControl(Protocol):
    """开机自启，但以管理员身份（Windows 的 ``/RL HIGHEST`` 登录任务，10 文档 §5.3）。

    刻意**不**做成 :class:`AutostartControl` 的一个参数：两者是两套机制（注册表项 vs
    计划任务），改动所需的权限不同（前者只写 ``HKCU``，后者建任务就要管理员），而且
    **互斥**——同时开着会在登录时启动两个实例。互斥由服务层维护，因为只有那一层同时
    看得到两个端口。

    :meth:`change_blocked_reason` 返回的是**给用户看的一句话**，而不是一个布尔值：这个
    开关不可用的三种理由（开发模式、程序在可写目录、当前没提权）对应三种完全不同的下一
    步动作，只给一个灰开关等于让用户猜（05 文档 §7）。
    """

    def is_enabled(self) -> bool:
        """任务存在、指向当前程序**且**真的会提权。"""

    def is_present(self) -> bool:
        """任务存在，但可能指向旧路径或没有提权。用于把"看起来是关的"说清楚。"""

    def change_blocked_reason(self) -> str:
        """此刻不能改这个开关的原因；``""`` = 可以改。"""

    def set_enabled(self, enabled: bool) -> None:
        """建立或删除登录任务。被闸门挡住时抛 :class:`PermissionError`。"""


@runtime_checkable
class ElevationControl(Protocol):
    """管理员（提权）运行模式（10 文档 §5.2）。

    存在的理由是一条平台事实：普通权限的进程收不到发往更高权限进程的键盘输入，
    于是"以管理员身份运行的编辑器里敲的键一个都没统计到"这种缺口只能靠**把自己也
    提权**来补。三个平台的做法完全不同（Windows 是 UAC + ``ShellExecuteEx "runas"``，
    macOS 是授权框，Linux 是 ``pkexec``），而调用方只需要状态与一个动作。

    它**不进** :class:`Capabilities`：那份数据回答的是"能采集到什么"，而权限层级是
    "此刻以什么身份在跑"。更要紧的是不能把"没提权"做成一条 :class:`DegradedNotice`
    ——普通权限是推荐状态，把它标成降级等于催促每一个用户给一个记录键盘的程序更多
    权限（08 文档 §8 的立场正相反）。
    """

    def is_elevated(self) -> bool:
        """当前进程是否以管理员 / root 身份运行。"""

    def can_elevate(self) -> bool:
        """能否**以同一个账户**提权。

        False 有两种成因：已经提过了，或者当前账户根本不是管理员——后者提权会切换到
        另一个账户，数据目录随之改变。调用方应据此禁掉入口，而不是让用户踩进去。
        """

    def relaunch_elevated(self) -> bool:
        """请求以管理员身份重启。

        True 表示新进程已在启动，调用方**必须**随即停机（否则两个实例同时抢锁）；
        False 表示用户取消或系统拒绝，当前进程照常继续运行。
        """

    def open_unelevated(self, target: str) -> bool:
        """以普通权限打开 URL 或目录；没能降权时返回 False，由调用方兜底。

        提权进程的子进程默认继承管理员令牌，直接打开浏览器等于交给它一份管理员权限。
        """


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
    #: 以管理员身份的开机自启（Windows 的登录计划任务）。``None`` = 本平台没有这条机制，
    #: 设置页据此不显示那一项。
    autostart_elevated: ElevatedAutostartControl | None = None
    #: 管理员模式（Windows 的 UAC）。``None`` = 本平台还没有实现，托盘据此隐藏那一项。
    elevation: ElevationControl | None = None
    foreground: ForegroundSource | None = None
    keyboard: KeyboardSource | None = None
    idle: IdleSource | None = None
    icons: IconSource | None = None
    tray_factory: Callable[..., object] | None = None
    extra: dict[str, object] = field(default_factory=dict)
