"""设置服务：读、改、热生效（05 文档 §7）。

**设置页由后端数据生成。** 每一项都带 ``value`` / ``default`` / ``options`` /
``available`` / ``unavailable_reason``，前端照着渲染表单，因此不含"哪个开关在哪个平台
上要隐藏"这类前端知识——那是 07 文档 §10 明令禁止的。

**改一项要说清它什么时候生效。** 响应分三档：``applied``（已生效）、
``requires_restart``（写进文件了，下次启动生效）、``rejected``（连文件都没写）。
旧 TimeLens 的做法是遇到坏值静默回退到默认值，用户以为改成功了——这里一律拒绝并指名
字段（10 文档 §6）。

**校验失败不写文件。** 先在内存里拼出新配置、跑一遍 :func:`~omnisight.core.config.validate`，
全部通过才原子落盘。半套配置比旧配置糟得多。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from ..capture import layouts
from ..core import config as config_module
from ..core.config import Config, ConfigError
from . import categories
from .context import ServiceContext

logger = logging.getLogger(__name__)

#: 生效方式。``restart`` 的项写进文件但当次运行不变——谎称已生效比说清楚糟得多。
HOT = "hot"
RESTART = "restart"


@dataclass(frozen=True, slots=True)
class SettingSpec:
    """一项设置的元数据。**声明式**：新增一项只改这张表。"""

    path: str
    kind: str
    applies: str = HOT
    options: tuple[object, ...] | None = None
    minimum: float | None = None
    maximum: float | None = None
    #: 需要哪项能力才可用；``None`` 表示与平台无关。
    capability: str | None = None
    note: str | None = None

    @property
    def section(self) -> str:
        return self.path.split(".", 1)[0]

    @property
    def field(self) -> str:
        return self.path.split(".", 1)[1]


SPECS: tuple[SettingSpec, ...] = (
    SettingSpec("server.port", "int", RESTART, minimum=1024, maximum=65535),
    SettingSpec("capture.foreground_poll_seconds", "number", HOT, minimum=0.5, maximum=10),
    SettingSpec("capture.idle_threshold_seconds", "int", HOT, minimum=60, maximum=86400),
    SettingSpec("capture.session_flush_seconds", "int", HOT, minimum=1, maximum=300),
    SettingSpec(
        "capture.keyboard_backend",
        "enum",
        RESTART,
        options=tuple(sorted(config_module.KEYBOARD_BACKENDS)),
        capability="keyboard",
    ),
    SettingSpec("capture.store_raw_key_events", "bool", HOT),
    SettingSpec("capture.paused", "bool", HOT),
    SettingSpec("storage.data_dir", "path", RESTART),
    SettingSpec(
        "storage.raw_event_retention_days",
        "int",
        RESTART,
        minimum=0,
        note="保留期的清理动作排在后续版本，改动当前只写进配置",
    ),
    SettingSpec(
        "storage.checkpoint_interval_seconds", "int", HOT, minimum=30, maximum=3600
    ),
    SettingSpec("ui.theme", "enum", HOT, options=tuple(sorted(config_module.THEMES))),
    SettingSpec("ui.locale", "string", HOT),
    SettingSpec(
        "ui.default_view", "enum", HOT, options=tuple(sorted(config_module.DEFAULT_VIEWS))
    ),
    SettingSpec(
        "ui.timezone",
        "string",
        RESTART,
        note="日期桶按此时区切分，改动只影响之后写入的数据",
    ),
    SettingSpec(
        "ui.keyboard_layout",
        "enum",
        HOT,
        options=("auto", *layouts.IMPLEMENTED_FAMILIES),
    ),
    SettingSpec(
        "ui.shell",
        "enum",
        RESTART,
        options=("browser",),
        note="WebView 外壳排在后续版本，当前只有浏览器外壳",
    ),
    SettingSpec("ui.week_starts_on", "int", HOT, minimum=0, maximum=6),
    SettingSpec(
        "privacy.record_window_titles",
        "bool",
        RESTART,
        capability="window_titles",
        note="标题记录由适配器在启动时决定，改动下次启动生效",
    ),
    SettingSpec("privacy.excluded_processes", "list", HOT),
    SettingSpec("privacy.realtime_stream", "bool", HOT),
)

SPEC_BY_PATH: dict[str, SettingSpec] = {spec.path: spec for spec in SPECS}


def _value_of(config: Config, spec: SettingSpec) -> Any:
    value = getattr(getattr(config, spec.section), spec.field)
    return list(value) if isinstance(value, tuple) else value


class SettingsService:
    __slots__ = ("_config_path", "_ctx", "_on_change")

    def __init__(
        self,
        ctx: ServiceContext,
        *,
        config_path: Path,
        on_change: Callable[[Config], None] | None = None,
    ) -> None:
        self._ctx = ctx
        self._config_path = config_path
        self._on_change = on_change

    # ── 读 ──────────────────────────────────────────────────────────────
    def describe(self) -> dict[str, object]:
        config = self._ctx.config
        defaults = config_module.Config()
        items: dict[str, object] = {}
        for spec in SPECS:
            available, reason = self._availability(spec)
            entry: dict[str, object] = {
                "value": _value_of(config, spec),
                "default": _value_of(defaults, spec),
                "kind": spec.kind,
                "applies": spec.applies,
                "available": available,
            }
            if spec.options is not None:
                entry["options"] = list(spec.options)
            if spec.minimum is not None:
                entry["min"] = spec.minimum
            if spec.maximum is not None:
                entry["max"] = spec.maximum
            if reason:
                entry["unavailable_reason"] = reason
            if spec.note:
                entry["note"] = spec.note
            items[spec.path] = entry
        items["system.autostart"] = self._autostart_entry()
        return {
            "settings": items,
            "categories": categories.catalog(),
            "config_path": str(self._config_path),
        }

    def _availability(self, spec: SettingSpec) -> tuple[bool, str | None]:
        if spec.path == "ui.shell":
            return (False, "当前版本只提供浏览器外壳")
        if spec.capability is None:
            return (True, None)
        if getattr(self._ctx.capabilities, spec.capability, False):
            return (True, None)
        return (False, f"当前环境不具备 {spec.capability} 能力")

    def _autostart_entry(self) -> dict[str, object]:
        """开机自启不在配置文件里——它的真源是操作系统（注册表 / LaunchAgent / XDG）。

        读它要问适配器；``capabilities.autostart == False`` 时如实标不可用，
        前端据此隐藏开关而不是让用户点一个注定 422 的按钮（05 文档 §7）。
        """
        control = getattr(self._ctx.adapters, "autostart", None)
        available = bool(self._ctx.capabilities.autostart and control is not None)
        value = False
        if available:
            try:
                value = bool(control.is_enabled())
            except Exception:  # pragma: no cover - 注册表读失败
                logger.debug("读取自启状态失败", exc_info=True)
                available = False
        return {
            "value": value,
            "default": False,
            "kind": "bool",
            "applies": HOT,
            "available": available,
            **({} if available else {"unavailable_reason": "当前环境不支持自动配置开机自启"}),
        }

    def set_autostart(self, enabled: bool) -> bool:
        control = getattr(self._ctx.adapters, "autostart", None)
        if control is None or not self._ctx.capabilities.autostart:
            raise CapabilityMissing("autostart", "当前环境不支持自动配置开机自启")
        control.set_enabled(enabled)
        return bool(control.is_enabled())

    # ── 写 ──────────────────────────────────────────────────────────────
    def patch(self, updates: dict[str, Any]) -> dict[str, object]:
        """部分更新。返回 ``{applied, requires_restart, rejected}``。"""
        rejected: list[dict[str, str]] = []
        staged: dict[str, dict[str, Any]] = {}
        for path, value in updates.items():
            spec = SPEC_BY_PATH.get(path)
            if spec is None:
                rejected.append(
                    {"field": path, "code": "unknown_setting", "message": "没有这一项设置"}
                )
                continue
            available, reason = self._availability(spec)
            if not available:
                rejected.append(
                    {
                        "field": path,
                        "code": "capability_unavailable",
                        "message": reason or "当前环境不支持这一项",
                    }
                )
                continue
            if spec.options is not None and value not in spec.options:
                rejected.append(
                    {
                        "field": path,
                        "code": "invalid_value",
                        "message": f"只能是 {list(spec.options)}",
                    }
                )
                continue
            staged.setdefault(spec.section, {})[spec.field] = _coerce(spec, value)

        if not staged:
            return {"applied": [], "requires_restart": [], "rejected": rejected}

        candidate = self._ctx.config
        for section, fields in staged.items():
            section_value = replace(getattr(candidate, section), **fields)
            candidate = replace(candidate, **{section: section_value})
        try:
            validated = config_module.validate(candidate)
        except ConfigError as exc:
            # 一项越界就整批拒绝：写进去半套配置比不写糟得多。
            rejected.append(
                {
                    "field": exc.field_path or "",
                    "code": "out_of_range",
                    "message": str(exc),
                }
            )
            return {"applied": [], "requires_restart": [], "rejected": rejected}

        config_module.save(self._config_path, validated)
        self._ctx.config = validated
        if self._on_change is not None:
            self._on_change(validated)
        self.apply_runtime(validated)
        self._ctx.cache.clear()

        touched = [
            spec.path
            for spec in SPECS
            if spec.section in staged and spec.field in staged[spec.section]
        ]
        return {
            "applied": [path for path in touched if SPEC_BY_PATH[path].applies == HOT],
            "requires_restart": [
                path for path in touched if SPEC_BY_PATH[path].applies == RESTART
            ],
            "rejected": rejected,
        }

    def apply_runtime(self, config: Config) -> None:
        """把能立刻生效的项推给正在跑的采集管道。

        每一项都必须有一个真实的 setter；"看起来会生效"是这里最容易犯的错——设置页显示
        已应用而采集线程还在用旧值，用户完全无从发现。
        """
        capture = self._ctx.capture
        if capture is None:
            return
        monitor = getattr(capture, "foreground", None)
        if monitor is not None:
            monitor.set_excluded(frozenset(config.privacy.excluded_processes))
            monitor.set_idle_threshold_seconds(config.capture.idle_threshold_seconds)
            monitor.set_poll_seconds(config.capture.foreground_poll_seconds)
            monitor.set_session_flush_seconds(config.capture.session_flush_seconds)
        writer = getattr(capture, "writer", None)
        if writer is not None:
            writer.set_store_raw(config.capture.store_raw_key_events)
            writer.set_checkpoint_interval(config.storage.checkpoint_interval_seconds)
        self.set_paused(config.capture.paused)

    def set_paused(self, paused: bool) -> dict[str, object]:
        """暂停/恢复采集。**必须是真的**：11 文档 §4.5 有一条"暂停后零行写入"的回归测试。

        恢复时不补记暂停期间的任何数据，前台会话从恢复时刻重新开始（04 文档 §7）。
        """
        capture = self._ctx.capture
        if capture is None:
            return {"paused": paused, "effective": False}
        for component in (getattr(capture, "keyboard", None), getattr(capture, "foreground", None)):
            if component is None:
                continue
            component.pause() if paused else component.resume()
        return {"paused": paused, "effective": True}


class CapabilityMissing(RuntimeError):
    """请求的操作依赖当前平台不具备的能力。表现层把它翻成 422。"""

    def __init__(self, capability: str, message: str) -> None:
        super().__init__(message)
        self.capability = capability
        self.message = message


def _coerce(spec: SettingSpec, value: Any) -> Any:
    """只做**形状**转换，取值范围交给 :func:`config.validate` —— 校验只该有一处。"""
    if spec.kind == "list":
        if isinstance(value, str):
            raise ConfigError(f"`{spec.path}` 必须是数组", spec.path)
        return tuple(str(item) for item in value or ())
    if spec.kind == "path":
        return str(value) if value else None
    if spec.kind == "int" and isinstance(value, bool):
        raise ConfigError(f"`{spec.path}` 必须是整数", spec.path)
    return value


__all__ = [
    "HOT",
    "RESTART",
    "SPECS",
    "SPEC_BY_PATH",
    "CapabilityMissing",
    "SettingSpec",
    "SettingsService",
]
