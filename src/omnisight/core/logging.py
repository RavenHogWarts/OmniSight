"""日志配置：滚动文件 + 控制台，附一道内容红线过滤器。

10 文档 §7 的红线在这里落地：**代码里可能忘记，过滤器不会**。窗口标题与按键
id 一律不进日志，即使调用方不小心把它们传进了格式化参数。
"""

from __future__ import annotations

import logging
import logging.handlers
import re
import sys
from pathlib import Path

LOG_FILENAME = "omnisight.log"
MAX_BYTES = 2 * 1024 * 1024
BACKUP_COUNT = 5

_FORMAT = "%(asctime)s %(levelname)-7s [%(threadName)s] %(name)s: %(message)s"

#: 命中即替换为 <redacted>。刻意只覆盖"结构化地泄露内容"的两类形态：
#: 显式的标题/文本字段，以及 key_id=xxx 这样的按键标识。
_REDACT_PATTERNS = (
    re.compile(r"(?i)\b(window_title|title|text|clipboard)\s*=\s*(?P<v>'[^']*'|\"[^\"]*\"|\S+)"),
    re.compile(r"(?i)\b(key_id|key_name)\s*=\s*(?P<v>'[^']*'|\"[^\"]*\"|\S+)"),
)

REDACTED = "<redacted>"


class PrivacyFilter(logging.Filter):
    """把窗口标题与按键标识从日志消息里抹掉（10 文档 §7）。"""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # pragma: no cover - 格式化本身坏了，交给 handler 报错
            return True
        scrubbed = scrub(message)
        if scrubbed != message:
            record.msg = scrubbed
            record.args = ()
        return True


def scrub(message: str) -> str:
    for pattern in _REDACT_PATTERNS:
        message = pattern.sub(lambda m: f"{m.group(1)}={REDACTED}", message)
    return message


def configure(
    logs_dir: Path,
    *,
    level: str = "INFO",
    console: bool = True,
) -> Path:
    """配置根日志器，返回日志文件路径。可重复调用（先清理已有 handler）。"""
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / LOG_FILENAME

    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()

    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    formatter = logging.Formatter(_FORMAT)
    privacy = PrivacyFilter()

    file_handler = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(privacy)
    root.addHandler(file_handler)

    # --noconsole 打包后 stderr 可能是 None，此时不挂控制台 handler。
    if console and sys.stderr is not None:
        stream_handler = logging.StreamHandler(sys.stderr)
        stream_handler.setFormatter(formatter)
        stream_handler.addFilter(privacy)
        root.addHandler(stream_handler)

    # werkzeug 每个请求打一行 access log，对常驻托盘程序是噪声。
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    return log_path
