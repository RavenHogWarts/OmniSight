"""Windows 应用图标提取（``IconSource`` 的 Windows 实现，04 文档 §6）。

**只做一件事：给一个应用身份，返回一张 PNG。** 缓存、失败重试、什么时候取，全部在
上层（``AppService.resolve_icon`` + ``app_icon`` 表）。适配器不认识数据库。

与 TimeLens 现状的三处刻意差异：

1. **不扫注册表的 ``Uninstall`` 子树。** 现状在解析失败时枚举 HKLM/HKCU 下数百个卸载
   项去猜图标路径，一次失败要几百毫秒到数秒，而它跑在 Flask 请求线程上（04 文档 §6
   "改动二"点名的问题）。这里的兜底只有两级：``App Paths`` 注册表点查（4 次 OpenKey）
   与 ``PATH`` 查找。真正的解法是**结果被持久化**——``app_icon`` 表加 7 天重试窗口，
   所以偶尔取不到不需要用一次全表扫描去挽救。
2. **保留 alpha 通道。** 现状把图标画到白色画刷填充的 24 位位图上，于是所有透明像素
   变成白色——深色主题下每个图标都带一个白框。这里读 ``GetIconInfo`` 给出的 32 位
   颜色位图，只有在它整片 alpha 为 0（老式图标）时才用掩码位图重建 alpha。
3. **纯 ctypes，不用 pywin32。** ``win32ui`` 的 DC/位图包装是这条路径上唯一用到
   pywin32 的地方；去掉它之后 ``requirements.txt`` 里的 pywin32 只服务托盘与
   Raw Input，替换成本更低（13 文档 §2 的"适配器可整体替换"）。
"""

from __future__ import annotations

import ctypes
import io
import logging
import os
import shutil
import threading
from ctypes import wintypes

from ...adapters.ports import AppIdentity

logger = logging.getLogger(__name__)

#: ``DrawIconEx`` / ``GetDIBits`` 的常量。写在这里而不是散在调用处，便于对照 MSDN。
_BI_RGB = 0
_DIB_RGB_COLORS = 0
_SHGFI_ICON = 0x000000100
_SHGFI_LARGEICON = 0x000000000
_SHGFI_USEFILEATTRIBUTES = 0x000000010

_shell32 = ctypes.WinDLL("shell32", use_last_error=True)
_user32 = ctypes.WinDLL("user32", use_last_error=True)
_gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)


class _ICONINFO(ctypes.Structure):
    _fields_ = (
        ("fIcon", wintypes.BOOL),
        ("xHotspot", wintypes.DWORD),
        ("yHotspot", wintypes.DWORD),
        ("hbmMask", wintypes.HBITMAP),
        ("hbmColor", wintypes.HBITMAP),
    )


class _BITMAP(ctypes.Structure):
    _fields_ = (
        ("bmType", wintypes.LONG),
        ("bmWidth", wintypes.LONG),
        ("bmHeight", wintypes.LONG),
        ("bmWidthBytes", wintypes.LONG),
        ("bmPlanes", wintypes.WORD),
        ("bmBitsPixel", wintypes.WORD),
        ("bmBits", ctypes.c_void_p),
    )


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = (
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    )


class _BITMAPINFO(ctypes.Structure):
    _fields_ = (("bmiHeader", _BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3))


class _SHFILEINFOW(ctypes.Structure):
    _fields_ = (
        ("hIcon", wintypes.HICON),
        ("iIcon", ctypes.c_int),
        ("dwAttributes", wintypes.DWORD),
        ("szDisplayName", ctypes.c_wchar * 260),
        ("szTypeName", ctypes.c_wchar * 80),
    )


def _declare() -> None:
    """给每个函数写出 ``argtypes`` / ``restype``。

    **不写等于把 64 位句柄按 32 位整数传。** ctypes 默认把参数当 ``c_int``，而 x64 上
    ``HBITMAP`` 是 64 位——``GetIconInfo`` 返回的位图句柄有时高位为 0（于是能用），
    有时不为 0（于是 ``OverflowError: int too long to convert``）。这类 bug 按机器、
    按会话随机出现，最容易被"我这儿是好的"掩盖过去。
    """
    _shell32.ExtractIconExW.argtypes = (
        wintypes.LPCWSTR, ctypes.c_int,
        ctypes.POINTER(wintypes.HICON), ctypes.POINTER(wintypes.HICON), wintypes.UINT,
    )
    _shell32.ExtractIconExW.restype = wintypes.UINT
    _shell32.SHGetFileInfoW.argtypes = (
        wintypes.LPCWSTR, wintypes.DWORD,
        ctypes.POINTER(_SHFILEINFOW), wintypes.UINT, wintypes.UINT,
    )
    _shell32.SHGetFileInfoW.restype = ctypes.c_size_t
    _user32.GetIconInfo.argtypes = (wintypes.HICON, ctypes.POINTER(_ICONINFO))
    _user32.GetIconInfo.restype = wintypes.BOOL
    _user32.DestroyIcon.argtypes = (wintypes.HICON,)
    _user32.DestroyIcon.restype = wintypes.BOOL
    _user32.GetDC.argtypes = (wintypes.HWND,)
    _user32.GetDC.restype = wintypes.HDC
    _user32.ReleaseDC.argtypes = (wintypes.HWND, wintypes.HDC)
    _user32.ReleaseDC.restype = ctypes.c_int
    _gdi32.GetObjectW.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p)
    _gdi32.GetObjectW.restype = ctypes.c_int
    _gdi32.GetDIBits.argtypes = (
        wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
        ctypes.c_void_p, ctypes.POINTER(_BITMAPINFO), wintypes.UINT,
    )
    _gdi32.GetDIBits.restype = ctypes.c_int
    _gdi32.DeleteObject.argtypes = (wintypes.HANDLE,)
    _gdi32.DeleteObject.restype = wintypes.BOOL


_declare()


class WindowsIconSource:
    """``IconSource``：进程身份 → PNG 字节。

    进程内带一层**路径解析**缓存（不是图标缓存——图标缓存在 ``app_icon`` 表里）。缓存
    的是"这个进程名对应哪个可执行文件"，包括"查不到"这个结论：否则每次重试都要重新走
    一遍注册表。
    """

    __slots__ = ("_lock", "_paths")

    def __init__(self) -> None:
        self._paths: dict[str, str | None] = {}
        self._lock = threading.Lock()

    def icon_png(self, identity: AppIdentity, size: int) -> bytes | None:
        path = self._resolve_path(identity)
        if not path:
            return None
        handle = _extract_icon(path)
        if not handle:
            return None
        try:
            return _icon_to_png(handle, size)
        except Exception:
            logger.debug("图标渲染失败：%s", path, exc_info=True)
            return None
        finally:
            _user32.DestroyIcon(handle)

    # ── 路径解析 ────────────────────────────────────────────────────────
    def _resolve_path(self, identity: AppIdentity) -> str | None:
        if identity.exe_path and os.path.exists(identity.exe_path):
            return identity.exe_path
        process = identity.process_name or identity.app_key
        if not process:
            return None
        with self._lock:
            if process in self._paths:
                return self._paths[process]
        found = _app_paths_lookup(process) or shutil.which(process)
        if found and not os.path.exists(found):
            found = None
        with self._lock:
            self._paths[process] = found
        return found


def _app_paths_lookup(process: str) -> str | None:
    """``App Paths`` 注册表点查——安装型应用几乎都在这里登记自己的主程序。

    只有 4 次 ``OpenKey``，与枚举卸载项不是一个数量级。
    """
    import winreg

    subkeys = (
        rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{process}",
        rf"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\{process}",
    )
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for subkey in subkeys:
            try:
                with winreg.OpenKey(root, subkey) as handle:
                    value, _ = winreg.QueryValueEx(handle, "")
            except OSError:
                continue
            candidate = os.path.expandvars((value or "").strip().strip('"'))
            if candidate and os.path.exists(candidate):
                return candidate
    return None


def _extract_icon(path: str) -> int | None:
    """先取可执行文件自带的图标，失败再让 Shell 给一个（至少是文件类型图标）。"""
    large = wintypes.HICON()
    small = wintypes.HICON()
    try:
        count = _shell32.ExtractIconExW(
            path, 0, ctypes.byref(large), ctypes.byref(small), 1
        )
    except OSError:  # pragma: no cover - 极少数损坏的 PE
        count = 0
    if count and (large.value or small.value):
        keep, drop = (large.value, small.value) if large.value else (small.value, None)
        if drop:
            _user32.DestroyIcon(drop)
        return keep
    info = _SHFILEINFOW()
    result = _shell32.SHGetFileInfoW(
        path,
        0,
        ctypes.byref(info),
        ctypes.sizeof(info),
        _SHGFI_ICON | _SHGFI_LARGEICON | _SHGFI_USEFILEATTRIBUTES,
    )
    return info.hIcon if result and info.hIcon else None


def _read_bgra(bitmap: int, width: int, height: int) -> bytearray | None:
    """把 GDI 位图读成自上而下的 32 位 BGRA。``biHeight`` 取负值即为自上而下。"""
    header = _BITMAPINFO()
    header.bmiHeader.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
    header.bmiHeader.biWidth = width
    header.bmiHeader.biHeight = -height
    header.bmiHeader.biPlanes = 1
    header.bmiHeader.biBitCount = 32
    header.bmiHeader.biCompression = _BI_RGB
    buffer = ctypes.create_string_buffer(width * height * 4)
    screen = _user32.GetDC(None)
    try:
        copied = _gdi32.GetDIBits(
            screen, bitmap, 0, height, buffer, ctypes.byref(header), _DIB_RGB_COLORS
        )
    finally:
        _user32.ReleaseDC(None, screen)
    if not copied:
        return None
    return bytearray(buffer.raw)


def _icon_to_png(handle: int, size: int) -> bytes | None:
    """``HICON`` → PNG。alpha 缺失时用掩码位图重建（见模块文档第 2 点）。"""
    from PIL import Image

    info = _ICONINFO()
    if not _user32.GetIconInfo(handle, ctypes.byref(info)):
        return None
    color, mask = info.hbmColor, info.hbmMask
    try:
        if not color:
            # 单色图标（1bpp，颜色与掩码合在一张位图里）。极罕见，不值得单独一条路径。
            return None
        shape = _BITMAP()
        if not _gdi32.GetObjectW(color, ctypes.sizeof(_BITMAP), ctypes.byref(shape)):
            return None
        width, height = int(shape.bmWidth), int(shape.bmHeight)
        if width <= 0 or height <= 0:
            return None
        pixels = _read_bgra(color, width, height)
        if pixels is None:
            return None
        if not any(pixels[3::4]):
            _apply_mask(pixels, mask, width, height)
        image = Image.frombuffer("RGBA", (width, height), bytes(pixels), "raw", "BGRA", 0, 1)
    finally:
        for bitmap in (color, mask):
            if bitmap:
                _gdi32.DeleteObject(bitmap)

    if (width, height) != (size, size):
        image = image.resize((size, size), Image.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _apply_mask(pixels: bytearray, mask: int, width: int, height: int) -> None:
    """老式图标的 alpha 全 0。掩码位图里**白色代表透明**（AND 掩码语义）。"""
    if not mask:
        for index in range(3, len(pixels), 4):
            pixels[index] = 255
        return
    mask_pixels = _read_bgra(mask, width, height)
    if mask_pixels is None:
        for index in range(3, len(pixels), 4):
            pixels[index] = 255
        return
    for index in range(0, len(pixels), 4):
        pixels[index + 3] = 0 if mask_pixels[index] else 255


def available() -> bool:
    """能不能用。只检查导出符号，不做任何真实提取——``build()`` 里不许有副作用。"""
    return all(
        hasattr(library, name)
        for library, name in (
            (_shell32, "ExtractIconExW"),
            (_shell32, "SHGetFileInfoW"),
            (_user32, "GetIconInfo"),
            (_gdi32, "GetDIBits"),
        )
    )


__all__ = ["WindowsIconSource", "available"]
