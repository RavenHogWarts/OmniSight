"""Raw Input 的纯 ctypes 层（← KeyTrace ``raw_input.py``，原样迁移）。

**这份代码已经在 KeyTrace 上验证过，不重写。** 04 文档 §3.1 明确要求原样搬来：
``RegisterRawInputDevices`` + 消息窗口 + ``WNDPROC`` 的细节很容易写错，而它已经
处理妥当。本文件只做纯解码，不认识 ``key_id``——归一化在
:mod:`~omnisight.adapters.windows.keymap_native` 里，那一层是纯函数、可表驱动测试。

相对 KeyTrace 的两处改动，都有明确理由：

1. **删掉了 ``normalize_raw_key``。** 它做的四件事（左右 Shift 靠扫描码、左右
   Ctrl/Alt 靠扩展位、小键盘导航簇靠 ``NUMPAD_BY_SCAN``、小键盘回车靠扩展位）在
   改用 ``(扫描码, E0)`` 作为映射键之后全部自然成立，见 ``keymap_native`` 的模块注释。
2. **窗口从 ``HWND_MESSAGE`` 改为未显示的顶层窗口。** 纯消息窗口收不到
   ``WM_ENDSESSION`` 这类广播，于是注销/关机时程序被直接杀掉、当前前台会话丢失。
   改为顶层窗口（创建后从不 ``ShowWindow``，因此不出现在任务栏与 Alt+Tab）后，
   关机能走正常停机路径。这是 M0 遗留限制的解法。

``RIDEV_INPUTSINK`` 是关键标志：它让窗口在**没有焦点时**也能收到输入，这才是
"全屏独占游戏里的按键也能统计"的根据。
"""

from __future__ import annotations

import ctypes
import logging
import os
import threading
from collections.abc import Callable
from ctypes import wintypes
from typing import ClassVar

logger = logging.getLogger(__name__)

WM_INPUT = 0x00FF
WM_QUIT = 0x0012
WM_CLOSE = 0x0010
WM_DESTROY = 0x0002
WM_QUERYENDSESSION = 0x0011
WM_ENDSESSION = 0x0016
RID_INPUT = 0x10000003
RIM_TYPEKEYBOARD = 1
RIDEV_INPUTSINK = 0x00000100
RI_KEY_BREAK = 0x0001

#: ``(vk, scan, flags, is_down)``——刻意保持与 KeyTrace 相同的回调形状。
RawCallback = Callable[[int, int, int, bool], None]

ULONG_PTR = wintypes.WPARAM
LRESULT = wintypes.LPARAM
WNDPROC = ctypes.WINFUNCTYPE(
    LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
)


class RAWINPUTDEVICE(ctypes.Structure):
    _fields_: ClassVar = [
        ("usUsagePage", wintypes.USHORT),
        ("usUsage", wintypes.USHORT),
        ("dwFlags", wintypes.DWORD),
        ("hwndTarget", wintypes.HWND),
    ]


class RAWINPUTHEADER(ctypes.Structure):
    _fields_: ClassVar = [
        ("dwType", wintypes.DWORD),
        ("dwSize", wintypes.DWORD),
        ("hDevice", wintypes.HANDLE),
        ("wParam", ULONG_PTR),
    ]


class RAWKEYBOARD(ctypes.Structure):
    _fields_: ClassVar = [
        ("MakeCode", wintypes.USHORT),
        ("Flags", wintypes.USHORT),
        ("Reserved", wintypes.USHORT),
        ("VKey", wintypes.USHORT),
        ("Message", wintypes.UINT),
        ("ExtraInformation", wintypes.ULONG),
    ]


class RAWINPUT(ctypes.Structure):
    _fields_: ClassVar = [("header", RAWINPUTHEADER), ("keyboard", RAWKEYBOARD)]


class WNDCLASSW(ctypes.Structure):
    _fields_: ClassVar = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]

def _configure_win32() -> tuple[ctypes.WinDLL, ctypes.WinDLL]:
    """写好这一批函数原型，并**把配置好的那两个对象交回调用方**。

    交回去不是顺手，是唯一正确的做法：``ctypes.windll.user32`` 的缓存**不是原子的**
    （``LibraryLoader.__getattr__`` 就是"没缓存就新建一个、再 setattr"），因此两个线程同时
    第一次取它会各拿到一个**不同的** WinDLL 对象——本机实测 200 次并发里 188 次如此。原型
    只写在其中一个身上，而进了缓存的是谁的 setattr 落在后面。

    代价是整整一次运行不记任何按键：消息泵拿到一个身上什么都没有的 user32，而
    ``CreateWindowExW`` 的 hInstance 是 64 位模块基址——没有 argtypes 就按 C int 转，于是
    ``argument 11: OverflowError: int too long to convert``，Raw Input 注册失败，日志里是
    ``keyboard=False / backend=none``（2026-09-06 01:07:53 现场：前台监控在 2 毫秒前刚启动，
    而它每秒都要取一次同一个 ``ctypes.windll.user32``）。ASLR 让模块基址有一半机会低于
    2^31，那种时候同一个 bug 什么事都不会发生——这就是它看起来"偶发"的原因。

    所以这两个句柄干脆是**私有的**（``ctypes.WinDLL(...)`` 每次都新建一个，与共享缓存无关，
    也就没人能改到它们身上的原型）——``elevation``、``icons``、``single_instance`` 三个邻居
    本来就是这么写的。不加 ``use_last_error``：本模块用 ``ctypes.WinError()`` 读错误码，而那
    个参数会让 ctypes 接管 ``GetLastError``，于是 ``WinError()`` 读到的就不是 API 留下的那个了。

    因此本模块里除了这个函数，**任何地方都不许再去 ``ctypes.windll`` 取**：拿到的引用要么
    从这里的返回值来，要么从 :attr:`RawInputKeyboardListener._user32` 来。
    """
    user32 = ctypes.WinDLL("user32")
    kernel32 = ctypes.WinDLL("kernel32")
    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    kernel32.GetModuleHandleW.restype = wintypes.HMODULE
    kernel32.GetCurrentThreadId.argtypes = []
    kernel32.GetCurrentThreadId.restype = wintypes.DWORD
    user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
    user32.RegisterClassW.restype = wintypes.ATOM
    user32.CreateWindowExW.argtypes = [
        wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.HWND, wintypes.HANDLE, wintypes.HINSTANCE, wintypes.LPVOID,
    ]
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.DefWindowProcW.argtypes = [
        wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
    ]
    user32.DefWindowProcW.restype = LRESULT
    user32.RegisterRawInputDevices.argtypes = [
        ctypes.POINTER(RAWINPUTDEVICE), wintypes.UINT, wintypes.UINT
    ]
    user32.RegisterRawInputDevices.restype = wintypes.BOOL
    user32.GetRawInputData.argtypes = [
        wintypes.HANDLE, wintypes.UINT, wintypes.LPVOID,
        ctypes.POINTER(wintypes.UINT), wintypes.UINT,
    ]
    user32.GetRawInputData.restype = wintypes.UINT
    user32.GetMessageW.argtypes = [
        ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT
    ]
    user32.GetMessageW.restype = wintypes.BOOL
    user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user32.DispatchMessageW.restype = LRESULT
    user32.PostThreadMessageW.argtypes = [
        wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
    ]
    user32.PostThreadMessageW.restype = wintypes.BOOL
    user32.DestroyWindow.argtypes = [wintypes.HWND]
    user32.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HINSTANCE]
    return user32, kernel32


def _release_window(
    user32: object,
    hwnd: int | None,
    atom: int,
    class_name: str,
    instance: int | None,
) -> None:
    """收掉消息窗口与那个窗口类。**尽力而为：一律不抛。**

    这几行与进程退出赛跑：``stop()`` 只 join 3 秒，而 ``WM_ENDSESSION`` 那条路压根不 join
    （它就跑在这个线程上）。解释器一旦开始收尾，``ctypes`` 上那些 argtypes 就可能已经不在
    了，而**没有原型的默认转换按 C int 走**——``GetModuleHandleW`` 给回的模块基址被 ASLR
    有一半的机会推到 2^31 以上，于是抛
    ``ArgumentError: argument 2: OverflowError: int too long to convert``。
    它发生在守护线程上，最后变成用户手里一份看不出所以然的崩溃报告（2026-09-06 现场四份
    崩溃报告全是这一条，而当时程序其实已经在正常停机了）。

    因此两件事一起做：**每个参数自带 ctypes 类型**（不指望 argtypes 还在），以及**任何失败
    只记 debug**。窗口与窗口类都由内核在进程退出时收走，这里失败没有后果——而一份崩溃报告
    有后果。
    """
    try:
        if hwnd:
            user32.DestroyWindow(wintypes.HWND(hwnd))
        if atom and instance:
            user32.UnregisterClassW(
                ctypes.c_wchar_p(class_name), wintypes.HINSTANCE(instance)
            )
    except Exception:  # 收尾阶段的失败没有后果，更不该变成一份崩溃报告
        logger.debug("Raw Input 窗口清理未完成（进程可能正在退出）", exc_info=True)


class RawInputKeyboardListener:
    """接收键盘 Raw Input，含全屏独占程序内的输入。

    ``on_session_end`` 在注销/关机时被调用（在消息泵线程上）。它必须很快返回——
    系统只给几秒，超时会强杀进程。
    """

    def __init__(
        self, callback: RawCallback, *, on_session_end: Callable[[], None] | None = None
    ) -> None:
        self.callback = callback
        self.on_session_end = on_session_end
        self._thread: threading.Thread | None = None
        self._thread_id = 0
        self._ready = threading.Event()
        self._error: BaseException | None = None
        self._wnd_proc: WNDPROC | None = None
        #: :func:`_configure_win32` 配置过的那个 user32。**全模块共用这一个引用**，
        #: 谁都不许再去 ``ctypes.windll.user32`` 取一次（理由见那个函数的说明）。
        self._user32: ctypes.WinDLL | None = None

    @property
    def running(self) -> bool:
        return bool(
            self._thread and self._thread.is_alive() and self._ready.is_set() and not self._error
        )

    def start(self) -> None:
        if os.name != "nt":  # pragma: no cover - 由能力探测保证不会走到
            raise RuntimeError("Raw Input 仅支持 Windows")
        if self.running:
            return
        self._ready.clear()
        self._error = None
        self._thread = threading.Thread(
            target=self._run, name="omnisight-raw-input", daemon=True
        )
        self._thread.start()
        if not self._ready.wait(timeout=3):
            raise RuntimeError("Raw Input 监听器启动超时")
        if self._error:
            raise RuntimeError(f"Raw Input 监听器启动失败：{self._error}") from self._error

    def stop(self) -> None:
        user32 = self._user32
        if os.name == "nt" and self._thread_id and user32 is not None:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        # 停机可能由消息泵线程自己触发（WM_ENDSESSION），此时 join 自己会死锁。
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=3)
            self._thread = None
        self._thread_id = 0
        self._ready.clear()

    def _run(self) -> None:
        user32, kernel32 = _configure_win32()
        self._user32 = user32
        self._thread_id = kernel32.GetCurrentThreadId()
        class_name = f"OmniSightRawInput_{os.getpid()}_{self._thread_id}"
        hwnd = None
        atom = 0
        instance = None
        try:
            self._wnd_proc = WNDPROC(self._window_proc)
            instance = kernel32.GetModuleHandleW(None)
            window_class = WNDCLASSW()
            window_class.lpfnWndProc = self._wnd_proc
            window_class.hInstance = instance
            window_class.lpszClassName = class_name
            atom = user32.RegisterClassW(ctypes.byref(window_class))
            if not atom:
                raise ctypes.WinError()
            # 顶层窗口但从不 ShowWindow：既能收到 WM_ENDSESSION，又不出现在界面上。
            hwnd = user32.CreateWindowExW(
                0, class_name, "OmniSight", 0, 0, 0, 0, 0, None, None, instance, None
            )
            if not hwnd:
                raise ctypes.WinError()
            device = RAWINPUTDEVICE(0x01, 0x06, RIDEV_INPUTSINK, hwnd)
            if not user32.RegisterRawInputDevices(
                ctypes.byref(device), 1, ctypes.sizeof(device)
            ):
                raise ctypes.WinError()
            self._ready.set()
            message = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(message))
                user32.DispatchMessageW(ctypes.byref(message))
        except BaseException as exc:
            self._error = exc
            self._ready.set()
        finally:
            _release_window(user32, hwnd, atom, class_name, instance)

    def _window_proc(self, hwnd, message, w_param, l_param):
        if message == WM_INPUT:
            self._read_keyboard(l_param)
            return 0
        if message == WM_QUERYENDSESSION:
            # 返回 TRUE 表示"我不阻止关机"。真正的清理在 WM_ENDSESSION 里做。
            return 1
        if message == WM_ENDSESSION:
            if w_param and self.on_session_end is not None:
                logger.info("收到 WM_ENDSESSION，开始停机")
                try:
                    self.on_session_end()
                except Exception:
                    logger.exception("关机回调失败")
            return 0
        user32 = self._user32
        if message in (WM_CLOSE, WM_DESTROY):
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, message, w_param, l_param)

    def _read_keyboard(self, raw_handle: int) -> None:
        size = wintypes.UINT(0)
        header_size = ctypes.sizeof(RAWINPUTHEADER)
        user32 = self._user32
        if (
            user32.GetRawInputData(raw_handle, RID_INPUT, None, ctypes.byref(size), header_size)
            == 0xFFFFFFFF
        ):
            return
        buffer = ctypes.create_string_buffer(size.value)
        if (
            user32.GetRawInputData(raw_handle, RID_INPUT, buffer, ctypes.byref(size), header_size)
            == 0xFFFFFFFF
        ):
            return
        raw = ctypes.cast(buffer, ctypes.POINTER(RAWINPUT)).contents
        if raw.header.dwType != RIM_TYPEKEYBOARD:
            return
        keyboard = raw.keyboard
        # 0 与 0xFF 是"没有对应虚拟键"的占位，不是按键。
        if keyboard.VKey in {0, 0xFF}:
            return
        self.callback(
            int(keyboard.VKey),
            int(keyboard.MakeCode),
            int(keyboard.Flags),
            not bool(keyboard.Flags & RI_KEY_BREAK),
        )
