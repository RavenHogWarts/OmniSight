"""基于锁文件的单实例控制（POSIX 一等实现，Windows 上作兜底）。

10 文档 §3 的语义是"独占**本用户**的这份数据"。Windows 用会话级命名互斥锁达成，
POSIX 由"锁文件位于用户私有数据目录"天然达成——核心层不关心用哪种机制。
"""

from __future__ import annotations

import contextlib
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


class FileInstanceLock:
    """锁文件 + 建议锁。持有者把 pid 写进文件，便于排查"谁占着"。"""

    __slots__ = ("_fd", "_path")

    def __init__(self, path: Path) -> None:
        self._path = path
        self._fd: int | None = None

    @property
    def path(self) -> Path:
        return self._path

    def acquire(self) -> bool:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(self._path, os.O_RDWR | os.O_CREAT, 0o600)
        except OSError as exc:
            logger.warning("无法打开锁文件 %s：%s——放行启动而非拒绝运行", self._path, exc)
            return True
        if not _try_lock(fd):
            os.close(fd)
            return False
        os.truncate(fd, 0)
        os.write(fd, str(os.getpid()).encode("ascii"))
        self._fd = fd
        return True

    def notify_existing(self) -> bool:
        """无通用的"唤起已有窗口"机制；由调用方退回打开仪表盘 URL。"""
        return False

    def release(self) -> None:
        if self._fd is None:
            return
        try:
            _unlock(self._fd)
        finally:
            os.close(self._fd)
            self._fd = None


def _try_lock(fd: int) -> bool:
    try:
        import fcntl
    except ImportError:
        return _try_lock_windows(fd)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def _unlock(fd: int) -> None:
    try:
        import fcntl
    except ImportError:
        _unlock_windows(fd)
        return
    # 进程退出中，解锁失败无可补救。
    with contextlib.suppress(OSError):
        fcntl.flock(fd, fcntl.LOCK_UN)


def _try_lock_windows(fd: int) -> bool:
    import msvcrt

    try:
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    except OSError:
        return False
    return True


def _unlock_windows(fd: int) -> None:
    import msvcrt

    try:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    except OSError:  # pragma: no cover
        pass
