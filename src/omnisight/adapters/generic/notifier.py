"""兜底通知：日志 + stderr + 数据目录里的 STARTUP_ERROR.txt。

最后那个文件是关键（10 文档 §6）：``--noconsole`` 打包后用户"双击了没反应"时，
它是唯一能被用户自己发现的线索，比任何 GUI 弹框方案都可靠——弹框依赖的 API
可能恰好就是当前环境缺失的那一个。
"""

from __future__ import annotations

import contextlib
import logging
import sys
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

STARTUP_ERROR_FILENAME = "STARTUP_ERROR.txt"


class FileNotifier:
    __slots__ = ("_dir",)

    def __init__(self, directory: Path) -> None:
        self._dir = directory

    def error(self, title: str, message: str) -> None:
        logger.error("%s: %s", title, message)
        if sys.stderr is not None:
            print(f"[OmniSight] {title}\n{message}", file=sys.stderr)
        self._write_file(title, message)

    def _write_file(self, title: str, message: str) -> None:
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().astimezone().isoformat(timespec="seconds")
            (self._dir / STARTUP_ERROR_FILENAME).write_text(
                f"{stamp}\n{title}\n\n{message}\n", encoding="utf-8"
            )
        except OSError:
            # 连数据目录都写不了时无处可诉——日志已经尽力，不要在报错路径上再抛错。
            logger.exception("无法写入 %s", STARTUP_ERROR_FILENAME)

    def clear(self) -> None:
        """启动成功后移除上一次的错误文件，避免用户看到过期线索。"""
        with contextlib.suppress(OSError):  # pragma: no cover
            (self._dir / STARTUP_ERROR_FILENAME).unlink(missing_ok=True)
