"""Windows 系统外壳过滤名单（04 文档 §2.2 的第一级过滤）。

**这份名单天生是平台特定的，因此它属于适配器而非采集层。** 采集层不需要知道任何
进程名——它只看到 ``ForegroundSource.current()`` 返回了 ``None``。其他平台要过滤的
是完全不同的东西（macOS 的 ``com.apple.dock``、Linux 的 ``gnome-shell``），如果这
份名单放在采集层，每加一个平台就得往里塞该平台的语义。

命中的后果是"不产生会话，且期间的按键归到 ``app_id = 0``"，而不是丢弃按键——键盘
总量必须守恒（04 文档 §2.2）。

第二级的**用户排除列表**（``privacy.excluded_processes``）与平台无关，因此在采集层
实现，不在这里。
"""

from __future__ import annotations

#: 全部小写，与 ``app_key = casefold(process_name)`` 的口径一致。
SHELL_KEYS: frozenset[str] = frozenset(
    {
        "explorer.exe",              # 桌面与任务栏本身
        "searchui.exe",              # Win10 搜索
        "searchapp.exe",             # Win11 搜索
        "shellexperiencehost.exe",   # 操作中心、音量浮窗
        "startmenuexperiencehost.exe",
        "lockapp.exe",               # 锁屏
        "textinputhost.exe",         # 输入法候选窗
        "ctfmon.exe",                # 输入法框架
    }
)


def is_shell(app_key: str) -> bool:
    return app_key.casefold() in SHELL_KEYS


def display_name_for(process_name: str) -> str:
    """``"Code.exe"`` → ``"Code"``。用户别名在服务层覆盖它（03 文档 §2.2）。"""
    name = process_name.strip()
    if name.casefold().endswith(".exe"):
        name = name[:-4]
    return name or process_name


__all__ = ["SHELL_KEYS", "display_name_for", "is_shell"]
