"""TCC 授权探测（19 文档 §2.5 / 20 文档 B5）。

**只 preflight，绝不 request。** ``CGRequestListenEventAccess`` 会弹系统对话框，
而 ``detect()`` 的契约是"纯函数、无副作用、永不抛异常"——请求授权是一个由用户
点击触发的动作，不落在启动路径上。用户自己去 系统设置 › 隐私与安全性 里勾选，
``hint`` 把这条路写清楚。

两张授权的必要性不同：

* **输入监控（input_monitoring）**：键盘采集的门槛。没有它 event tap 与 pynput
  一起失效（pynput 在 mac 上同样走 CGEventTap）——键盘统计为 0，屏幕时间照常。
* **辅助功能（accessibility）**：只有窗口标题需要它，而标题默认关闭，所以多数
  用户根本不需要。它**不在** ``permissions_required`` 里（required 表达"这个平台
  的完整体验需要什么"，标题属于可选维度），但授权与否会如实出现在 ``granted``。
"""

from __future__ import annotations

import logging

from ..ports import DegradedNotice

logger = logging.getLogger(__name__)

INPUT_MONITORING = "input_monitoring"
ACCESSIBILITY = "accessibility"

#: 「输入监控」被拒时的降级说明。severity 用 error：键盘面板整个空掉，而用户
#: 不知道为什么——一条把路标写全的说明是此时唯一的产品手段。
INPUT_MONITORING_DENIED = DegradedNotice(
    code="input_monitoring_denied",
    severity="error",
    title="键盘采集需要「输入监控」授权",
    detail=(
        "系统还没有允许本程序读取键盘事件，键盘统计因此为 0；"
        "应用使用时长的统计不受影响，仍在正常记录。"
    ),
    hint=(
        "打开 系统设置 › 隐私与安全性 › 输入监控，勾选 OmniSight"
        "（源码运行时勾选的是终端），然后重新启动本程序"
    ),
)

#: 授权后无需重启的那条（19 文档 §2.5 的 M9 判据）尚未落地时，先给如实的引导。
SETUP_HINT = "键盘统计需要在「系统设置 › 隐私与安全性 › 输入监控」中允许本程序"


def preflight() -> tuple[tuple[str, ...], tuple[str, ...]]:
    """``(required, granted)``。**只探测，不弹任何对话框，永不抛异常。**

    探测本身失败（框架缺失、非 mac 环境）按"未授权"上报——谎报 granted 的后果
    是面板空转，而"未授权 + 引导文案"至少把下一步写清楚了。
    """
    granted: list[str] = []
    try:
        from Quartz import CGPreflightListenEventAccess

        if CGPreflightListenEventAccess():
            granted.append(INPUT_MONITORING)
    except Exception:
        logger.debug("输入监控探测不可用", exc_info=True)
    try:
        from ApplicationServices import AXIsProcessTrusted

        if AXIsProcessTrusted():
            granted.append(ACCESSIBILITY)
    except Exception:
        logger.debug("辅助功能探测不可用", exc_info=True)
    return (INPUT_MONITORING,), tuple(granted)


__all__ = [
    "ACCESSIBILITY",
    "INPUT_MONITORING",
    "INPUT_MONITORING_DENIED",
    "SETUP_HINT",
    "preflight",
]
