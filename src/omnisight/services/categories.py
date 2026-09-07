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
#:
#: 历史上 ``system`` 行里还有 ``"microsoft."``——它是为 Windows 的 UWP 包名
#: （``Microsoft.WindowsStore``）准备的，但在 bundle id 的世界里是个陷阱：
#: ``com.microsoft.VSCode`` 会因此被判成"系统"。真正需要的名字进精确表
#: （``photos`` 已经在），不留会跨口径误伤的关键词（19 文档 A3）。
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
    ("system", ("windows", "host", "service", "设置")),
)

#: bundle id（casefold）→ 类别。macOS 的应用身份是 bundle id，与进程名表
#: **按身份口径分家**：同一台 Mac 上 bundle id 与进程名可以并存，"查哪张表"
#: 由数据行自己的 ``identity_kind`` 决定，不是由平台判断。
#:
#: 这张表**一定会漏**——漏了就是 ``uncategorized``，那是一个有颜色有文案的
#: 合法类别，用户还能手工覆盖（``category_source='user'``）。首批约 50 条
#: 覆盖常用应用（19 文档 A3、20 文档 A3），按用户反馈增量补。
EXACT_BUNDLES: dict[str, str] = {
    # 开发
    "com.microsoft.vscode": "development", "com.apple.dt.xcode": "development",
    "com.googlecode.iterm2": "development", "com.apple.terminal": "development",
    "com.jetbrains.pycharm": "development", "com.jetbrains.intellij": "development",
    "com.todesktop.230313mzl4w4u92": "development",  # Cursor
    "com.sublimetext.4": "development", "com.docker.docker": "development",
    "com.postmanlabs.mac": "development", "dev.warp.warp-stable": "development",
    # 效率
    "com.apple.safari": "productivity", "com.google.chrome": "productivity",
    "com.microsoft.edgemac": "productivity", "org.mozilla.firefox": "productivity",
    "com.apple.iwork.pages": "productivity", "com.apple.iwork.numbers": "productivity",
    "com.apple.iwork.keynote": "productivity", "com.microsoft.word": "productivity",
    "com.microsoft.excel": "productivity", "com.microsoft.powerpoint": "productivity",
    "md.obsidian": "productivity", "abnerworks.typora": "productivity",
    "notion.id": "productivity", "com.figma.desktop": "productivity",
    "com.apple.preview": "productivity", "com.apple.notes": "productivity",
    "com.adobe.acrobat.pro": "productivity",
    # 沟通
    "com.tencent.xinwechat": "communication", "com.tencent.qq": "communication",
    "com.apple.mail": "communication", "ru.keepcoder.telegram": "communication",
    "com.hnc.discord": "communication", "com.tinyspeck.slackmacgap": "communication",
    "us.zoom.xos": "communication", "com.microsoft.teams2": "communication",
    "com.electron.lark": "communication",  # 飞书
    # 娱乐
    "com.spotify.client": "entertainment", "com.netease.163music": "entertainment",
    "com.apple.music": "entertainment", "tv.danmaku.bilianime": "entertainment",
    "org.videolan.vlc": "entertainment", "io.mpv": "entertainment",
    "com.valvesoftware.steam": "entertainment",
    # 系统
    "com.apple.finder": "system", "com.apple.systempreferences": "system",
    "com.apple.activitymonitor": "system", "com.apple.dock": "system",
    "com.apple.spotlight": "system",
}

#: .desktop id → 类别。Linux 的应用身份是 .desktop 文件 id（M8 填，19 文档 A3）。
EXACT_DESKTOP_IDS: dict[str, str] = {}

#: （identity_kind → 精确表）。哪张表由数据决定，不由平台名决定。
EXACT_BY_KIND: dict[str, dict[str, str]] = {
    "process": EXACT_PROCESSES,
    "bundle": EXACT_BUNDLES,
    "desktop": EXACT_DESKTOP_IDS,
}


def _stem(process_name: str) -> str:
    """``"Code.exe"`` → ``"code"``。仅用于**进程名**口径。

    bundle id 的 ``.app`` 后缀是 id 的一部分（``com.foo.app`` 剥掉后缀就成了
    ``com.foo``，查的是一张错误的表），因此剥离只发生在进程名上。
    """
    name = (process_name or "").strip().casefold()
    for suffix in (".exe", ".app"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def categorize(
    display_name: str = "", process_name: str = "", identity_kind: str = "process"
) -> str:
    """自动分类。**永不抛异常**，认不出来就是 ``uncategorized``。

    "认不出来"必须是一个有名字的类别而不是空字符串：``uncategorized`` 在 UI 上有自己的
    颜色与文案（06 文档 §3.1），而空字符串会让分类饼图多出一块没有图例的扇形。

    ``identity_kind`` 决定查哪张精确表——它是随每一行 ``app`` 一起存进数据库的
    事实（03 文档 §2.2 的三元组身份），不是平台判断。默认 ``"process"`` 保住
    全部既有调用点与 Windows 行为。
    """
    if identity_kind == "process":
        key = _stem(process_name)
    else:
        # bundle / desktop id 整串就是键，不剥任何后缀。
        key = (process_name or "").strip().casefold()
    exact = EXACT_BY_KIND.get(identity_kind, {}).get(key)
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
    "EXACT_BUNDLES",
    "EXACT_BY_KIND",
    "EXACT_DESKTOP_IDS",
    "EXACT_PROCESSES",
    "KEYWORD_RULES",
    "UNCATEGORIZED",
    "catalog",
    "categorize",
    "is_known",
    "name_of",
]
