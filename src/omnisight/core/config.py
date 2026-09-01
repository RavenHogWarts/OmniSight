"""配置模型、加载、校验与默认值生成（合并两个旧项目的 ``settings.py``）。

设计要点：

* **校验失败不覆盖用户文件。** 旧 TimeLens 的做法是遇到坏配置就静默写回默认值，
  用户手改出一个拼写错误就会丢掉全部设置。这里改为报错退出并指出具体字段
  （10 文档 §6）。
* **未知键保留并告警。** 用旧版程序打开新版写的配置时，未知键不能被丢弃，
  否则降级运行一次就会永久损失新版设置。
* **只有引导期配置进文件。** 端口、数据目录、隐私开关这些"启动前就要知道"的
  项在 ``config.json``；其余用户设置存库（05 文档 §7）。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

CONFIG_VERSION = 1

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
KEYBOARD_BACKENDS = frozenset({"auto", "raw_input", "pynput", "none"})
THEMES = frozenset({"system", "light", "dark"})
DEFAULT_VIEWS = frozenset({"daily", "weekly", "monthly", "yearly", "total"})
KEYBOARD_LAYOUTS = frozenset({"auto", "ansi104", "iso105", "tkl87", "mac_ansi", "mac_iso"})
UI_SHELLS = frozenset({"browser", "webview"})


class ConfigError(Exception):
    """配置无法使用。``field`` 指向具体出错的键，供错误弹框显示。"""

    def __init__(self, message: str, field_path: str | None = None) -> None:
        super().__init__(message)
        self.field_path = field_path


@dataclass(frozen=True, slots=True)
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 6100


@dataclass(frozen=True, slots=True)
class CaptureConfig:
    foreground_poll_seconds: float = 1.0
    idle_threshold_seconds: int = 1800
    session_flush_seconds: int = 10
    keyboard_backend: str = "auto"
    store_raw_key_events: bool = True
    paused: bool = False


@dataclass(frozen=True, slots=True)
class StorageConfig:
    data_dir: str | None = None
    raw_event_retention_days: int = 0
    checkpoint_interval_seconds: int = 300


@dataclass(frozen=True, slots=True)
class UiConfig:
    theme: str = "system"
    locale: str = "zh-CN"
    default_view: str = "daily"
    timezone: str | None = None
    keyboard_layout: str = "auto"
    shell: str = "browser"
    #: 一周从哪天开始：0 = 周一（ISO / 中国大陆），6 = 周日（美国习惯）。
    #: 05 文档 §1.2 要求"周"统一为自然周且起始日可配置，§9 的示例直接引用了
    #: ``settings.ui.week_starts_on``——M2 落地周期计算时才需要它，故此时补上。
    week_starts_on: int = 0


@dataclass(frozen=True, slots=True)
class PrivacyConfig:
    record_window_titles: bool = False
    excluded_processes: tuple[str, ...] = ()
    realtime_stream: bool = True


@dataclass(frozen=True, slots=True)
class AppsConfig:
    aliases: dict[str, str] = field(default_factory=dict)
    merges: dict[str, str] = field(default_factory=dict)
    categories: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Config:
    version: int = CONFIG_VERSION
    server: ServerConfig = field(default_factory=ServerConfig)
    capture: CaptureConfig = field(default_factory=CaptureConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    ui: UiConfig = field(default_factory=UiConfig)
    privacy: PrivacyConfig = field(default_factory=PrivacyConfig)
    apps: AppsConfig = field(default_factory=AppsConfig)
    #: 未识别的键，原样保留以便旧版打开新版配置后不丢设置
    unknown: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        unknown = data.pop("unknown")
        data["privacy"]["excluded_processes"] = list(self.privacy.excluded_processes)
        data.update(unknown)
        return data

    def dashboard_url(self, token: str | None = None) -> str:
        host = "127.0.0.1" if self.server.host in {"0.0.0.0", "::"} else self.server.host
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        url = f"http://{host}:{self.server.port}/"
        return f"{url}?token={token}" if token else url


_SECTIONS: dict[str, type] = {
    "server": ServerConfig,
    "capture": CaptureConfig,
    "storage": StorageConfig,
    "ui": UiConfig,
    "privacy": PrivacyConfig,
    "apps": AppsConfig,
}


def _coerce_section(name: str, raw: Any, warnings: list[str]) -> Any:
    """按声明的字段构造一个配置段；未知子键告警后丢弃（顶层才保留）。"""
    cls = _SECTIONS[name]
    if raw is None:
        return cls()
    if not isinstance(raw, dict):
        raise ConfigError(f"`{name}` 必须是对象", name)
    known = {f for f in cls.__dataclass_fields__}
    kwargs: dict[str, Any] = {}
    for key, value in raw.items():
        if key in known:
            kwargs[key] = value
        else:
            warnings.append(f"忽略未知配置项 `{name}.{key}`")
    try:
        return cls(**kwargs)
    except TypeError as exc:  # pragma: no cover - dataclass 只会因类型数量出错
        raise ConfigError(f"`{name}` 结构错误：{exc}", name) from exc


def _require(condition: bool, message: str, field_path: str) -> None:
    if not condition:
        raise ConfigError(message, field_path)


def _as_number(value: Any, field_path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"`{field_path}` 必须是数字", field_path)
    return float(value)


def _as_int(value: Any, field_path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"`{field_path}` 必须是整数", field_path)
    return value


def _as_bool(value: Any, field_path: str) -> bool:
    if not isinstance(value, bool):
        raise ConfigError(f"`{field_path}` 必须是 true 或 false", field_path)
    return value


def validate(cfg: Config) -> Config:
    """校验并归一化。任何不合法取值都抛 :class:`ConfigError`，绝不静默回退。"""
    host = cfg.server.host
    _require(isinstance(host, str) and bool(host), "`server.host` 不能为空", "server.host")
    # 08 文档 §3.2e：绑定非回环地址等于把按键统计暴露到局域网，直接拒绝启动。
    _require(
        host in LOOPBACK_HOSTS,
        f"`server.host` 只能是回环地址 {sorted(LOOPBACK_HOSTS)}，当前为 {host!r}——"
        "监听非回环地址会把本机数据暴露到网络",
        "server.host",
    )
    port = _as_int(cfg.server.port, "server.port")
    _require(1024 <= port <= 65535, "`server.port` 必须在 1024–65535 之间", "server.port")

    poll = _as_number(cfg.capture.foreground_poll_seconds, "capture.foreground_poll_seconds")
    _require(
        0.5 <= poll <= 10,
        "`capture.foreground_poll_seconds` 必须在 0.5–10 之间",
        "capture.foreground_poll_seconds",
    )
    idle = _as_int(cfg.capture.idle_threshold_seconds, "capture.idle_threshold_seconds")
    _require(
        60 <= idle <= 24 * 3600,
        "`capture.idle_threshold_seconds` 必须在 60–86400 之间",
        "capture.idle_threshold_seconds",
    )
    flush = _as_int(cfg.capture.session_flush_seconds, "capture.session_flush_seconds")
    _require(
        1 <= flush <= 300,
        "`capture.session_flush_seconds` 必须在 1–300 之间",
        "capture.session_flush_seconds",
    )
    _require(
        cfg.capture.keyboard_backend in KEYBOARD_BACKENDS,
        f"`capture.keyboard_backend` 只能是 {sorted(KEYBOARD_BACKENDS)}",
        "capture.keyboard_backend",
    )
    _as_bool(cfg.capture.store_raw_key_events, "capture.store_raw_key_events")
    _as_bool(cfg.capture.paused, "capture.paused")

    retention = _as_int(cfg.storage.raw_event_retention_days, "storage.raw_event_retention_days")
    _require(
        retention >= 0,
        "`storage.raw_event_retention_days` 不能为负（0 = 永久保留）",
        "storage.raw_event_retention_days",
    )
    checkpoint = _as_int(
        cfg.storage.checkpoint_interval_seconds, "storage.checkpoint_interval_seconds"
    )
    _require(
        30 <= checkpoint <= 3600,
        "`storage.checkpoint_interval_seconds` 必须在 30–3600 之间",
        "storage.checkpoint_interval_seconds",
    )
    if cfg.storage.data_dir is not None:
        _require(
            isinstance(cfg.storage.data_dir, str) and bool(cfg.storage.data_dir.strip()),
            "`storage.data_dir` 必须是非空路径字符串，或 null 表示按平台惯例解析",
            "storage.data_dir",
        )

    _require(cfg.ui.theme in THEMES, f"`ui.theme` 只能是 {sorted(THEMES)}", "ui.theme")
    _require(
        cfg.ui.default_view in DEFAULT_VIEWS,
        f"`ui.default_view` 只能是 {sorted(DEFAULT_VIEWS)}",
        "ui.default_view",
    )
    _require(
        cfg.ui.keyboard_layout in KEYBOARD_LAYOUTS,
        f"`ui.keyboard_layout` 只能是 {sorted(KEYBOARD_LAYOUTS)}",
        "ui.keyboard_layout",
    )
    _require(cfg.ui.shell in UI_SHELLS, f"`ui.shell` 只能是 {sorted(UI_SHELLS)}", "ui.shell")
    week_start = _as_int(cfg.ui.week_starts_on, "ui.week_starts_on")
    _require(
        0 <= week_start <= 6,
        "`ui.week_starts_on` 必须在 0–6 之间（0 = 周一）",
        "ui.week_starts_on",
    )
    if cfg.ui.timezone is not None:
        # 时区名写错会让所有日期桶归错日，且事后无法从数据里看出来——必须启动即拒。
        from .clock import ZoneInfoNotFoundError, resolve_timezone

        try:
            resolve_timezone(cfg.ui.timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ConfigError(
                f"`ui.timezone` 不是有效的 IANA 时区名（如 Asia/Shanghai）：{exc}", "ui.timezone"
            ) from exc

    _as_bool(cfg.privacy.record_window_titles, "privacy.record_window_titles")
    _as_bool(cfg.privacy.realtime_stream, "privacy.realtime_stream")
    excluded = cfg.privacy.excluded_processes
    if isinstance(excluded, str):
        raise ConfigError("`privacy.excluded_processes` 必须是数组", "privacy.excluded_processes")
    normalized = tuple(sorted({str(item).casefold() for item in excluded if str(item).strip()}))

    return replace(cfg, server=replace(cfg.server, port=port), privacy=replace(
        cfg.privacy, excluded_processes=normalized
    ))


def default_config() -> Config:
    return validate(Config())


def loads(text: str) -> tuple[Config, list[str]]:
    """解析配置文本，返回 ``(config, warnings)``。"""
    warnings: list[str] = []
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConfigError(
            f"config.json 语法错误：第 {exc.lineno} 行第 {exc.colno} 列 {exc.msg}"
        ) from exc
    if not isinstance(raw, dict):
        raise ConfigError("config.json 的顶层必须是对象")

    version = raw.pop("version", CONFIG_VERSION)
    if not isinstance(version, int) or version < 1:
        raise ConfigError("`version` 必须是正整数", "version")
    if version > CONFIG_VERSION:
        warnings.append(
            f"config.json 版本 {version} 高于本程序支持的 {CONFIG_VERSION}，"
            "未识别的设置会被保留但不生效"
        )

    sections = {name: _coerce_section(name, raw.pop(name, None), warnings) for name in _SECTIONS}
    cfg = Config(version=min(version, CONFIG_VERSION), unknown=raw, **sections)
    return validate(cfg), warnings


def dumps(cfg: Config) -> str:
    return json.dumps(cfg.to_dict(), indent=2, ensure_ascii=False) + "\n"


def load(path: Path) -> tuple[Config, list[str]]:
    """加载配置；文件不存在时写入一份默认配置并返回它。"""
    if not path.exists():
        cfg = default_config()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(dumps(cfg), encoding="utf-8")
        return cfg, [f"未找到配置文件，已生成默认配置：{path}"]
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"无法读取 {path}：{exc}") from exc
    return loads(text)


def save(path: Path, cfg: Config) -> None:
    """原子写回：先写临时文件再替换，避免断电留下半个 JSON。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(dumps(validate(cfg)), encoding="utf-8")
    tmp.replace(path)
