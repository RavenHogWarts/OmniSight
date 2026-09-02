"""发布前的扫描留证（12 文档 M6 判据 2、风险登记 R2 的"提前扫描并留证"）。

一个全局读键盘的程序会被杀软报警，R2 把它列为"概率高、影响高"。对策有三层：
文档正面解释（`docs/faq.md`）、程序本身不含任何出站调用（08 文档）、以及**发布前
扫一遍并把结果记下来**。这个脚本负责第三层。

它做两件可复现的事：

1. 算出 ``dist/`` 里两件产物的大小与 SHA-256，并给出各自的 VirusTotal
   **按哈希查询**地址；
2. 用本机 Windows Defender 做一次按需扫描，且**关掉修复动作**
   （``-DisableRemediation``）——取证的目的是记录结论，不是让杀软顺手把刚构建
   好的产物隔离掉。

**VirusTotal 的提交是人工步骤，脚本不做。** 上传一个文件到 VirusTotal 等于把它
公开（此后任何人都能按哈希取走样本），这个决定应当由维护者自己做，不该由构建
脚本替他做。脚本给出查询链接，并留一个 ``--virustotal`` 参数：提交完把结果摘要
传进来，它就进记录。

**退出码**：本机扫描报出威胁 → 1（这样的产物不该被静默发出去）；扫描不可用
（Defender 被停用或被第三方杀软接管）→ 0，但记录里如实写"未执行"，绝不写成
"通过"——一份把"没扫"记成"干净"的留证比没有留证更坏。
"""

from __future__ import annotations

import locale
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
RECORD = ROOT / "docs" / "scan-record.md"

for _entry in (ROOT / "src", Path(__file__).resolve().parent):
    if str(_entry) not in sys.path:
        sys.path.insert(0, str(_entry))

import build  # noqa: E402  产物名单与摘要实现只此一份，见 build.artifact_names
from omnisight import __version__  # noqa: E402

#: 按哈希查询的地址。**查询不上传任何东西**——用的是上面本地算出的 SHA-256，
#: 文件本身不出本机。首次发布时它会显示"未收录"，那说明还没人提交过这个哈希，
#: 不等于"扫描通过"。
VT_LOOKUP = "https://www.virustotal.com/gui/file/{digest}"

#: ``MpCmdRun.exe`` 的两个落点：新版随引擎更新滚动到 ProgramData 的
#: ``Platform/<版本>/`` 下，老路径在 Program Files。只认一个的脚本会在相当一部分
#: 机器上报"找不到"。
PLATFORM_SUBDIR = ("Microsoft", "Windows Defender", "Platform")
LEGACY_SUBDIR = ("Windows Defender",)
CLI_NAME = "MpCmdRun.exe"

#: 引擎被停用或被第三方杀软接管时的输出特征。**必须与"发现威胁"区分开**：
#: MpCmdRun 这两种情况都可能返回退出码 2，只看退出码会把"扫不了"记成"有毒"。
UNAVAILABLE_MARKERS = ("Product/Feature disabled", "[Failed]", "hr = 0x")

#: 命中数的正则。不能用 ``"found" in output`` 判定——干净结果的原话是
#: "found no threats"，那样写会把每一次通过都记成检出。
THREAT_COUNT = re.compile(r"found\s+(\d+)\s+threat", re.IGNORECASE)

STATE_LABELS = {
    "clean": "未报警",
    "detected": "报出威胁",
    "unavailable": "未执行（引擎不可用）",
    "error": "未执行（命令异常）",
    "skipped": "未执行（本次跳过）",
}


@dataclass(frozen=True, slots=True)
class ScanResult:
    """一次扫描的结论。``state`` 取 :data:`STATE_LABELS` 的键。"""

    state: str
    detail: str = ""

    @property
    def label(self) -> str:
        return STATE_LABELS.get(self.state, self.state)

    @property
    def blocking(self) -> bool:
        """是否应当阻止发布。只有真的检出才算——"扫不了"是留证的缺口，不是证据。"""
        return self.state == "detected"


@dataclass(frozen=True, slots=True)
class Scanned:
    """一件产物及其扫描结论。"""

    name: str
    size: int
    digest: str
    result: ScanResult
    #: 是否是**发布出去的**那两件之一（便携 zip / 安装包）。裸 EXE 只是构建产物，但它
    #: 仍然要被扫——杀软报的是它，而用户核对下载用的是发布物的校验值。两件事都要说清楚。
    published: bool = False

    @property
    def role(self) -> str:
        return "发布物" if self.published else "两件发布物内含的可执行文件"

    @property
    def lookup(self) -> str:
        return VT_LOOKUP.format(digest=self.digest)


def _version_key(name: str) -> tuple[int, ...]:
    """``4.18.26080.3-0`` → ``(4, 18, 26080, 3, 0)``。

    按字符串排序会把 ``4.18.9999`` 排在 ``4.18.26080`` 之后（字典序比 9 大），
    于是脚本会挑一个旧引擎去扫——结论看起来一样，实际用的特征库老了几个月。
    """
    return tuple(int(part) for part in re.findall(r"\d+", name))


def defender_cli(env: dict[str, str] | None = None) -> tuple[Path | None, str]:
    """找到 ``MpCmdRun.exe``，同时给出可写进记录的引擎版本标签。

    返回 ``(路径, 版本标签)``；找不到时返回 ``(None, "")``。版本标签直接取
    Platform 目录名——它就是引擎的平台版本，免费且准确，不必再起一个进程去问。

    **环境变量按大写查。** Windows 上 ``os.environ`` 本身是大小写无关的映射，但
    ``dict(os.environ)`` 一转就退化成普通字典（键在 Windows 上是大写的），于是
    ``env.get("ProgramData")`` 恒为空——脚本会安静地报告"本机没装 Defender"。
    """
    source = os.environ if env is None else env
    env = {key.upper(): value for key, value in source.items()}
    program_data = env.get("PROGRAMDATA", "")
    if program_data:
        platform_root = Path(program_data).joinpath(*PLATFORM_SUBDIR)
        candidates = []
        if platform_root.is_dir():
            candidates = sorted(
                (item for item in platform_root.iterdir() if (item / CLI_NAME).exists()),
                key=lambda item: _version_key(item.name),
                reverse=True,
            )
        if candidates:
            return candidates[0] / CLI_NAME, candidates[0].name
    program_files = env.get("PROGRAMFILES", "")

    if program_files:
        legacy = Path(program_files).joinpath(*LEGACY_SUBDIR, CLI_NAME)
        if legacy.exists():
            return legacy, "系统内置"
    return None, ""


def interpret(returncode: int, output: str) -> ScanResult:
    """把 MpCmdRun 的退出码 + 输出翻译成结论。

    判定顺序是刻意的：**先认"引擎不可用"**。本机实测过一次
    ``WARN: Product/Feature disabled`` + ``[Failed][0x80004005]`` + 退出码 2 的组合
    ——如果先按退出码判，这台机器上的记录会写成"报出威胁"，而实际上什么都没扫。
    """
    text = output.strip()
    lowered = text.lower()
    for marker in UNAVAILABLE_MARKERS:
        if marker.lower() in lowered:
            return ScanResult("unavailable", _reason(text) or f"{marker}（退出码 {returncode}）")
    match = THREAT_COUNT.search(text)
    if match:
        count = int(match.group(1))
        if count == 0:
            return ScanResult("clean", "found 0 threats")
        return ScanResult("detected", match.group(0))
    if "no threats" in lowered or "未发现威胁" in text:
        return ScanResult("clean", "no threats")
    if returncode == 0:
        return ScanResult("clean", "退出码 0")
    if returncode == 2 or "threat" in lowered:
        return ScanResult("detected", f"退出码 {returncode}")
    return ScanResult("error", f"退出码 {returncode}")


def _reason(text: str) -> str:
    """挑一行能解释"为什么没扫成"的输出，供记录直接引用。"""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(("WARN:", "ERROR:", "[Failed]")):
            return stripped
    return ""


def _decode(raw: bytes) -> str:
    """把 MpCmdRun 的输出解成文本。

    **不用 ``subprocess`` 的 ``text=True``**：它按 locale 的首选编码解码，而
    MpCmdRun 在中文 Windows 上输出的是 UTF-8——两者不一致时得到的是一段乱码，
    而这段文字会被原样抄进发布记录里（实测：``未指定的错误`` 变成 ``鏈�鎸囧畾``）。
    先试 UTF-8，再退回本机首选编码。
    """
    for encoding in ("utf-8", locale.getpreferredencoding(False)):
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("latin-1", errors="replace")


def scan(path: Path, cli: Path | None = None, *, timeout: float = 900) -> ScanResult:
    """按需扫描一个文件。``-DisableRemediation`` 不是可选项，见模块说明。"""
    if cli is None:
        cli, _ = defender_cli()
    if cli is None:
        return ScanResult("unavailable", "本机找不到 MpCmdRun.exe（未安装或已被替换）")
    command = [str(cli), "-Scan", "-ScanType", "3", "-File", str(path), "-DisableRemediation"]
    try:
        completed = subprocess.run(command, capture_output=True, timeout=timeout, check=False)
    except FileNotFoundError:
        return ScanResult("unavailable", f"无法执行 {cli}")
    except subprocess.TimeoutExpired:
        return ScanResult("error", f"扫描超过 {timeout:.0f} 秒未返回")
    output = f"{_decode(completed.stdout)}\n{_decode(completed.stderr)}"
    return interpret(completed.returncode, output)



def collect(dist: Path = DIST, *, run_scan: bool = True) -> tuple[list[Scanned], str]:
    """对 ``dist/`` 里的产物逐件算摘要并扫描。返回 ``(记录, 引擎版本标签)``。

    产物名单来自 :func:`build.artifact_names`——两处各写一遍的话，改名那天记录会
    静默少一行，而"少一行"和"这件产物没问题"在文档里长得一模一样。
    """
    cli, engine = (defender_cli() if run_scan else (None, ""))
    published = set(build.published_names())
    scanned: list[Scanned] = []
    for name in build.artifact_names():
        path = dist / name
        if not path.exists():
            continue
        result = scan(path, cli) if run_scan else ScanResult("skipped", "--no-scan")
        scanned.append(
            Scanned(
                name=name,
                size=path.stat().st_size,
                digest=build.sha256_of(path),
                result=result,
                published=name in published,
            )
        )
    return scanned, engine


def render(
    scanned: list[Scanned],
    *,
    version: str = __version__,
    when: datetime | None = None,
    engine: str = "",
    virustotal: str = "",
    virustotal_url: str = "",
) -> str:
    """生成记录正文。面向的是"要不要信任这个下载"的用户，不是维护者自己。"""
    when = when or datetime.now().astimezone()
    artifacts = "\n".join(
        f"| `{item.name}` | {item.role} | {item.size / 1048576:.1f} MB | `{item.digest}` |"
        for item in scanned
    ) or "| —— | —— | —— | 本次生成时 `dist/` 里没有产物 |"
    scans = "\n".join(
        f"| `{item.name}` | {item.result.label} | {item.result.detail or '—'} |" for item in scanned
    ) or "| —— | 未执行 | 没有可扫描的产物 |"
    lookups = "\n".join(f"- `{item.name}` → <{item.lookup}>" for item in scanned) or "- （无产物）"
    engine_line = f"Windows Defender（引擎平台版本 {engine}）" if engine else "Windows Defender"
    vt_state = virustotal or "**未提交**（提交是人工步骤，见下）"
    vt_link = f"\n公开报告：<{virustotal_url}>\n" if virustotal_url else ""
    # 每件发布物给一行核对命令。这里是**普通 f-string**，不是下面那个大模板的一部分，
    # 所以反斜杠只需转义一次——多一层就会在文档里印出 `.\\OmniSight-...`。
    checks = "\n".join(
        f"Get-FileHash .\\{item.name} -Algorithm SHA256" for item in scanned if item.published
    ) or "Get-FileHash .\\<下载到的文件> -Algorithm SHA256"
    return f"""# 发布物扫描记录

本文件由 `tools/scan_record.py` 生成，请勿手改——每次发布重新生成一份。
它只回答一个问题：**这份产物在发出去之前被扫过没有，结果是什么。**

OmniSight 全局读取键盘输入，杀软把它标为可疑是合理的启发式判断——为什么会这样、
以及怎么处理，见 [faq.md 的杀软一节](faq.md)。这份记录不试图说服你它无害，
只提供可核对的事实。

- 程序版本：`{version}`
- 记录时间：{when.isoformat(timespec="seconds")}
- 生成环境：Python {sys.version.split()[0]} / {sys.platform}

## 产物与校验值

**发布两件产物**：便携 zip 与安装包（分工是安装位置，见 [README](../README.md)）。
下表同时列出它们内含的可执行文件，因为杀软报的是它，而你核对下载用的是发布物的校验值。

| 文件 | 角色 | 大小 | SHA-256 |
| --- | --- | --- | --- |
{artifacts}

下载后自己算一遍，与上表比对：

```powershell
{checks}
```

## 本机杀软扫描

引擎：{engine_line}

| 文件 | 结果 | 说明 |
| --- | --- | --- |
{scans}

复现命令（`<MpCmdRun>` 在 `%ProgramData%\\Microsoft\\Windows Defender\\Platform\\<版本>\\` 下）：

```powershell
& "<MpCmdRun>" -Scan -ScanType 3 -File .\\OmniSight.exe -DisableRemediation
```

`-DisableRemediation` 是刻意的：取证时不希望杀软顺手把产物隔离掉。

**"未报警"的含义有限**：它是这一个引擎、这一份特征库、这一次扫描的结论，不是
"本程序无害"的证明。真正能支撑后者的是源码公开与下面第三条路径。

## VirusTotal

状态：{vt_state}
{vt_link}
按 SHA-256 查询（**查询不上传文件**，用的是上表里本地算出的哈希）：

{lookups}

提交样本是人工步骤：上传到 VirusTotal 等于公开发布这个文件，此后任何人都能按
哈希取走样本，因此这个决定由维护者本人做，构建脚本不代劳。首次发布时上面的
链接可能显示"未收录"——那说明还没有人提交过这个哈希，**不代表扫描通过**。

## 你可以自己验证的三条路径

1. **核对校验值**——确认下载到的字节与本记录一致（上面那条 `Get-FileHash`）。
2. **按哈希查 VirusTotal**——不需要上传，也不需要相信本文件里的任何结论。
3. **从源码构建**——`python tools/build.py`。注意 PyInstaller 的输出**不是逐字节
   可复现**的（构建时间戳、临时路径、依赖轮子差异都会进产物），所以你自己构建出的
   EXE 哈希**不会**等于发布版的哈希。这不是被篡改的迹象；逐字节比对只在同一次
   构建的产物之间成立。

未签名产物的说明、以及为什么暂不购买代码签名证书，见 [faq.md](faq.md)；
程序记录什么、不记录什么见 [privacy.md](privacy.md)。
"""


def _argument(argv: list[str], flag: str) -> str:
    """``--flag 值`` 与 ``--flag=值`` 都认。"""
    for index, item in enumerate(argv):
        if item == flag and index + 1 < len(argv):
            return argv[index + 1]
        if item.startswith(f"{flag}="):
            return item.split("=", 1)[1]
    return ""


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    dist = Path(_argument(argv, "--dist") or DIST)
    out = Path(_argument(argv, "--out") or RECORD)
    scanned, engine = collect(dist, run_scan="--no-scan" not in argv)
    if not scanned:
        print(f"{dist} 里没有产物——先跑一次 python tools/build.py", file=sys.stderr)
        return 1
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        render(
            scanned,
            engine=engine,
            virustotal=_argument(argv, "--virustotal"),
            virustotal_url=_argument(argv, "--virustotal-url"),
        ),
        encoding="utf-8",
    )
    print(f"已写入 {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}")
    for item in scanned:
        print(f"  {item.name}  {item.result.label}  sha256={item.digest[:16]}…")
    blocking = [item for item in scanned if item.result.blocking]
    if blocking:
        print("\n本机扫描报出威胁，先查清原因再决定是否发布：", file=sys.stderr)
        for item in blocking:
            print(f"  {item.name}: {item.result.detail}", file=sys.stderr)
        return 1
    if any(item.result.state != "clean" for item in scanned):
        print(
            "\n提示：本机扫描未真正执行（见记录里的说明）。判据要求的留证尚不完整，"
            "发布前请在一台启用了杀软的机器上补扫，并把 VirusTotal 结果用 "
            "--virustotal 传进来。"
        )
    return 0


if __name__ == "__main__":
    # 见 tools/_console.py：runner 上 stdout 是管道，按 locale 挑到 cp1252，
    # 一行中文输出就能让进程死在 UnicodeEncodeError 上。
    from _console import use_utf8_output

    use_utf8_output()
    sys.exit(main())
