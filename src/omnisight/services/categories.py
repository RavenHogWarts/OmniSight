"""应用分类——**全项目唯一真源**（07 文档 §10、09 文档 §5）。

TimeLens 把同一份规则在 ``web_app.py:_CATEGORY_RULES`` 与
``static/app-categories.js:CATEGORY_RULES`` 各存了一份，改一处忘另一处就会让前后端
分类不一致。合并后规则只在后端，前端只消费 ``category`` 字段——``app-categories.js``
被删除，不留副本。有测试盯住"静态资源里不再出现第二份规则"。

**两处相对现状的改动：**

1. **分类从 3 个扩到 6 个。** 现状是 ``productivity`` / ``common`` / ``other``，其中
   ``common`` 混装了浏览器、聊天和资源管理器，``other`` 混装了游戏和音乐。06 文档 §3.1
   已经为 6 个类别定了颜色令牌，这里与之对齐。
2. **先按进程名精确匹配，再退回关键词包含。** 现状纯用子串匹配，于是 ``code`` 命中
   ``unicode``、``vscode``、``qqmusic`` 里的任何一个含 "code" 的名字。精确表消掉了
   这一类误判，关键词表仍然兜住没列举到的应用。

用户可以覆盖任何一条（``app.category_source = 'user'``），覆盖后自动规则不再介入。
"""

from __future__ import annotations

#: 类别 id → 展示名。id 进数据库与接口，展示名可随 i18n 改。
CATEGORIES: tuple[tuple[str, str], ...] = (
    ("development", "开发"),
    ("productivity", "效率"),
    ("communication", "沟通"),
    ("entertainment", "娱乐"),
    ("system", "系统"),
    ("uncategorized", "未分类"),
)

CATEGORY_NAMES: dict[str, str] = dict(CATEGORIES)
CATEGORY_IDS: tuple[str, ...] = tuple(name for name, _label in CATEGORIES)
UNCATEGORIZED = "uncategorized"

#: 进程名（不含扩展名，casefold）→ 类别。**精确匹配，优先于关键词**。
EXACT_PROCESSES: dict[str, str] = {
    # 开发
    "code": "development", "code - insiders": "development", "cursor": "development",
    "trae": "development", "devenv": "development", "pycharm64": "development",
    "idea64": "development", "webstorm64": "development", "goland64": "development",
    "clion64": "development", "rider64": "development", "sublime_text": "development",
    "windowsterminal": "development", "wt": "development", "powershell": "development",
    "pwsh": "development", "cmd": "development", "conhost": "development",
    "bash": "development", "mintty": "development", "alacritty": "development",
    "docker desktop": "development", "postman": "development", "insomnia": "development",
    "dbeaver": "development", "navicat": "development", "sqlitestudio": "development",
    "nvim": "development", "vim": "development", "emacs": "development",
    # 效率
    "winword": "productivity", "excel": "productivity", "powerpnt": "productivity",
    "onenote": "productivity", "outlook": "communication", "wps": "productivity",
    "et": "productivity", "wpp": "productivity", "notepad": "productivity",
    "notepad++": "productivity", "obsidian": "productivity", "typora": "productivity",
    "notion": "productivity", "acrobat": "productivity", "sumatrapdf": "productivity",
    "photoshop": "productivity", "illustrator": "productivity", "figma": "productivity",
    "blender": "productivity", "msedge": "productivity", "chrome": "productivity",
    "firefox": "productivity", "safari": "productivity", "brave": "productivity",
    "opera": "productivity", "msedgewebview2": "productivity",
    # 沟通
    "wechat": "communication", "weixin": "communication", "qq": "communication",
    "telegram": "communication", "discord": "communication", "slack": "communication",
    "ms-teams": "communication", "teams": "communication", "feishu": "communication",
    "dingtalk": "communication", "zoom": "communication", "thunderbird": "communication",
    "whatsapp": "communication", "tim": "communication",
    # 娱乐
    "steam": "entertainment", "steamwebhelper": "entertainment",
    "epicgameslauncher": "entertainment", "bilibili": "entertainment",
    "douyin": "entertainment", "cloudmusic": "entertainment", "qqmusic": "entertainment",
    "kugou": "entertainment", "spotify": "entertainment", "potplayer64": "entertainment",
    "potplayermini64": "entertainment", "vlc": "entertainment", "mpv": "entertainment",
    "iqiyi": "entertainment", "youku": "entertainment", "netflix": "entertainment",
    # 系统
    "explorer": "system", "systemsettings": "system", "taskmgr": "system",
    "control": "system", "mmc": "system", "dwm": "system", "sihost": "system",
    "shellexperiencehost": "system", "searchhost": "system", "startmenuexperiencehost": "system",
    "applicationframehost": "system", "snippingtool": "system", "photos": "system",
    "everything": "system", "regedit": "system", "mstsc": "system",
}

#: 关键词包含匹配，**按顺序**判定，第一个命中即返回。
#:
#: 顺序有意义：``game`` 放在最后，否则 ``GameBar`` 之类的系统组件会被算成娱乐。
KEYWORD_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("development", (
        "visual studio", "jetbrains", "android studio", "terminal", "git",
        "docker", "kubernetes", "sourcetree", "fork", "tortoisegit",
    )),
    ("communication", ("mail", "chat", "messenger", "meeting", "会议", "邮件")),
    ("entertainment", (
        "music", "player", "video", "netease", "tencent video", "launcher",
        "音乐", "视频", "游戏", "game",
    )),
    ("productivity", (
        "office", "pdf", "browser", "note", "draw", "design", "浏览器", "笔记",
    )),
    ("system", ("windows", "microsoft.", "host", "service", "设置")),
)


def _stem(process_name: str) -> str:
    """``"Code.exe"`` → ``"code"``。跨平台：Linux/macOS 的进程名本来就没有扩展名。"""
    name = (process_name or "").strip().casefold()
    for suffix in (".exe", ".app"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def categorize(display_name: str = "", process_name: str = "") -> str:
    """自动分类。**永不抛异常**，认不出来就是 ``uncategorized``。

    "认不出来"必须是一个有名字的类别而不是空字符串：``uncategorized`` 在 UI 上有自己的
    颜色与文案（06 文档 §3.1），而空字符串会让分类饼图多出一块没有图例的扇形。
    """
    stem = _stem(process_name)
    exact = EXACT_PROCESSES.get(stem)
    if exact:
        return exact
    haystack = f"{display_name or ''} {process_name or ''}".casefold()
    if not haystack.strip():
        return UNCATEGORIZED
    for category, keywords in KEYWORD_RULES:
        if any(keyword in haystack for keyword in keywords):
            return category
    return UNCATEGORIZED


def is_known(category: str) -> bool:
    return category in CATEGORY_NAMES


def name_of(category: str) -> str:
    """展示名；未知 id 原样返回。

    未知不代表出错：用户可能在旧版里手动设过一个已被删掉的类别，界面照样要画出来，
    而不是让整个分类面板 500（与 ``keymap.label_for`` 同一条原则）。
    """
    return CATEGORY_NAMES.get(category, category)


def catalog() -> list[dict[str, str]]:
    """供设置页与图例使用的类别清单。"""
    return [{"id": category, "name": label} for category, label in CATEGORIES]


__all__ = [
    "CATEGORIES",
    "CATEGORY_IDS",
    "CATEGORY_NAMES",
    "EXACT_PROCESSES",
    "KEYWORD_RULES",
    "UNCATEGORIZED",
    "catalog",
    "categorize",
    "is_known",
    "name_of",
]
