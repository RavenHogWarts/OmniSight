"""端口契约的机械检查（11 文档 §8.2）。

**为什么需要这一层。** ``ports.py`` 里的 Protocol 是核心层与操作系统之间唯一的约定，
而 Python 的 Protocol 不在运行时强制任何东西：一个漏了方法的适配器照样能被构造、
照样能通过类型检查（只要没人显式标注类型），直到运行到那一行才炸。

代价最大的一次就发生在 :class:`Notifier` 上：``lifecycle`` 在启动流程**最后一步**
调用 ``notifier.clear()``，两个现有实现碰巧都有这个方法，所以协议里漏了声明这件事
一直没人发现。新平台照着协议写一个 Notifier，会在"启动完全成功"的那一刻抛
``AttributeError``。

因此本文件对每个端口做两件事：

1. 断言**现有实现**满足协议（``isinstance`` + ``runtime_checkable``）；
2. 断言协议**声明了实现真正被调用到的方法**——这一条靠"调用点用到的名字"清单来钉，
   ``runtime_checkable`` 只检查名字存在，不检查签名，所以清单是必要的补充。

本文件不含任何平台判断，三个平台上都必须通过。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from omnisight.adapters import ports
from omnisight.adapters.generic.instance_lock import FileInstanceLock
from omnisight.adapters.generic.notifier import FileNotifier

#: 各端口协议 → ``lifecycle`` / ``services`` 真正会调用到的方法名。
#:
#: 这份清单是**手工维护**的，且它就是维护成本本身的理由：往里加一行比在启动路径上
#: 追一个 ``AttributeError`` 便宜得多。新增端口方法时同步这里。
REQUIRED_METHODS: dict[type, tuple[str, ...]] = {
    ports.Notifier: ("error", "clear"),
    ports.InstanceLock: ("acquire", "notify_existing", "release"),
    ports.ForegroundSource: ("current", "list_running"),
    ports.KeyboardSource: ("start", "stop", "running", "backend_name", "needs_main_loop"),
    ports.IdleSource: ("idle_seconds",),
    ports.IconSource: ("icon_png",),
    ports.AutostartControl: ("is_enabled", "set_enabled"),
    ports.ElevatedAutostartControl: (
        "is_enabled",
        "is_present",
        "change_blocked_reason",
        "set_enabled",
    ),
    ports.ElevationControl: (
        "is_elevated",
        "can_elevate",
        "relaunch_elevated",
        "open_unelevated",
    ),
}


@pytest.mark.parametrize(
    "protocol", list(REQUIRED_METHODS), ids=lambda proto: proto.__name__
)
def test_protocol_declares_every_method_callers_use(protocol: type) -> None:
    """协议里必须声明调用方真正用到的每一个名字。

    这是 A1 那个缺口的回归测试：``Notifier`` 曾经只声明 ``error``，而
    ``lifecycle`` 一直在调 ``clear``。
    """
    missing = [name for name in REQUIRED_METHODS[protocol] if not hasattr(protocol, name)]
    assert not missing, f"{protocol.__name__} 漏了调用方要用的成员：{missing}"


def test_file_notifier_satisfies_notifier(tmp_path: Path) -> None:
    """通用兜底 Notifier —— 每个平台的实现都以它为最低标准。"""
    notifier = FileNotifier(tmp_path)
    assert isinstance(notifier, ports.Notifier)
    for name in REQUIRED_METHODS[ports.Notifier]:
        assert callable(getattr(notifier, name)), f"FileNotifier.{name} 不可调用"


def test_file_instance_lock_satisfies_instance_lock(tmp_path: Path) -> None:
    lock = FileInstanceLock(tmp_path / "omnisight.lock")
    assert isinstance(lock, ports.InstanceLock)


@pytest.mark.windows_only
def test_windows_notifier_satisfies_notifier(tmp_path: Path) -> None:
    """Windows 的 ``MessageBoxNotifier``。

    标 ``windows_only`` 只因为导入它会拉起 ``ctypes.WinDLL``；协议本身与平台无关。
    """
    from omnisight.adapters.windows.notifier import MessageBoxNotifier

    notifier = MessageBoxNotifier(tmp_path)
    assert isinstance(notifier, ports.Notifier)
    for name in REQUIRED_METHODS[ports.Notifier]:
        assert callable(getattr(notifier, name))
