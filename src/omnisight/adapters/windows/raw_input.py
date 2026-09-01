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

def _configure_win32() -> None:
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
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
        if os.name == "nt" and self._thread_id:
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        # 停机可能由消息泵线程自己触发（WM_ENDSESSION），此时 join 自己会死锁。
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=3)
            self._thread = None
        self._thread_id = 0
        self._ready.clear()

    def _run(self) -> None:
        _configure_win32()
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        self._thread_id = kernel32.GetCurrentThreadId()
        class_name = f"OmniSightRawInput_{os.getpid()}_{self._thread_id}"
        hwnd = None
        atom = 0
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
            if hwnd:
                user32.DestroyWindow(hwnd)
            if atom:
                user32.UnregisterClassW(class_name, kernel32.GetModuleHandleW(None))

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
        if message in (WM_CLOSE, WM_DESTROY):
            ctypes.windll.user32.PostQuitMessage(0)
            return 0
        return ctypes.windll.user32.DefWindowProcW(hwnd, message, w_param, l_param)

    def _read_keyboard(self, raw_handle: int) -> None:
        size = wintypes.UINT(0)
        header_size = ctypes.sizeof(RAWINPUTHEADER)
        user32 = ctypes.windll.user32
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
