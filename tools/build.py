"""PyInstaller 打包与发布物组装（10 文档 §2.1、§10）。

**这是允许出现 ``sys.platform`` 判断的少数地方之一**：它是构建脚本而非运行时代码，
不受 02 文档 §1 那条约束管辖。约束的目标是防止业务逻辑里散落平台分支，而打包
本身就是平台特定的操作。

结构刻意是"通用参数 + 平台补丁"，不是三份独立脚本——三份脚本会各自漂移，
而真正的差异只有下面这几行。

M6 起本脚本不止能产出 EXE，还能产出**可以直接交给别人的一整套东西**（10 文档 §10）：
便携 zip、它的校验值、许可清单，以及那份"不看仓库 README 也能上手"的 ``README.txt``。
理由很直接：任何需要人手动补一步的发布流程，都会在某一次发布时漏掉那一步。
代码签名（可选，§2.3）同样接在这条流水线上，且**排在算校验值之前**——顺序颠倒
就会发出一份校验不上的产物。

两条与"默认行为"有关的决定（都写成默认，因为默认值决定了人们实际怎么用它）：

* **默认只构建 EXE，不组装发布物。** 本地一天要构建好几次，而组装只有发布那一次
  用得上。组装用 ``--release``（或 ``--assemble-only`` 复用已有 EXE）。
* **发布两件产物：便携 zip 与安装包。** 分工不是"要不要安装步骤"（那道题确实没有
  实质内容，M6 因此只发 zip），而是**安装位置**：规划中的「登录时以管理员身份启动」
  要求 EXE 位于普通用户不可写的目录，否则那条无提示提权的启动项就成了一条静默的
  管理员通道（§5.2 的取舍表）。装进 Program Files 是便携包做不到的事，于是安装包
  有了实质理由——**那个开关本身排在安装包之后交付**（12 文档 M7）。
  ``dist/OmniSight.exe`` 仍然只是构建产物：裸 EXE 带不走许可正文与说明。
"""

from __future__ import annotations

import hashlib
import os
import shutil
import string
import subprocess
import sys
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
BUILD = ROOT / "build"

if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from omnisight import APP_NAME, __version__  # noqa: E402

#: PyInstaller 的历史包袱：``--add-data`` 的分隔符在 Windows 上是 ``;``，其余是 ``:``。
#: 硬编码任一形式都会让另一个平台构建失败，且报错信息毫无指向性。
SEP = ";" if sys.platform == "win32" else ":"

PKG = "src/omnisight"

#: 便携版数据目录的开关文件（10 文档 §2.2）。它**只进 zip**，不留在 ``dist/`` 里——
#: 留一份在 ``dist/`` 意味着谁手动双击 ``dist/OmniSight.exe`` 都会以便携模式跑，
#: 数据落进 ``dist/data/``，而下一次构建的清理逻辑必须为它绕路（见 ``_clean_dist``）。
#: 冒烟测试需要它时自己创建、自己删除（``tools/smoke.py``）。
PORTABLE_MARKER = "portable.marker"
PORTABLE_MARKER_TEXT = (
    "存在此文件时，OmniSight 把数据写在同级 data/ 目录，而不是系统的用户数据目录。\n"
    "删掉它，数据就回到 %LOCALAPPDATA%\\OmniSight\\（已有的 data/ 不会被搬走）。\n"
)

COMMON = [
    # 入口是根目录的 main.py，不是包内的 __main__.py：后者用相对导入，
    # 而 PyInstaller 以顶层脚本方式执行入口，没有父包可用。见 main.py 的说明。
    "main.py",
    "--name=OmniSight",
    "--noconsole",
    "--noconfirm",
    f"--paths={ROOT / 'src'}",
    f"--add-data={PKG}/presentation/templates{SEP}omnisight/presentation/templates",
    f"--add-data={PKG}/presentation/static{SEP}omnisight/presentation/static",
    f"--add-data=assets/omnisight.png{SEP}omnisight/presentation/static/assets",
    "--exclude-module=tkinter",
    "--exclude-module=unittest",
    "--exclude-module=pytest",
]

PLATFORM: dict[str, list[str]] = {
    "win32": [
        "--onefile",
        "--icon=assets/omnisight.ico",
        # tzdata 必须显式收集，否则 ZoneInfo 在打包后找不到时区库。
        "--collect-data=tzdata",
        # 管理员模式下降权打开仪表盘要借桌面 shell 的 IShellDispatch2（COM，见
        # adapters/windows/elevation.py 的 shell_dispatch）。这两个模块是惰性导入的，
        # 而漏了它们**不会让程序崩**——只会让提权状态下的浏览器悄悄跟着提权。这种缺失
        # 谁都发现不了，所以显式写上而不是指望静态分析扫到函数体里那两行 import。
        "--hidden-import=pythoncom",
        "--hidden-import=win32com.client.dynamic",
    ],
    "darwin": [
        # 不用 --onefile：TCC（隐私权限）记录绑定 bundle id + 签名，而 onefile 每次
        # 运行都解压到新的临时目录，会让"输入监控"授权行为变得不可预期（M9 生效）。
        "--windowed",
        "--icon=assets/omnisight.icns",
        "--osx-bundle-identifier=com.ravenhogwarts.omnisight",
    ],
    "linux": ["--onefile"],
}


def _version_resource() -> list[str]:
    """Windows 的版本资源（10 文档 §2.2）。

    生成而非手写：版本号的真源是 ``omnisight.__version__``，手写一份必然漂移，
    而"属性页显示 0.1.0、程序自报 0.2.0"这种不一致只有在用户报错时才会被发现。
    仅 Windows 有此概念——``--version-file`` 在其他平台被 PyInstaller 忽略，
    但生成一个没人用的文件是噪声，所以按平台产出。
    """
    if sys.platform != "win32":
        return []
    # tools/ 未必在 sys.path 上（本模块也可能被当作 ``tools.build`` 导入）。
    if str(Path(__file__).resolve().parent) not in sys.path:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
    from version_info import write as write_version_info

    target = write_version_info(BUILD / "version_info.txt")
    return [f"--version-file={target}"]


def build(
    *,
    clean: bool = True,
    exclude_pynput: bool = False,
    assemble_release: bool = False,
    installer: bool = True,
) -> int:
    """构建 EXE。**默认不组装发布物**（``assemble_release=False``）。

    日常开发一天要构建好几次，而组装那一套（重新生成许可清单、写 README.txt、打 zip、
    算两个大文件的 sha256）只有发布那一次用得上——默认做它等于每次本地构建都白等
    十几秒，还会把 ``dist/`` 弄成一个看不出"哪个才是刚构建出来的"的目录。
    发布时显式加 ``--release``。
    """
    if clean:
        _clean_dist()
        shutil.rmtree(BUILD, ignore_errors=True)
    BUILD.mkdir(parents=True, exist_ok=True)

    args = [*COMMON, *PLATFORM.get(sys.platform, ["--onefile"]), *_version_resource()]
    if exclude_pynput:
        # 精简变体：不含低级键盘钩子模块，代价是专用后端失败时无法降级
        # （10 文档 §1.1 的取舍）。
        args.append("--exclude-module=pynput")

    print("PyInstaller 参数：")
    for arg in args:
        print(f"  {arg}")
    completed = subprocess.run(
        [sys.executable, "-m", "PyInstaller", *args], cwd=ROOT, check=False
    )
    if completed.returncode != 0:
        return completed.returncode
    if assemble_release:
        assemble(installer=installer)
    else:
        exe = DIST / _executable_name()
        print(f"\n已构建 {exe}（{exe.stat().st_size / 1048576:.1f} MB）")
        print("这只是可执行文件；发布物（便携 zip + 安装包 + 校验值）用 --release 组装。")
    return 0


def _clean_dist() -> None:
    """清 ``dist/`` 但**保留 ``dist/data/``**。

    这是踩过的坑。``dist/portable.marker`` 一旦存在（冒烟测试会创建它），手动双击
    ``dist/OmniSight.exe`` 就以便携模式运行，数据落在 ``dist/data/``——而旧版这里
    一句 ``rmtree(DIST)`` 会把它连库一起删掉，且毫无提示。症状是"我明明跑了一下午，
    统计全没了"，而真正的原因在打包脚本里。

    与 M2 的 ``.bench/`` 是同一类问题（基准库原本落在 ``build/``，被下一次打包删掉），
    所以处理方式也一样：**构建产物目录里的用户数据一律不碰。**
    """
    if not DIST.exists():
        return
    data_dir = DIST / "data"
    for path in DIST.iterdir():
        if path == data_dir:
            print(f"保留 {path}（便携模式的数据目录，打包不碰它）")
            continue
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)


def _write_portable_marker(target: Path) -> Path:
    """数据放同级还是放 %LOCALAPPDATA%，区别只有这个标记文件（10 文档 §2.2）。

    发布包里预置它，所以发布形态默认是便携的；用户删掉它就回到平台惯例路径。
    """
    target.write_text(PORTABLE_MARKER_TEXT, encoding="utf-8")
    return target


# ── 代码签名（10 文档 §2.3）──────────────────────────────────────────────

#: 签名配置**只从环境变量读**，不做命令行参数：证书口令一旦进了 shell 历史或 CI
#: 日志，补救办法只有吊销证书重签。同理，未配置时构建照常进行——签名是可选项
#: （§2.3 的表格：Windows 上"可选"），把它做成硬前置会让没有证书的人无法自行构建。
SIGNTOOL_ENV = "OMNISIGHT_SIGNTOOL"
SIGN_THUMBPRINT_ENV = "OMNISIGHT_SIGN_THUMBPRINT"
SIGN_PFX_ENV = "OMNISIGHT_SIGN_PFX"
SIGN_PASSWORD_ENV = "OMNISIGHT_SIGN_PASSWORD"
SIGN_TIMESTAMP_ENV = "OMNISIGHT_SIGN_TIMESTAMP_URL"

#: 时间戳服务器。**没有时间戳的签名会随证书一起过期**，而已经发出去的产物不会
#: 重签——那时用户看到的是"签名已过期"，比从未签名更像出了问题。
DEFAULT_TIMESTAMP_URL = "http://timestamp.digicert.com"


@dataclass(frozen=True, slots=True)
class Signing:
    """一次 ``signtool sign`` 调用的完整配置。"""

    tool: str = "signtool"
    thumbprint: str = ""
    pfx: str = ""
    password: str = ""
    timestamp_url: str = DEFAULT_TIMESTAMP_URL

    def command(self, exe: Path) -> list[str]:
        """``/fd sha256`` 是摘要算法，``/td sha256`` 是时间戳的摘要算法——两个都得给，
        只给前者的签名在 Windows 上仍按 SHA-1 时间戳处理。
        """
        args = [self.tool, "sign", "/fd", "sha256"]
        if self.thumbprint:
            # 证书在本机证书存储里：只给指纹，私钥不出机器（硬件令牌同理）。
            args += ["/sha1", self.thumbprint]
        else:
            args += ["/f", self.pfx]
            if self.password:
                args += ["/p", self.password]
        if self.timestamp_url:
            args += ["/tr", self.timestamp_url, "/td", "sha256"]
        return [*args, str(exe)]

    def describe(self, exe: Path) -> str:
        """可以打印的形式：口令替换成 ``***``。构建日志会被贴进 issue。"""
        parts = self.command(exe)
        if self.password:
            parts = ["***" if part == self.password else part for part in parts]
        return " ".join(parts)


def signing_from_env(env: Mapping[str, str] | None = None) -> Signing | None:
    """按环境变量决定这次构建是否签名。两者都没给就是"不签名"。"""
    env = os.environ if env is None else env
    thumbprint = env.get(SIGN_THUMBPRINT_ENV, "").strip()
    pfx = env.get(SIGN_PFX_ENV, "").strip()
    if not (thumbprint or pfx):
        return None
    return Signing(
        tool=env.get(SIGNTOOL_ENV, "").strip() or "signtool",
        thumbprint=thumbprint,
        pfx=pfx,
        password=env.get(SIGN_PASSWORD_ENV, ""),
        timestamp_url=env.get(SIGN_TIMESTAMP_ENV, DEFAULT_TIMESTAMP_URL).strip(),
    )


def sign(exe: Path, config: Signing) -> None:
    """给 EXE 签名。**失败即中止构建，绝不退化成"不签名照发"。**

    配置了证书却发出未签名产物，是最坏的一种失败：校验值照样对得上，属性页却
    没有签名者，而发布页上写着"已签名"。宁可构建红掉。
    """
    print(f"签名：{config.describe(exe)}")
    try:
        completed = subprocess.run(config.command(exe), check=False)
    except FileNotFoundError as error:  # signtool 不在 PATH 上
        raise SystemExit(
            f"找不到 {config.tool}（Windows SDK 的 signtool.exe）——"
            f"用 {SIGNTOOL_ENV} 指向它的完整路径，或清空签名配置以发布未签名产物"
        ) from error
    if completed.returncode != 0:
        raise SystemExit(f"signtool 失败（退出码 {completed.returncode}）：构建中止，产物未签名")


# ── 发布物组装（10 文档 §10）────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Artifact:
    """一件可下载的产物及其校验值。"""

    path: Path
    digest: str

    @property
    def size(self) -> int:
        return self.path.stat().st_size

    def describe(self) -> str:
        return f"{self.path.name}  {self.size / 1048576:.1f} MB  sha256={self.digest[:16]}…"


#: 随产物分发、且必须与 EXE 放在一起的文件。缺哪一份都不是"少个附件"：
#: 许可正文是分发义务，``config.example.json`` 是端口冲突时用户唯一的参照。
RELEASE_FILES = (
    "config.example.json",
    "THIRD_PARTY_NOTICES.md",
    "THIRD_PARTY_LICENSES.txt",
    "LICENSE",
)

#: 便携 zip 的内容。EXE 与标记文件另外注入（前者是产物，后者是生成的）。
PORTABLE_EXTRAS = ("README.txt", *RELEASE_FILES)

USAGE = """用法：python tools/build.py [选项]

  （无选项）        只构建 EXE，落在 dist/。日常开发用这个。
  --release        构建后再组装发布物：便携 zip + 安装包 + 校验值 + 重新生成许可清单。
  --assemble-only  跳过 PyInstaller，只用现有的 dist/ 里的 EXE 重新组装发布物。
  --no-installer   组装时跳过安装包（只出便携 zip）。没装 Inno Setup 时用它。
  --no-clean       不清 dist/ 与 build/（增量重建，偶尔用于排查打包问题）。
  --exclude-pynput 精简变体：不打包 pynput（代价见 10 文档 §1.1）。

发布物两件：便携 zip 与安装包。分工是**安装位置**——安装版进 Program Files（普通用户
不可写），规划中的「登录时以管理员身份启动」只能指向它；便携版解压即用。裸 EXE 不发布，
它带不走许可正文与说明（LICENSE、清单四件套、README.txt 随两件产物分发）。

安装包需要 Inno Setup 的 ISCC.exe：自动找不到时用 OMNISIGHT_ISCC 指向它。"""


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _executable_name() -> str:
    return f"{APP_NAME}.exe" if sys.platform == "win32" else APP_NAME


def portable_name() -> str:
    return f"{APP_NAME}-portable.zip"


def installer_name() -> str:
    return f"{APP_NAME}-Setup.exe"


def artifact_names() -> tuple[str, ...]:
    """要留证的全部文件：``(EXE, 便携 zip, 安装包)``。

    公开是为了让 ``tools/scan_record.py`` 按**同一份名单**找文件。名字在两处各写
    一遍的话，改名那天扫描记录会静默少一行——而"少一行"看起来和"这件产物没问题"
    一模一样。
    """
    return (_executable_name(), portable_name(), installer_name())


def published_names() -> tuple[str, ...]:
    """真正发出去的两件：便携 zip 与安装包（10 文档 §10）。

    ``dist/`` 里的裸 EXE 不在其中——它带不走许可正文与说明。两件产物的分工是
    **安装位置**：安装版进 Program Files（普通用户不可写），因此它是"登录时以管理员
    身份启动"唯一可以指向的目标；便携版解压即用，那个开关在它上面是禁用的。
    """
    return (portable_name(), installer_name())


def _default_port() -> int:
    from omnisight.core.config import default_config

    return default_config().server.port


def _readme_launch(exe: str, *, portable: bool) -> str:
    if portable:
        return f"双击 {exe}。"
    return f"从「开始」菜单打开 {APP_NAME}（或安装目录里的 {exe}）。"


def _readme_data(*, portable: bool) -> str:
    """"数据在哪"那一段。两种形态的答案不同，而这是用户最常问的一件事。"""
    if portable:
        return f"""本压缩包解压后是**便携模式**（同级有 portable.marker），数据在解压目录里：

    <解压目录>\\data\\omnisight.db     数据库
    <解压目录>\\logs\\                 运行日志与崩溃报告
    <解压目录>\\config.json            配置（首次启动时生成）

如果你想让数据按 Windows 惯例放在系统目录里，**删掉 portable.marker**，位置变成：

    %LOCALAPPDATA%\\{APP_NAME}\\

托盘 →「打开数据目录」直接跳过去，「打开日志目录」跳到日志。
已有的 data\\ 不会被自动搬走——要带走旧数据就自己复制过去。
"""
    return f"""安装版的数据与程序分开，放在系统的用户数据目录里：

    %LOCALAPPDATA%\\{APP_NAME}\\data\\omnisight.db   数据库
    %LOCALAPPDATA%\\{APP_NAME}\\logs\\               运行日志与崩溃报告
    %LOCALAPPDATA%\\{APP_NAME}\\config.json          配置（首次启动时生成）

托盘 →「打开数据目录」直接跳过去，「打开日志目录」跳到日志。
卸载时会问要不要一并删除这些数据，**默认保留**。

（发布页另有一份便携 zip：它把数据放在解压目录里，靠同级的 portable.marker 区分。）
"""


def _readme_uninstall(exe: str, *, portable: bool) -> str:
    """"怎么彻底卸载"是 10 文档 §10 的硬要求：记录按键的程序必须让用户知道怎么移除它。"""
    if portable:
        return f"""1. 托盘 →「退出」
2. 关掉开机自启：托盘取消勾选「开机自启」，或删掉注册表
   HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run 下的 {APP_NAME} 值
3. 删除数据目录（上面「数据在哪」给出的那两个位置之一）
4. 删除 {exe} 本身

程序不写系统目录、不装服务、不装驱动、不改系统设置。除上面第 2 条那个
自启项外不留任何注册表项。
"""
    return f"""1. 托盘 →「退出」
2.「设置 → 应用 → 已安装的应用」里找到 {APP_NAME} → 卸载
3. 卸载过程会问是否一并删除统计数据（**默认保留**，选「是」才删）

卸载程序会一并清掉程序写的开机自启项（注册表 HKCU 的 Run 下那一个值）。
程序不装服务、不装驱动、不改系统设置，除那个自启项外不留任何注册表项。
"""


def render_readme(
    *,
    version: str = __version__,
    port: int | None = None,
    signed: bool = False,
    portable: bool = True,
) -> str:
    """随产物分发的 ``README.txt``（10 文档 §10）。

    它面向**完全没读过仓库 README 的人**：装完/解压出来只有一个 EXE 和这份文本，
    因此四件事必须自足——怎么启动、数据在哪、怎么暂停、**怎么彻底卸载**。
    最后一件是 §10 的硬要求：一个记录按键的程序，必须让用户清楚知道怎么移除它。

    端口不写死，从配置默认值取：两处各写一个 6100，改端口那天就会剩下一个错的。

    ``signed`` 同理：这份文本里"本程序未做代码签名"那一句在签名构建里就是**假的**，
    而它出现在用户判断该不该信任这个程序的那一屏上。构建知道自己签没签，这句话
    因此由构建决定，不由人记得改（10 文档 §2.3）。

    ``portable`` 决定另外三段：启动方式、数据位置、卸载步骤。两种形态各发一份自己的
    README——把两套说明并排写进同一份文件，等于让每个用户先判断"我装的是哪一种"，
    而他手上只有一个 EXE。
    """
    port = port or _default_port()
    exe = _executable_name()
    archive = portable_name() if portable else installer_name()
    trust = (
        f"""本程序已用代码签名证书签名：右键 {exe} →「属性」→「数字签名」可以看到
签名者，Windows 不再显示 SmartScreen 的未知发布者警告。签名之外仍建议核对
校验值（签名证明"谁签的"，校验值证明"字节没被改过"）："""
        if signed
        else """本程序未做代码签名，Windows 可能显示 SmartScreen 警告，杀软也可能因为
"读键盘"这一行为把它标为可疑。下载后请核对校验值："""
    )
    return f"""OmniSight {version}
本地运行的应用使用时长 + 键盘使用统计工具。

数据只留在本机：无账号、不联网、无遥测。


启动
────────────────────────────────────────────────────────────
{_readme_launch(exe, portable=portable)}程序常驻托盘（任务栏右下角），不会自己弹出窗口。

托盘图标 →「打开 OmniSight」在浏览器里打开仪表盘。地址是
http://127.0.0.1:{port}/，只监听本机回环地址，局域网访问不到。

仪表盘需要一个一次性令牌，托盘那一项会自动带上。直接手输地址会看到
401——这是有意的：它挡住的是任意网页对本机接口的读取。

首次打开时会显示一屏说明：记录什么、不记录什么、数据在哪、怎么暂停。
那屏内容是按你此刻的配置**算出来**的，不是固定文案。


数据在哪
────────────────────────────────────────────────────────────
{_readme_data(portable=portable)}

暂停记录
────────────────────────────────────────────────────────────
托盘 →「暂停记录」立即停止一切写入，图标同时变灰。暂停期间缓冲的事件被
丢弃，而不是延后落盘——你点暂停是希望这段不被记录，不是希望晚点记。

以管理员身份运行的程序（管理员模式的编辑器、终端、任务管理器）里敲的键，
普通权限的程序一个也收不到。需要统计它们时用托盘 →「以管理员身份重启」，
它只对本次运行有效。日常使用不需要管理员权限。


端口被占用
────────────────────────────────────────────────────────────
{port} 端口被占时程序**不会静默换端口**，而是报错退出并说明原因。改
config.json 里的 server.port（参照同目录的 config.example.json），或先关掉
占用它的程序（常见情况是上一个 OmniSight 还没退干净）。

启动失败且看不到任何提示时，看数据目录里的 STARTUP_ERROR.txt——无控制台
程序唯一的错误出口。


完全卸载
────────────────────────────────────────────────────────────
{_readme_uninstall(exe, portable=portable)}

平台支持
────────────────────────────────────────────────────────────
当前版本**只支持 Windows**（10 版本 1809 及以上 / 11）。macOS 与 Linux 在
规划中，**尚未实现**——程序的架构为它们留好了位置，但那不等于现在能用。


校验与安全提示
────────────────────────────────────────────────────────────
{trust}

    PowerShell> Get-FileHash .\\{archive} -Algorithm SHA256

与发布页上 {archive}.sha256 的内容比对（应完全一致）。校验的是你下载到的
那个文件；{exe} 本身不单独发布（裸 EXE 带不走这份说明与许可正文）。

杀软误报、Raw Input 权限、端口冲突的详细说明见仓库里的 docs/faq.md，
隐私边界的完整说明见 docs/privacy.md。


许可
────────────────────────────────────────────────────────────
OmniSight 自身以 MIT 许可发布（见 LICENSE）。随产物分发的第三方开源包
及其许可见 THIRD_PARTY_NOTICES.md 与 THIRD_PARTY_LICENSES.txt。
"""


def _regenerate_licenses() -> int:
    """重新生成许可清单。**每次发布都重新生成**：依赖版本变了而清单没变，
    等于分发了一份不实的声明（10 文档 §1.2）。
    """
    if str(Path(__file__).resolve().parent) not in sys.path:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
    import licenses

    packages, forbidden = licenses.generate()
    if forbidden:
        names = "、".join(f"{pkg.name}（{pkg.license_name}）" for pkg in forbidden)
        raise SystemExit(f"依赖里出现 GPL 系许可，与单文件静态打包不相容：{names}")
    print(f"已重新生成许可清单（{len(packages)} 个包）")
    return len(packages)


def assemble(
    *,
    dist: Path = DIST,
    exe: Path | None = None,
    regenerate_licenses: bool = True,
    installer: bool = True,
) -> list[Artifact]:
    """把 PyInstaller 的输出补成一套可以直接发出去的东西（10 文档 §10）。

    可单独调用（``python tools/build.py --assemble-only``），因此不假设自己
    紧跟在一次真实构建之后——测试就是这么用它的。

    **两件发布物：便携 zip 与安装包。** 裸 EXE 不在其中——它**带不走许可正文与说明**
    （LICENSE / 清单四件套 / README.txt 都随两件产物分发），而那几份是分发义务，不是
    附件。``dist/`` 里的 EXE 是构建产物，不是发布物。

    两件产物的分工是**安装位置**，不是"装还是不装"这道空题（M6 曾据此只发 zip，见
    偏离 110/117）：安装版进 Program Files，那是普通用户不可写的目录，因此它是
    规划中的"登录时以管理员身份启动"唯一可以指向的目标（10 文档 §5.2）；便携版
    解压即用，那个开关在它上面禁用。

    **随产物分发的东西在 ``build/portable/`` 与 ``build/installer/`` 里就位，不往
    ``dist/`` 里摊。** ``dist/`` 只放"要发出去的文件"，这样"哪些是发布物"由目录本身
    回答，而不是靠一份需要人记得的名单。``portable.marker`` 同理只进 zip：留一份在
    ``dist/`` 会让谁手动双击 ``dist/OmniSight.exe`` 都以便携模式跑，数据落进
    ``dist/data/``（见 :func:`_clean_dist`）。
    """
    exe = exe or dist / _executable_name()
    if not exe.exists():
        raise SystemExit(f"找不到构建产物 {exe}——先跑一次 python tools/build.py")
    dist.mkdir(parents=True, exist_ok=True)

    if regenerate_licenses:
        _regenerate_licenses()

    # 签名必须发生在**算校验值与打包之前**：签名会改写 EXE 的字节，先算摘要就等于
    # 发布一份对不上的校验值——而用户核对失败时的第一反应是"这个下载被篡改过"。
    signing = signing_from_env()
    if signing is not None:
        sign(exe, signing)
    else:
        print(
            f"未配置签名证书（{SIGN_THUMBPRINT_ENV} / {SIGN_PFX_ENV} 均为空）："
            "产物不签名，校验手段是随产物发布的 .sha256（10 文档 §2.3）"
        )

    staging = _stage_portable_files()
    archive = dist / portable_name()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.write(exe, exe.name)
        bundle.write(staging / PORTABLE_MARKER, PORTABLE_MARKER)
        for name in PORTABLE_EXTRAS:
            bundle.write(staging / name, name)

    published: list[Path] = [archive]
    if installer:
        setup = build_installer(dist)
        # 安装包本身也要签，且同样排在算摘要之前——它是用户真正双击的那个文件，
        # SmartScreen 首先看的也是它。
        if signing is not None:
            sign(setup, signing)
        published.append(setup)

    artifacts = [Artifact(path=path, digest=sha256_of(path)) for path in published]
    for artifact in artifacts:
        # sha256sum 兼容格式，同时 Get-FileHash 的输出也能人眼比对。
        (dist / f"{artifact.path.name}.sha256").write_text(
            f"{artifact.digest}  {artifact.path.name}\n", encoding="utf-8"
        )

    print(f"\n发布物已组装（{dist}）：")
    for artifact in artifacts:
        print(f"  {artifact.describe()}")
        print(f"  {artifact.path.name}.sha256")
    print(f"\nzip 内含：{_executable_name()}、{PORTABLE_MARKER}、{'、'.join(PORTABLE_EXTRAS)}")
    if installer:
        print(f"安装包装进 Program Files（不含 {PORTABLE_MARKER}，数据在 %LOCALAPPDATA%）")
    else:
        print("本次跳过安装包（--no-installer）")
    print(f"（{exe.name} 本身不单独发布——它带不走许可正文与说明）")
    return artifacts


def _stage_portable_files(staging: Path | None = None) -> Path:
    """把随 zip 分发的文件收进暂存目录，返回该目录。

    缺任何一件都直接失败：许可正文是分发义务，``config.example.json`` 是端口冲突时
    用户唯一的参照——"少个附件"这种说法在这里不成立。
    """
    staging = staging or BUILD / "portable"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)

    readme = staging / "README.txt"
    # 显式 CRLF：这份文件的读者用的是 Windows 记事本。
    readme.write_text(
        render_readme(signed=signing_from_env() is not None), encoding="utf-8", newline="\r\n"
    )
    _write_portable_marker(staging / PORTABLE_MARKER)

    missing = [name for name in RELEASE_FILES if not (ROOT / name).exists()]
    if missing:
        raise SystemExit(f"缺少随产物分发的文件：{'、'.join(missing)}")
    for name in RELEASE_FILES:
        shutil.copy2(ROOT / name, staging / name)
    return staging


# ── 安装包（10 文档 §10.1）──────────────────────────────────────────────

#: Inno Setup 的命令行编译器。**先看环境变量**：自动发现只能覆盖常见位置，而"我把
#: Program Files 放在 D 盘"这类机器上它一定失败，那时报错信息必须指向这个变量。
ISCC_ENV = "OMNISIGHT_ISCC"
ISCC_NAME = "ISCC.exe"
INSTALLER_SCRIPT = ROOT / "installer" / "omnisight.iss"


def _iscc_roots(env: Mapping[str, str]) -> list[Path]:
    """可能装着 Inno Setup 的目录。各分区的 ``Program Files`` 都看一眼——
    把它装在 D 盘并不罕见，而"找不到"对一个只想构建一次的人是纯粹的阻碍。
    """
    roots: list[Path] = []
    for key in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)"):
        value = env.get(key)
        if value:
            roots.append(Path(value))
    for letter in string.ascii_uppercase[2:]:  # 从 C 开始：A/B 是软驱年代的遗产
        drive = Path(f"{letter}:/")
        if not drive.exists():
            continue
        roots += [drive / "Program Files", drive / "Program Files (x86)"]
    return roots


def find_iscc(env: Mapping[str, str] | None = None) -> Path | None:
    """按三级顺序找 ``ISCC.exe``：环境变量 → ``PATH`` → 各分区的 Program Files。"""
    env = os.environ if env is None else env
    explicit = env.get(ISCC_ENV, "").strip().strip('"')
    if explicit:
        candidate = Path(explicit)
        if candidate.is_dir():
            candidate = candidate / ISCC_NAME
        # 显式指定却不存在时**不再自动回退**：那会让一个写错的路径表现为"用了另一个
        # 编译器"，而用户以为自己指定的那个生效了。
        return candidate if candidate.exists() else None
    on_path = shutil.which("ISCC")
    if on_path:
        return Path(on_path)
    for root in _iscc_roots(env):
        # 版本号倒序：装了多个版本时用新的那个。
        for path in sorted(root.glob(f"Inno Setup */{ISCC_NAME}"), reverse=True):
            return path
    return None


def _version_quad() -> str:
    """Windows 版本资源要的四元整数组，与 EXE 属性页里那份同源（``tools/version_info.py``）。"""
    if str(Path(__file__).resolve().parent) not in sys.path:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
    from version_info import file_version

    return ".".join(str(part) for part in file_version(__version__))


def _stage_installer_files(staging: Path | None = None) -> Path:
    """安装包要带的文件。与便携包**不是同一套**。

    三处不同，每一处都有理由：``README.txt`` 换成安装版的说法（数据位置与卸载步骤
    完全不同）；``LICENSE`` 复制成 ``LICENSE.txt`` 且转成 CRLF——Inno 的 ``LicenseFile``
    要一个带扩展名的文本文件，而它用 RichEdit 显示，只有 LF 的文本会挤成一行；
    **没有 ``portable.marker``**——装进 Program Files 之后同级目录不可写，带上它只会
    让程序把数据往一个写不进去的地方放，然后启动失败。
    """
    staging = staging or BUILD / "installer"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)

    (staging / "README.txt").write_text(
        render_readme(signed=signing_from_env() is not None, portable=False),
        encoding="utf-8",
        newline="\r\n",
    )
    missing = [name for name in RELEASE_FILES if not (ROOT / name).exists()]
    if missing:
        raise SystemExit(f"缺少随产物分发的文件：{'、'.join(missing)}")
    for name in RELEASE_FILES:
        source = ROOT / name
        if name == "LICENSE":
            (staging / "LICENSE.txt").write_text(
                source.read_text(encoding="utf-8"), encoding="utf-8", newline="\r\n"
            )
            continue
        shutil.copy2(source, staging / name)
    return staging


def build_installer(dist: Path = DIST, *, iscc: Path | None = None) -> Path:
    """编译安装包，返回产物路径。

    **找不到编译器就让构建红掉**，不静默跳过：``--release`` 是发布动作，而"少了一件
    产物"与"这次发布只有便携版"在 ``dist/`` 里长得一模一样。只想要便携版时显式写
    ``--no-installer``。
    """
    iscc = iscc or find_iscc()
    if iscc is None:
        raise SystemExit(
            "找不到 Inno Setup 的 ISCC.exe，安装包无法生成。\n"
            f"用 {ISCC_ENV} 指向它（例如 D:\\Program Files\\Inno Setup 7\\ISCC.exe），"
            "或加 --no-installer 只发布便携 zip"
        )
    if not INSTALLER_SCRIPT.exists():  # pragma: no cover - 仓库文件缺失
        raise SystemExit(f"找不到安装脚本 {INSTALLER_SCRIPT}")

    stage = _stage_installer_files()
    quad = _version_quad()
    # 版本与路径全部由 /D 传进去：.iss 里再写一份字面量就会有一天两处不一致，
    # 而"安装包属性页显示 0.1.0、程序自报 0.2.0"只有用户会发现。
    command = [
        str(iscc),
        "/Q",
        f"/DAppVersion={__version__}",
        f"/DVersionQuad={quad}",
        f"/DDistDir={dist}",
        f"/DStageDir={stage}",
        str(INSTALLER_SCRIPT),
    ]
    print(f"编译安装包：{iscc}")
    completed = subprocess.run(command, cwd=ROOT, check=False)
    if completed.returncode != 0:
        raise SystemExit(f"ISCC 失败（退出码 {completed.returncode}）：安装包未生成")
    target = dist / installer_name()
    if not target.exists():  # pragma: no cover - ISCC 成功但改了输出名
        raise SystemExit(f"ISCC 报告成功，但 {target} 不存在——检查 .iss 的 OutputBaseFilename")
    return target


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if "--help" in argv or "-h" in argv:
        print(USAGE)
        return 0
    installer = "--no-installer" not in argv
    if "--assemble-only" in argv:
        assemble(installer=installer)
        return 0
    return build(
        clean="--no-clean" not in argv,
        exclude_pynput="--exclude-pynput" in argv,
        # 组装是**发布动作**，要显式要求。本地一天构建好几次，每次都重算许可清单、
        # 打 zip、编译安装包、算几个大文件的摘要，纯属白等。
        assemble_release="--release" in argv,
        installer=installer,
    )


if __name__ == "__main__":
    sys.exit(main())
