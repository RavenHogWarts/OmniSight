"""生成第三方许可清单（10 文档 §1.2）。

两份产物，与两个原项目沿用的做法一致：

* ``THIRD_PARTY_NOTICES.md`` —— 人类可读的表格：包名、版本、许可、项目地址。
* ``THIRD_PARTY_LICENSES.txt`` —— 完整许可正文的拼接，这份才是**法律上要随产物
  分发的东西**（MIT / BSD / Apache 都要求保留许可与版权声明）。

**不用 ``pip-licenses`` 的库形态，直接读 ``importlib.metadata``。** 理由是可复现：
``pip-licenses`` 的输出格式在小版本间变过，而它的数据源就是这里读的同一批元数据。
CI 里仍然跑 ``pip-licenses --fail-on=GPL``（那是一道独立的门禁），但**产物的生成
不依赖它**——发布物的内容不该随一个开发期工具的版本漂移。

**只收真正会随产物分发的包。** 环境标记决定了 Windows 上根本不会装 pyobjc /
python-xlib，把它们列进清单等于声称分发了没分发的东西；反过来，开发依赖
（pytest / ruff / pyinstaller）也不在产物里。因此清单从 ``requirements.txt`` +
``requirements-optional.txt`` 出发算**依赖闭包**（含传递依赖），而不是把当前
环境里 ``pip list`` 的一切都倒出来。
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
NOTICES = ROOT / "THIRD_PARTY_NOTICES.md"
LICENSES = ROOT / "THIRD_PARTY_LICENSES.txt"

if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from omnisight import APP_NAME, __version__  # noqa: E402

#: 产物里会包含的依赖清单文件。开发依赖（requirements-dev.txt）刻意不在其中。
REQUIREMENT_FILES = ("requirements.txt", "requirements-optional.txt")

#: 红线：**强著佐权**（GPL / AGPL）与本项目的分发方式（单文件 EXE 静态打包）不相容，
#: 出现即构建失败而不是"发出去再说"。
#:
#: **LGPL 刻意不在红线上**，理由要写清楚而不是留给正则去猜：托盘（pystray）与键盘
#: 兜底（pynput）都是 LGPLv3 且无可替代，两个旧项目多年随产物分发它们并写入清单；
#: LGPL 的"用户可替换该库"义务在这里由 **OmniSight 自身 MIT 开源 + 完整构建脚本
#: 公开**满足——任何人都可以检出源码、改掉 LGPL 组件后重新打包。清单（NOTICES）
#: 里为此有一段专门的说明。
#:
#: 匹配用 ``(?<![A-Za-z])`` 而不是 ``\b``：``\bGPL\b`` 对 "GPLv3" 不命中（v 是
#: 单词字符，边界不成立），写在那里的门禁实际拦不住它要拦的东西。
FORBIDDEN_LICENSE_PATTERN = re.compile(r"(?<![A-Za-z])(?:AGPL|GPL)", re.IGNORECASE)

#: 许可/版权类文件的名字。**按文件名匹配，不按路径**：新式 wheel 把正文放在
#: ``dist-info/licenses/`` 下，老式直接放 ``dist-info/`` 根，pywin32 这类甚至放在包
#: 目录里（``win32/license.txt``）。写死任一位置都会漏掉另外两种。
LICENSE_NAME_PATTERN = re.compile(r"^(licen[cs]e|copying|copyright|notice|authors)", re.IGNORECASE)

#: 同一个包里多份文件的顺序：许可正文在前，版权/致谢一类的附属声明在后。
LICENSE_NAME_RANK = ("licen", "copying", "copyright", "notice", "authors")

#: 明显不是许可正文的后缀。``^licen[cs]e`` 会命中 ``licenses.py``——把一段 Python
#: 源码印进许可文件是很难看的错，而它只在真的发生时才会被发现。
NON_TEXT_SUFFIXES = frozenset(
    {".py", ".pyc", ".pyi", ".pyd", ".so", ".dylib", ".dll", ".exe", ".json", ".cfg", ".ini",
     ".toml", ".yaml", ".yml"}
)

#: 与 FORBIDDEN_LICENSE_PATTERN 同一口径：弱著佐权（LGPL）允许，但必须在清单里
#: 挂上义务说明（见 :func:`render_notices`）。
LGPL_PATTERN = re.compile(r"(?<![A-Za-z])LGPL", re.IGNORECASE)

#: 许可**正文**里的 LGPL 标题。只用来补充义务说明，**绝不喂给 FORBIDDEN 门禁**：
#: LGPLv3 的定义是"GPLv3 + 附加许可"，所以 pystray 这类包会如实随附一份 GPL 正文
#: ——按正文判强著佐权会把它误杀，而它是托盘的唯一实现。
#:
#: 它抓的是另一类漏网：pywin32 的元数据只写 PSF，而它的 wheel 里捆着 LGPL-2.1 的
#: adodbapi。按标识判的话，这条义务在清单上完全看不见。
#:
#: **必须是独占一行的标题、且出现在文件开头附近**，不能只判"出现过这个短语"：
#: Pillow 的 LICENSE 里转载了 XZ Utils 的一段文档，其中逐条列出
#: ``- COPYING.LGPLv2.1: GNU Lesser General Public License version 2.1``——那是一句
#: 说明文字，不是许可本身。宽松匹配会让清单多出一条**不实的** LGPL 义务声明，
#: 而这份文件的全部价值就在于每一句都为真（实测踩到）。
LGPL_TITLE_PATTERN = re.compile(
    r"^[ \t]*(?:GNU[ \t]+)?LESSER[ \t]+GENERAL[ \t]+PUBLIC[ \t]+LICENSE",
    re.IGNORECASE | re.MULTILINE,
)

#: 只在正文开头这么多字符里找标题。许可文件的标题总在最前面，而转载、附录、
#: "另见"一类的提及总在后面。
LGPL_TITLE_WINDOW = 1500



#: 标准库与打包工具自身，不属于"第三方依赖"。
IGNORED = frozenset({"pip", "setuptools", "wheel", "omnisight"})

#: ``Project-URL`` 标签的优先级分档，标签按 ``[^a-z]`` 剔除后比对
#: （``Source Code`` → ``sourcecode``）。
URL_LABEL_TIERS = (
    frozenset({"homepage", "home", "homepage2", "website", "site"}),
    frozenset({"repository", "repo", "source", "sources", "sourcecode", "code", "github"}),
    frozenset({"documentation", "docs", "doc"}),
    frozenset({"download", "releases"}),
)

#: 许可正文文件的分节宽度。80 列是纯文本文件的通行宽度——这份文件会在记事本里被读。
RULE = "=" * 80

#: 元数据里没有任何许可声明时的占位。**不留空**：清单里的空白会被读成"漏了一项"，
#: 而这里的事实是"上游没写"——两者对合规审查的含义完全不同。
UNDECLARED = "未声明"




@dataclass(frozen=True, slots=True)
class Package:
    name: str
    version: str
    license_name: str
    homepage: str
    #: 随 wheel 分发的许可文件：``((相对路径, 正文), …)``。**存结构而不是拼好的字符串**，
    #: 这样"哪个文件里出现了 LGPL"这类问题不必回头解析自己的排版。
    license_files: tuple[tuple[str, str], ...] = ()

    @property
    def license_text(self) -> str:
        """许可正文：多份按序拼接，每份带一行来源标注。没有正文时是空字符串——
        "未随附"的说明文案属于渲染层，塞进数据里就等于让这个字段谎称自己是正文。
        """
        return "\n\n".join(f"--- {path} ---\n{text}" for path, text in self.license_files)

    @property
    def forbidden(self) -> bool:
        # 只看许可标识，不扫正文：正文里出现 "GPL" 的多数是"本许可与 GPL 兼容"
        # 这类说明句，按正文判会把 MIT 包全部误杀。
        return bool(FORBIDDEN_LICENSE_PATTERN.search(self.license_name))

    @property
    def lgpl(self) -> bool:
        return bool(LGPL_PATTERN.search(self.license_name))

    @property
    def lgpl_components(self) -> tuple[str, ...]:
        """元数据没声明 LGPL、但随附正文里确有 LGPL 的那些文件。

        pywin32 就是这样：元数据只写 PSF，wheel 里却捆着 LGPL-2.1 的 adodbapi。
        它是否真进了 EXE 取决于 PyInstaller 的模块收集，但**清单按包粒度声明**，
        所以这条义务照样要在清单上看得见。
        """
        if self.lgpl:
            return ()
        return tuple(
            path
            for path, text in self.license_files
            if LGPL_TITLE_PATTERN.search(text[:LGPL_TITLE_WINDOW])
        )

    @property
    def declared(self) -> bool:
        return self.license_name != UNDECLARED

    @property
    def license_label(self) -> str:
        """索引那一行的显示。未声明时指向正文，免得读者以为清单漏了一项。"""
        return self.license_name if self.declared else f"{UNDECLARED}（见该节正文）"


def _normalize(name: str) -> str:
    """PEP 503 规范化：``Pillow`` / ``pillow`` / ``python_xlib`` 要能对上。"""
    return re.sub(r"[-_.]+", "-", name).lower()


def _requirement_names(paths: tuple[str, ...] = REQUIREMENT_FILES) -> set[str]:
    """从需求文件里取直接依赖名。

    **环境标记按当前解释器求值**，因此在 Windows 上跑得到 pywin32 + tzdata，
    在 Linux 上跑得到 python-xlib + evdev——清单描述的是"这次构建的产物"，
    而不是一份想象中的全平台并集。
    """
    names: set[str] = set()
    for filename in paths:
        path = ROOT / filename
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            requirement = line.split("#", 1)[0].strip()
            if not requirement or requirement.startswith("-"):
                continue
            name, marker = _split_marker(requirement)
            if marker is not None and not _marker_applies(marker):
                continue
            if name:
                names.add(_normalize(name))
    return names


def _split_marker(requirement: str) -> tuple[str, str | None]:
    head, _, marker = requirement.partition(";")
    name = re.split(r"[<>=!~\[]", head.strip(), maxsplit=1)[0].strip()
    return name, marker.strip() or None


def _marker_applies(marker: str) -> bool:
    try:
        from packaging.markers import Marker  # type: ignore[import-not-found]

        return bool(Marker(marker).evaluate())
    except Exception:
        # packaging 不可用时退回只认 sys_platform 的最小实现——本项目的标记
        # 全是这一种形态，而静默把不适用的包收进清单比抛错更糟。
        match = re.search(r'sys_platform\s*==\s*[\'"]([^\'"]+)[\'"]', marker)
        return match.group(1) == sys.platform if match else True


def _closure(direct: set[str]) -> list[str]:
    """把直接依赖展开成传递闭包（BFS）。分发的是整棵树，清单也必须是整棵树。"""
    seen: set[str] = set()
    order: list[str] = []
    queue = sorted(direct)
    while queue:
        name = queue.pop(0)
        if name in seen or name in IGNORED:
            continue
        seen.add(name)
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            # 环境里没装（例如可选依赖没安装）：跳过而不是编造一行。
            continue
        order.append(name)
        for requirement in dist.requires or ():
            child, marker = _split_marker(requirement)
            if not child:
                continue
            if marker is not None and (_is_extra_marker(marker) or not _marker_applies(marker)):
                continue
            queue.append(_normalize(child))
    return sorted(order)


def _is_extra_marker(marker: str) -> bool:
    """``extra == "dev"`` 这类可选组不随产物分发。"""
    return "extra" in marker


def _license_name(dist: metadata.Distribution) -> str:
    """许可标识。新旧元数据字段并存，逐个回退。"""
    meta = dist.metadata
    for key in ("License-Expression", "License"):
        value = meta.get(key)
        if value and len(value) < 200 and "\n" not in value:
            return value.strip()
    classifiers = [
        value.split("::")[-1].strip()
        for value in meta.get_all("Classifier") or ()
        if value.startswith("License ::")
    ]
    if classifiers:
        return "; ".join(dict.fromkeys(classifiers))
    return UNDECLARED


def _homepage(dist: metadata.Distribution) -> str:
    """项目地址。

    ``Project-URL`` 的标签没有统一写法（``Source`` / ``Sources`` / ``Source Code`` /
    ``Repository`` / ``Homepage``…），因此按**归一化后的标签**匹配并保留优先级：
    主页 > 代码仓库 > 文档 > 下载。逐字比对 ``"source"`` 的写法会让 cffi、clr_loader
    这类只提供 ``Source Code`` / ``Sources`` 的包在清单里显示"—"，而它们其实有地址
    ——清单里的空白会被读成"这个包查不到出处"。
    """
    meta = dist.metadata
    for key in ("Home-page", "Download-URL"):
        value = meta.get(key)
        if value:
            return value.strip()
    tiers: dict[int, str] = {}
    for entry in meta.get_all("Project-URL") or ():
        label, _, url = entry.partition(",")
        normalized = re.sub(r"[^a-z]", "", label.lower())
        for index, aliases in enumerate(URL_LABEL_TIERS):
            if normalized in aliases and index not in tiers and url.strip():
                tiers[index] = url.strip()
    return tiers[min(tiers)] if tiers else ""


def _license_files(dist: metadata.Distribution) -> list[tuple[str, str]]:
    """随 wheel 分发的许可文件：``[(相对路径, 正文), …]``。

    **必须用 ``PackagePath.locate()`` 读，不能用 ``dist.read_text()``。** 后者解析的是
    **dist-info 目录内**的相对路径，而 ``dist.files`` 给出的是**相对 site-packages** 的
    路径；把后者喂给前者永远找不到文件，而 ``read_text`` 吞掉 ``FileNotFoundError``
    只返回 ``None``——于是每个包都变成"wheel 未随附许可正文"。这是最坏的一种失败：
    它不报错，只是安静地把一项分发义务从发布物里删掉（M6 实测 22 个包全军覆没，
    而当时的测试因为接受兜底文案而全绿）。

    去重按**正文内容**：pywin32 在四个包目录里各放了一份一模一样的 ``license.txt``，
    照抄四遍只会让读者以为自己看错了。
    """
    declared = {name.strip() for name in (dist.metadata.get_all("License-File") or ())}
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    for entry in sorted(dist.files or (), key=_license_file_rank):
        name = PurePosixPath(str(entry)).name
        if name not in declared and not LICENSE_NAME_PATTERN.match(name):
            continue
        if PurePosixPath(name).suffix.lower() in NON_TEXT_SUFFIXES:
            continue
        try:
            text = entry.locate().read_text(encoding="utf-8", errors="replace")
        except OSError:  # pragma: no cover - 文件被删/无权限
            continue
        text = text.replace("\r\n", "\n").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        found.append((str(entry), text))
    return found


def _license_file_rank(entry: object) -> tuple[int, str]:
    name = PurePosixPath(str(entry)).name.lower()
    for index, prefix in enumerate(LICENSE_NAME_RANK):
        if name.startswith(prefix):
            return (index, str(entry))
    return (len(LICENSE_NAME_RANK), str(entry))




def collect() -> list[Package]:
    packages: list[Package] = []
    for name in _closure(_requirement_names()):
        dist = metadata.distribution(name)
        packages.append(
            Package(
                name=dist.metadata.get("Name") or name,
                version=dist.version,
                license_name=_license_name(dist),
                homepage=_homepage(dist),
                license_files=tuple(_license_files(dist)),
            )
        )
    return packages


def render_notices(packages: list[Package]) -> str:
    rows = "\n".join(
        f"| {pkg.name} | {pkg.version} | {pkg.license_name} | "
        f"{f'<{pkg.homepage}>' if pkg.homepage else '—'} |"
        for pkg in packages
    )
    lgpl = [pkg for pkg in packages if pkg.lgpl]
    names = "、".join(pkg.name for pkg in lgpl)
    lgpl_note = (
        f"\n下列 {len(lgpl)} 个包以 **LGPL** 系许可发布（{names}）。\n"
        "LGPL 要求用户能够替换这些库；OmniSight 自身以 MIT 开源且构建脚本完整公开\n"
        "（`tools/build.py`），因此这一义务的行使方式是：检出源码、修改或替换对应库、\n"
        "重新构建。GPL/AGPL 系许可的依赖会被构建直接拒绝，与此不同。\n"
        if lgpl
        else ""
    )
    # 元数据没写 LGPL、但 wheel 里确实捆着 LGPL 组件的包（pywin32 的 adodbapi）。
    # 义务不看元数据写了什么，所以这一段必须自动生成——手写的话，换个依赖版本就忘了。
    bundled = [pkg for pkg in packages if pkg.lgpl_components]
    bundled_note = (
        f"\n另有 {len(bundled)} 个包的元数据没声明 LGPL，但其 wheel 里随附了 LGPL 许可正文：\n\n"
        + "".join(
            f"- **{pkg.name}**（元数据写 {pkg.license_name}）："
            f"{'、'.join(f'`{path}`' for path in pkg.lgpl_components)}\n"
            for pkg in bundled
        )
        + "\n这些组件是否真的进了 EXE 取决于 PyInstaller 的模块收集，但本清单按**包**\n"
        "粒度声明，因此同一条 LGPL 义务照样列在这里。\n"
        if bundled
        else ""
    )
    undeclared = [pkg for pkg in packages if not pkg.declared]
    undeclared_note = (
        f"\n有 {len(undeclared)} 个包的元数据未声明许可标识"
        f"（{'、'.join(pkg.name for pkg in undeclared)}）。对应的许可正文随 wheel 分发，\n"
        "见 `THIRD_PARTY_LICENSES.txt` 里那一节——缺标识不等于缺许可。\n"
        if undeclared
        else ""
    )
    return f"""# 第三方声明

OmniSight 自身以 MIT 许可发布。发布物里静态包含了下列开源 Python 包；
它们各自的完整许可正文见同目录的 `THIRD_PARTY_LICENSES.txt`。

本文件由 `tools/licenses.py` 生成，请勿手改——依赖变化后重新生成。
清单只包含**随产物分发的**依赖（`requirements.txt` +
`requirements-optional.txt` 的传递闭包，按当前平台的环境标记求值）；
开发期依赖（pytest / ruff / PyInstaller 等）不在其中。

| 包 | 版本 | 许可 | 项目地址 |
| --- | --- | --- | --- |
{rows}

共 {len(packages)} 个包。
{lgpl_note}{bundled_note}{undeclared_note}"""


def render_licenses(packages: list[Package]) -> str:
    """拼出 ``THIRD_PARTY_LICENSES.txt``：索引 + 每包一节的许可正文。

    结构是刻意规整的，因为这份文件的读者有两类，需求相反：**律师/合规审查**要能
    按包名跳到对应正文（所以有编号索引与统一的字段），**普通用户**只是想确认
    "这里面装了什么"（所以第一屏就是全部包名）。正文本身逐字照抄，不换行不缩进
    ——许可文本的措辞不允许被"排版"。
    """
    index = "\n".join(
        f"  {number:>3}. {pkg.name} {pkg.version} —— {pkg.license_label}"
        for number, pkg in enumerate(packages, start=1)
    )
    sections = [_render_license_section(number, pkg) for number, pkg in enumerate(packages, 1)]
    return f"""{RULE}
{APP_NAME} {__version__} —— 第三方许可正文
{RULE}

本文件由 tools/licenses.py 生成，请勿手改——依赖变化后重新生成。

下列许可适用于随 {APP_NAME} 发布物**静态包含**的第三方 Python 包。清单为
requirements.txt + requirements-optional.txt 的传递闭包，按当前平台的环境标记
求值；开发期依赖（pytest / ruff / PyInstaller 等）不随产物分发，不在其中。

{APP_NAME} 自身以 MIT 许可发布，见同目录的 LICENSE。
包名、版本、许可标识与项目地址的表格见 THIRD_PARTY_NOTICES.md。

共 {len(packages)} 个包：

{index}

每一节给出该包的许可标识、项目地址，以及**随 wheel 分发的许可文件原文**
（以 "--- 路径 ---" 标出来源）。少数包的 wheel 未随附正文文件，该节会明确
说明并给出项目地址。

{"".join(sections)}"""


def _render_license_section(number: int, pkg: Package) -> str:
    body = pkg.license_text or (
        "（此包的 wheel 未随附许可正文文件。许可标识见上，完整正文见项目地址；\n"
        " 若上面的项目地址也为空，请按包名在 PyPI 上查该版本的源码分发。）"
    )
    declared = (
        f"许可标识：{pkg.license_name}"
        if pkg.license_name != UNDECLARED
        else f"许可标识：{UNDECLARED}（元数据里没有，以下正文为准）"
    )
    return f"""
{RULE}
{number}. {pkg.name} {pkg.version}
{RULE}
{declared}
项目地址：{pkg.homepage or "（元数据未提供）"}

{body}
"""



def generate(
    *, notices: Path = NOTICES, licenses: Path = LICENSES
) -> tuple[list[Package], list[Package]]:
    """写两份文件，返回 ``(全部包, 违规包)``。

    违规不阻止写文件——由调用方决定退出码。
    """
    packages = collect()
    notices.write_text(render_notices(packages), encoding="utf-8")
    # 显式 CRLF：这份文件随 zip 分发，读它的人用 Windows 记事本；隐式换行还会让
    # 同一次构建在 Windows 与 Linux 上产出字节不同的文件（M8/M9 会在两处构建）。
    licenses.write_text(render_licenses(packages), encoding="utf-8", newline="\r\n")
    return packages, [pkg for pkg in packages if pkg.forbidden]


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    packages, forbidden = generate()
    outputs = f"{NOTICES.relative_to(ROOT)} 与 {LICENSES.relative_to(ROOT)}"
    print(f"已生成 {outputs}（{len(packages)} 个包）")
    for pkg in packages:
        marker = "" if pkg.license_text else "  ← wheel 未随附正文"
        print(f"  {pkg.name} {pkg.version} — {pkg.license_name}{marker}")
    if forbidden:
        print("\n发现不相容的许可（GPL 系与单文件静态打包不相容）：", file=sys.stderr)
        for pkg in forbidden:
            print(f"  {pkg.name} {pkg.version}: {pkg.license_name}", file=sys.stderr)
        return 1
    # 下面两类不判失败，但每次都要说出来：它们需要人看一眼，而不是靠"下次注意"。
    if undeclared := [pkg for pkg in packages if not pkg.declared]:
        names = "、".join(f"{pkg.name} {pkg.version}" for pkg in undeclared)
        print(f"\n提醒：{len(undeclared)} 个包的元数据未声明许可标识（{names}）——已在清单里点名。")
    if missing := [pkg for pkg in packages if not pkg.license_text]:
        names = "、".join(f"{pkg.name} {pkg.version}" for pkg in missing)
        print(
            f"提醒：{len(missing)} 个包的 wheel 未随附许可正文（{names}）。"
            "MIT/BSD/Apache 都要求随分发保留许可正文，发布前请确认是否需要手工补入。"
        )
    if "--check" in argv:
        print("许可检查通过：无 GPL 系依赖")
    return 0


if __name__ == "__main__":
    # 见 tools/_console.py：runner 上 stdout 是管道，按 locale 挑到 cp1252，
    # 一行中文输出就能让进程死在 UnicodeEncodeError 上。
    from _console import use_utf8_output

    use_utf8_output()
    sys.exit(main())
