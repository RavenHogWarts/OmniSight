"""首次运行说明（08 文档 §6.1、12 文档 M6 判据 4/5）。

这一屏的全部内容都是**算出来的，不是写死的文案**。理由不是优雅：一个记录按键的
程序，如果首启页承诺"不记录窗口标题"而用户的 `config.json` 里恰好开着
`record_window_titles`，那这句话就是谎言——而它出现在最需要被信任的地方。因此
"记录什么 / 不记录什么"两张清单由 :class:`~omnisight.adapters.ports.Capabilities`
与当前配置推导，L4（原始事件）开着的时候它会如实出现在"记录"那一栏。

同理，平台支持一栏由 ``platform_id`` + ``tier`` 生成而不是硬编码"仅支持 Windows"：
12 文档 M6 判据 5 要求这句话必须出现且**不含糊其辞地暗示已支持跨平台**，而写死
的字符串在 M8 落地后就会变成新的谎言（R15 那类 issue 正是这么来的）。

状态存在数据库的 ``meta`` 表而不是配置文件：配置是用户会手改、会被"恢复默认"清掉
的东西，而"我已经看过说明了"是一条与这份数据同生共死的事实。库被删掉时说明重新
出现，这是想要的行为——那本来就是一次全新的开始。
"""

from __future__ import annotations

import logging
from typing import Any

from ..core import paths
from .context import ServiceContext

logger = logging.getLogger(__name__)

#: 说明内容的版本。改动到"用户应当重新读一遍"的程度时 +1，旧的确认即失效。
#: 措辞微调不算——那只会制造一次没必要的打扰。
ONBOARDING_VERSION = 1

ACK_KEY = "onboarding_ack"
ACK_VERSION_KEY = "onboarding_ack_version"

#: 各平台的承诺级别（13 文档 §4.1，与 README 的分级表同源）。
TIER_LABELS = {
    1: "一级平台：全功能，性能基准在此度量",
    2: "二级平台：全功能，已知差异逐条记录",
    3: "三级平台：仅键盘统计，应用归因受平台限制不可用",
}


class OnboardingService:
    """首启说明的内容与"看过了"这条状态。"""

    __slots__ = ("_ctx",)

    def __init__(self, ctx: ServiceContext) -> None:
        self._ctx = ctx

    # ── 状态 ────────────────────────────────────────────────────────────
    def acknowledged(self) -> str | None:
        """返回确认时刻；从未确认、或确认的是更早版本的说明时返回 ``None``。"""
        stamp = self._ctx.database.meta_get(ACK_KEY)
        if not stamp:
            return None
        try:
            version = int(self._ctx.database.meta_get(ACK_VERSION_KEY, "0") or 0)
        except ValueError:  # pragma: no cover - meta 被手改成了非数字
            version = 0
        return stamp if version >= ONBOARDING_VERSION else None

    def acknowledge(self) -> str:
        now = self._ctx.clock.now().isoformat(timespec="seconds")
        self._ctx.database.meta_set(ACK_KEY, now)
        self._ctx.database.meta_set(ACK_VERSION_KEY, str(ONBOARDING_VERSION))
        logger.info("用户已确认首次运行说明（v%s）", ONBOARDING_VERSION)
        return now

    # ── 内容 ────────────────────────────────────────────────────────────
    def describe(self) -> dict[str, Any]:
        acknowledged = self.acknowledged()
        return {
            "version": ONBOARDING_VERSION,
            "required": acknowledged is None,
            "acknowledged_at": acknowledged,
            "records": self._records(),
            "not_records": self._not_records(),
            "paths": self._paths(),
            "platform": self._platform(),
            "pause": {
                "tray_item": "暂停记录",
                "detail": (
                    "托盘菜单里的「暂停记录」立即停止一切写入，图标同时变灰；"
                    "设置里也有同一个开关。暂停期间缓冲的事件被丢弃而不是延后落盘。"
                ),
            },
            "documents": {
                "privacy": "docs/privacy.md",
                "faq": "docs/faq.md",
                "uninstall": "README.md#完全卸载",
            },
        }

    def _records(self) -> list[dict[str, str]]:
        """"会记录什么"——按当前能力与配置如实列出。"""
        caps = self._ctx.capabilities
        privacy = self._ctx.config.privacy
        capture = self._ctx.config.capture
        items: list[dict[str, str]] = []
        if caps.foreground:
            items.append(
                {
                    "code": "app_usage",
                    "text": "你使用了哪些应用、各用了多久",
                    "detail": "进程名与可执行文件路径，用于把时长归到应用上。",
                }
            )
        if caps.keyboard:
            duration = "每个键被按了多少次" + ("、按压多长" if caps.keyboard_durations else "")
            items.append(
                {
                    "code": "key_counts",
                    "text": duration,
                    "detail": "只有计数与时长的汇总，不含按键的先后顺序。",
                }
            )
        if privacy.record_window_titles and caps.window_titles:
            items.append(
                {
                    "code": "window_titles",
                    "text": "窗口标题（你已在配置里开启）",
                    "detail": "网页标题与文件名会随会话一起入库。关闭方式见设置页。",
                }
            )
        if capture.store_raw_key_events:
            items.append(
                {
                    "code": "raw_key_events",
                    "text": "每次按键的精确时间与所属应用（你已在配置里开启）",
                    "detail": (
                        "这类数据在技术上可以还原你输入过的文本内容，"
                        "也可作为识别个人的击键特征。仅在你了解并接受这一点时保持开启。"
                    ),
                }
            )
        return items

    def _not_records(self) -> list[dict[str, str]]:
        """"不会记录什么"。开着的项**不会**出现在这里——那才是最要紧的一致性。"""
        privacy = self._ctx.config.privacy
        capture = self._ctx.config.capture
        items: list[dict[str, str]] = []
        if not (privacy.record_window_titles and self._ctx.capabilities.window_titles):
            items.append({"code": "window_titles", "text": "窗口标题（网页标题、文件名）"})
        if not capture.store_raw_key_events:
            items.append({"code": "raw_key_events", "text": "按键的先后顺序与精确时间"})
        items.append({"code": "content", "text": "剪贴板、屏幕内容、文件内容"})
        items.append({"code": "network", "text": "任何形式的上传：无账号、不联网、无遥测"})
        return items

    def _paths(self) -> dict[str, str]:
        database = self._ctx.database.path
        return {
            "database": str(database),
            "data_dir": str(database.parent),
            "logs_dir": str(paths.logs_dir()),
            "config": str(paths.config_path()),
            "portable": str(paths.is_portable()),
        }

    def _platform(self) -> dict[str, Any]:
        """平台支持声明。**架构就绪不等于平台就绪**（12 文档 M6 判据 5）。"""
        caps = self._ctx.capabilities
        return {
            "id": caps.platform_id,
            "tier": caps.tier,
            "tier_label": TIER_LABELS.get(caps.tier, "未在支持列表中"),
            "notice": (
                "当前版本只支持 Windows，其他平台在规划中（尚未实现）。"
                if caps.platform_id == "windows"
                else "当前版本只支持 Windows，此系统上的功能可能不完整。"
            ),
        }


__all__ = ["ACK_KEY", "ACK_VERSION_KEY", "ONBOARDING_VERSION", "TIER_LABELS", "OnboardingService"]
