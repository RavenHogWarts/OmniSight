"""发版说明：变更取自 git 提交记录，校验值取自 ``dist/`` 里的发布物（10 文档 §11）。

发版由**手工打 tag** 触发（``v0.1.0-alpha.1`` / ``v0.1.0``）。tag 一推上去，
``.github/workflows/release.yml`` 跑完整检查、构建两件产物、调这个脚本生成说明，
再建 Release。**这个脚本是那条流水线里唯一需要做判断的一步**，它做的三件事各自
对应一种会静默出错的方式：

* **tag 与代码里的 ``__version__`` 必须是同一个版本**（``--check-only`` 在流水线最
  前面单跑这一条）。不核对的后果不是构建失败，而是发布页写着 0.2.0，而它发出去的
  EXE 属性页、安装包卸载项、崩溃报告、API 响应里全都写着 0.1.0-alpha.1——用户核对
  属性页时唯一合理的结论是"这个文件被人换过"。
* **预发布还是正式版由版本串自己决定**，判定复用 :func:`version_info.is_prerelease`
  ——EXE 属性页上那个"（预发布）"标记用的就是它。两处各写一遍判定，迟早出现一个
  挂着 GitHub "Latest release" 徽章、而属性页写着预发布的产物。
* **校验值必须属于真正发出去的那些字节**：脚本自己算一遍摘要，并与 ``--release``
  写下的 ``.sha256`` 比对。不一致意味着产物在算完摘要之后被动过，或者 ``dist/`` 里
  混着上一次构建的残留——两种都必须让发布失败，因为"校验不上"在用户那边只有一种
  解释方式，而那种解释比发布失败严重得多。

**不做的事**：不改版本号、不打 tag、不提交任何文件。版本号是人改的（``__version__``
与 ``pyproject.toml`` 各一处，``tests/unit/test_version.py`` 核对两者是同一个版本），
tag 也是人打的——"自动发版"自动的是发布动作，不是"发哪个版本"这个决定。
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"

for _entry in (ROOT / "src", Path(__file__).resolve().parent):
    if str(_entry) not in sys.path:
        sys.path.insert(0, str(_entry))

import build  # noqa: E402  产物名单、摘要实现与"哪几件才发布"只此一份
import version_info  # noqa: E402  预发布判定与 EXE 属性页同源
from omnisight import APP_NAME, __version__  # noqa: E402

USAGE = """用法：python tools/release_notes.py [选项]

  --tag v0.1.0-alpha.1  要发布的 tag（默认 v<当前版本>）。前缀 v 可有可无。
  --check-only          只核对 tag 与代码里的版本号，不生成任何东西。
  --no-artifacts        不读 dist/，只渲染变更部分（本地预览用）。
  --dist 目录           发布物所在目录（默认 dist/）。
  --previous v0.1.0     手动指定基线 tag（默认按"同类"自动选，见下）。
  --repo owner/name     仓库（默认取 GITHUB_REPOSITORY，否则解析 origin 的 URL）。
  --out 文件            写入文件（默认写到标准输出）。

变更以 git 提交记录为准：取 <基线 tag>..<tag> 之间的提交，按 Conventional Commits
的前缀分节；认不出前缀的进"其他"，一条都不丢。

**基线是同类的上一个 tag**：预发布跟上一个预发布比，正式版跟上一个正式版比。否则
v0.1.0 会拿 v0.1.0-rc.1 当基线，而那份说明里只剩 rc 之后那几条提交——这个正式版真正
交付的东西全在它前面。

本地预览（tag 还没打时按 HEAD 算）：
    .venv/Scripts/python tools/release_notes.py --no-artifacts"""

OTHER = "其他"
BREAKING = "不兼容变更"

#: 提交前缀 → 小节标题。别名（``feature`` / ``doc`` / ``tests``）一并认：前缀写成
#: 复数不该让一条提交掉进"其他"。
SECTION_OF = {
    "feat": "新增",
    "feature": "新增",
    "fix": "修复",
    "bugfix": "修复",
    "perf": "性能",
    "revert": "回退",
    "refactor": "重构",
    "docs": "文档",
    "doc": "文档",
    "test": "测试",
    "tests": "测试",
    "build": "构建与杂项",
    "ci": "构建与杂项",
    "chore": "构建与杂项",
    "style": "构建与杂项",
}

#: 渲染顺序。**不兼容变更排在最前**——它是唯一"不看就会踩到"的一类。
SECTION_ORDER = (
    BREAKING,
    "新增",
    "修复",
    "性能",
    "回退",
    "重构",
    "文档",
    "测试",
    "构建与杂项",
    OTHER,
)

#: Conventional Commits 的标题行：``type(scope)!: summary``。
_HEADER = re.compile(
    r"^(?P<type>[a-zA-Z]+)(?:\((?P<scope>[^)]*)\))?(?P<breaking>!)?:\s*(?P<summary>.*)$"
)

#: 从 ``origin`` 的 URL 里认出 ``owner/name``。SSH（``git@github.com:o/n.git``）与
#: HTTPS 两种写法都要认——只认一种的话，一半的检出上 sha 链接会静默消失。
_REMOTE = re.compile(r"github\.com[:/](?P<owner>[^/]+)/(?P<name>[^/]+?)(?:\.git)?/?$")


@dataclass(frozen=True, slots=True)
class Commit:
    """一条提交。``subject`` 保留原始标题行，不做任何改写。"""

    sha: str
    subject: str

    @property
    def _head(self) -> re.Match[str] | None:
        return _HEADER.match(self.subject)

    @property
    def section(self) -> str:
        head = self._head
        if head is None:
            return OTHER
        if head["breaking"]:
            return BREAKING
        return SECTION_OF.get(head["type"].lower(), OTHER)

    @property
    def breaking(self) -> bool:
        return bool(self._head and self._head["breaking"])

    @property
    def summary(self) -> str:
        """去掉 ``feat:`` 这类前缀后的正文。

        两处刻意保留原文：**认不出的前缀**（``WIP: 待续`` 里的 ``WIP`` 是这条提交
        的重点，剥掉它等于篡改）、以及**没有前缀**的标题。作用域保留成
        ``tray: 图标变灰`` 的形式——它常常是"这条改动落在哪儿"的唯一线索，扔掉
        会让一半提交看起来像在说同一件事。
        """
        head = self._head
        if head is None or head["type"].lower() not in SECTION_OF:
            return self.subject
        text = head["summary"].strip() or self.subject
        scope = (head["scope"] or "").strip()
        return f"{scope}: {text}" if scope else text


def parse_log(text: str) -> list[Commit]:
    """``git log --pretty=format:%h%x1f%s`` 的输出 → 提交列表。

    分隔符用 ``\\x1f``（US）而不是空格或制表符：提交标题里出现制表符罕见但合法，
    而一次错切会把标题的一半当成 sha。
    """
    commits: list[Commit] = []
    for line in text.splitlines():
        sha, _, subject = line.partition("\x1f")
        sha = sha.strip()
        if not sha:
            continue
        commits.append(Commit(sha=sha, subject=subject.strip() or "（无标题）"))
    return commits


def _decode(raw: bytes) -> str:
    return raw.decode("utf-8", errors="replace").strip()


def _git(args: list[str], *, cwd: Path | None = None) -> tuple[int, str, str]:
    """跑一次 git，返回 ``(退出码, stdout, stderr)``。

    两个刻意的选择：

    * **不用 ``text=True``**。它按 locale 的首选编码解码，而提交信息是 UTF-8——
      中文 Windows（cp936）上那样读会把每条中文标题解成乱码，然后原样抄进发版说明。
    * **显式 ``-c i18n.logOutputEncoding=UTF-8``**。谁的 ``~/.gitconfig`` 里设了
      ``gbk``，上一条的解码就白做了，而症状同样是发布页上一片乱码。
    """
    command = ["git", "-c", "i18n.logOutputEncoding=UTF-8", *args]
    result = subprocess.run(command, cwd=str(cwd or ROOT), capture_output=True, check=False)
    return result.returncode, _decode(result.stdout), _decode(result.stderr)


def git(*args: str, cwd: Path | None = None) -> str:
    code, out, err = _git(list(args), cwd=cwd)
    if code != 0:
        raise SystemExit(f"git {' '.join(args)} 失败（退出码 {code}）：{err or out}")
    return out


def git_quiet(*args: str, cwd: Path | None = None) -> str | None:
    """失败返回 ``None`` 的版本，给"存在与否本身就是答案"的那几次查询用。"""
    code, out, _err = _git(list(args), cwd=cwd)
    return out if code == 0 else None


def is_shallow(*, cwd: Path | None = None) -> bool:
    """浅克隆下 ``git log`` 取不到上一个 tag，**而且不报错**——生成的变更日志会安静
    地变空。``actions/checkout`` 默认就是深度 1，所以这条必须显式挡在前面。
    """
    return git_quiet("rev-parse", "--is-shallow-repository", cwd=cwd) == "true"


def rev_exists(rev: str, *, cwd: Path | None = None) -> bool:
    return git_quiet("rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}", cwd=cwd) is not None


def tags_in_history(rev: str, *, cwd: Path | None = None) -> list[str]:
    """从 ``rev`` 往回，按**历史顺序**（近的在前）列出可达的 tag。

    两条路都试过，都不能用：

    * ``git tag --sort=-creatordate`` 按 tag 的**创建时间**排，而"给一个旧提交补打一个
      tag"会让顺序与历史不符——基线选错一个，整份变更日志跟着错；
    * ``git log --simplify-by-decoration`` 看着正合适，实测会**漏掉 tag**：一串空提交
      （``--allow-empty``）上，根提交那个 tag 就不出现。它是一种历史简化模式，与
      TREESAME 的裁剪相互作用，漏的方式安静得看不出来。

    于是用 ``--decorate-refs=refs/tags`` 走全部提交：顺序就是 ``git log`` 的顺序，装饰
    里只有 tag（分支与 HEAD 不掺进来），代价是每个提交一行——对任何规模的仓库都便宜。
    """
    tags: list[str] = []
    log = git("log", "--pretty=%D", "--decorate-refs=refs/tags", rev, cwd=cwd)
    for line in log.splitlines():
        for entry in line.split(","):
            entry = entry.strip()
            if entry.startswith("tag: "):
                tags.append(entry.removeprefix("tag: ").strip())
    return tags


def is_prerelease_tag(tag: str) -> bool:
    """tag 是不是预发布。

    判定复用 :func:`version_info.is_prerelease`——与 Release 徽章、EXE 属性页上那个
    "（预发布）"标记同一个函数。**不写成 ``v*-*`` 这样的 glob 丢给 git 去筛**：那是
    第二处判定，而它认不出 ``v0.1.0a1``（PEP 440 里合法的预发布写法，没有连字符）。
    """
    return version_info.is_prerelease(version_of(tag))


def baseline_from(tags: list[str], *, prerelease: bool) -> str | None:
    """这次发布该拿**哪个** tag 当基线。``tags`` 是历史顺序的候选（近的在前）。

    **预发布跟上一个预发布比，正式版跟上一个正式版比。** 理由是"跟着一条线看"：
    ``v0.2.0`` 的说明要是拿 ``v0.2.0-rc.1`` 当基线，剩下的就只有 rc 到正式版之间那
    几条提交，而这个正式版真正交付的东西全在它前面——一份"看起来什么都没改"的正式版
    说明，比没有说明更误导人。

    找不到同类时两种情况的答案不同，这处不对称是有意的：

    * **正式版找不到上一个正式版** → ``None``，列出全部历史。这只会发生在"第一个
      正式版"上，而那时"自项目开始以来"正是它要交付的东西。
    * **预发布找不到上一个预发布** → 退回最近的那个 tag（也就是上一个正式版）。
      用户此刻手上装着的就是它，拿它当基线是对的；而列出全部历史只会淹掉这次预发布
      真正改了什么。
    """
    same_kind = [tag for tag in tags if is_prerelease_tag(tag) is prerelease]
    if same_kind:
        return same_kind[0]
    if prerelease and tags:
        return tags[0]
    return None

def commits_between(previous: str | None, until: str, *, cwd: Path | None = None) -> list[Commit]:
    """``previous..until`` 之间的提交，新的在前。``previous`` 为空则取全部历史。"""
    if is_shallow(cwd=cwd):
        raise SystemExit(
            "仓库是浅克隆，取不到完整提交记录——checkout 时设 fetch-depth: 0。"
            "（不挡的话变更日志会是空的，而且一声不响。）"
        )
    span = f"{previous}..{until}" if previous else until
    return parse_log(git("log", "--no-merges", "--pretty=format:%h%x1f%s", span, cwd=cwd))


def repository(environ: dict[str, str] | None = None, *, cwd: Path | None = None) -> str | None:
    """``owner/name``，用来把 sha 与"完整对比"链到 GitHub。拿不到就不链，不猜。"""
    environ = environ if environ is not None else dict(os.environ)
    slug = environ.get("GITHUB_REPOSITORY")
    if slug:
        return slug.strip()
    match = _REMOTE.search((git_quiet("remote", "get-url", "origin", cwd=cwd) or "").strip())
    return f"{match['owner']}/{match['name']}" if match else None


# ── tag 与版本号 ────────────────────────────────────────────────────────


def version_of(tag: str) -> str:
    """``v0.1.0-alpha.1`` → ``0.1.0-alpha.1``。前缀 ``v`` 只是 tag 的习惯写法。"""
    return tag[1:] if tag[:1] in {"v", "V"} else tag


def tag_for(version: str = __version__) -> str:
    return f"v{version}"


def verify_tag(tag: str, version: str = __version__) -> str:
    """核对 tag 与代码里的版本号是同一个版本，返回 tag 对应的版本串。

    比的是 **PEP 440 规范化之后**的版本：``v0.1.0a1`` 与 ``0.1.0-alpha.1`` 是同一个
    版本，拒绝它只会逼人去查规范。真正要拦的是 ``v0.2.0`` 撞上代码里的
    ``0.1.0-alpha.1`` 那种——那会发出一份"发布页与它自己的文件各说各话"的产物。

    返回的是**代码里那个**版本串（``0.1.0-alpha.1``），不是 tag 上的写法：发布标题
    要与 EXE 属性页、安装包卸载项显示的完全一致，而那几处显示的都是 ``__version__``。
    """
    wanted = version_of(tag)
    try:
        from packaging.version import InvalidVersion, Version
    except ImportError:  # pragma: no cover - 开发环境必有 packaging（pyinstaller 依赖）
        same = wanted == version
    else:
        try:
            same = Version(wanted) == Version(version)
        except InvalidVersion:
            same = wanted == version
    if not same:
        raise SystemExit(
            f"tag {tag} 与代码里的版本 {version} 不是同一个版本。\n"
            f"  要发 {wanted}：先把 src/omnisight/__init__.py 的 __version__ 与 "
            "pyproject.toml 的 version 改过去（tests/unit/test_version.py 核对两者），"
            "提交后重新打 tag；\n"
            f"  要发当前代码：用 tag {tag_for(version)}。"
        )
    return version


# ── 发布物与校验值 ──────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Asset:
    """一件要挂到 Release 上的发布物。"""

    path: Path
    digest: str
    role: str = ""

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def size(self) -> str:
        return f"{self.path.stat().st_size / 1048576:.1f} MB"

    @property
    def sidecar(self) -> Path:
        return self.path.with_name(f"{self.path.name}.sha256")


def _roles() -> dict[str, str]:
    """两件产物各自"适合谁"。键取自 build 的名字函数——改名的那天，这里不会剩下
    一句挂在错误文件上的描述。
    """
    return {
        build.installer_name(): "装进系统：开始菜单项 + 标准卸载项，数据在 %LOCALAPPDATA%",
        build.portable_name(): "解压即用：不动系统，数据在解压目录，可放 U 盘",
    }


def _display_order() -> list[str]:
    """安装包在前（大多数人要的是它），便携包在后。

    顺序表**不是名单**：名单永远是 ``build.published_names()``。将来多出第三件产物
    时它会跟在后面，而不是被这里的两行字面量静默漏掉。
    """
    published = list(build.published_names())
    preferred = [name for name in (build.installer_name(), build.portable_name())
                 if name in published]
    return preferred + [name for name in published if name not in preferred]


def collect(dist: Path = DIST) -> list[Asset]:
    """找出发布物，算摘要，并与 ``--release`` 写下的 ``.sha256`` 比对。

    **裸 EXE 不在其中**（``build.published_names()`` 的理由）：它带不走许可正文与
    说明，而发布页上多挂一个 ``OmniSight.exe`` 等于给出一条绕开分发义务的下载路径。

    缺一件直接失败：Release 页面上"这次只发了便携版"与"安装包没构建出来"长得一模
    一样，而后者是必须让发布红掉的事故。
    """
    roles = _roles()
    assets: list[Asset] = []
    for name in _display_order():
        path = dist / name
        if not path.exists():
            raise SystemExit(
                f"找不到发布物 {path}——先跑 python tools/build.py --release，"
                "或者用 --no-artifacts 只预览变更部分。"
            )
        digest = build.sha256_of(path)
        asset = Asset(path=path, digest=digest, role=roles.get(name, ""))
        if not asset.sidecar.exists():
            raise SystemExit(
                f"找不到 {asset.sidecar.name}——它要随产物一起发布（用户核对下载靠它）。"
            )
        recorded = asset.sidecar.read_text(encoding="utf-8").strip()
        if not recorded.startswith(digest):
            raise SystemExit(
                f"{asset.name} 的实际摘要与 {asset.sidecar.name} 不一致：\n"
                f"  实际  {digest}\n"
                f"  记录  {recorded.split()[0] if recorded else '(空)'}\n"
                "产物在算完摘要之后被动过，或者 dist/ 里混着上一次构建的残留。"
                "重新跑一次 python tools/build.py --release。"
            )
        assets.append(asset)
    return assets


# ── 渲染 ────────────────────────────────────────────────────────────────


def group(commits: list[Commit]) -> list[tuple[str, list[Commit]]]:
    """按小节分组，顺序按 :data:`SECTION_ORDER`。

    最后一句 ``extra`` 是给"加了新小节却忘了排序"留的兜底：宁可某一节乱序，也不能
    让它连同里面的提交一起从发版说明里消失。
    """
    buckets: dict[str, list[Commit]] = {}
    for commit in commits:
        buckets.setdefault(commit.section, []).append(commit)
    ordered = [title for title in SECTION_ORDER if title in buckets]
    extra = [title for title in buckets if title not in SECTION_ORDER]
    return [(title, buckets[title]) for title in [*ordered, *extra]]


def _sha_link(commit: Commit, repo: str | None) -> str:
    if repo:
        return f"[`{commit.sha}`](https://github.com/{repo}/commit/{commit.sha})"
    return f"`{commit.sha}`"


def render_changelog(
    commits: list[Commit],
    *,
    tag: str,
    previous: str | None = None,
    repo: str | None = None,
    nearest: str | None = None,
) -> str:
    """变更那一节。

    ``previous`` 是基线（同类的上一个 tag，见 :func:`baseline_from`）；``nearest`` 是
    历史上最近的那个 tag，只在"没有同类基线、但前面确实有 tag"时用来解释**为什么**
    这份清单这么长——一个读者看到 200 条提交时，第一个问题就是这个。
    """
    lines = ["## 变更"]
    if not commits:
        # 同一个提交上打两个 tag（把 alpha 原样转正）时这是正确结果，不是故障。
        lines.append(f"\n自 {previous} 以来没有新提交。" if previous else "\n没有提交记录。")
        return "\n".join(lines)
    if previous:
        # 说出基线是哪一类：正式版拿上一个正式版比，清单会包含此前预发布里已经出现过
        # 的改动，而不说明这一点的话，跟着预发布走的人会以为重复了。
        kind = "预发布" if is_prerelease_tag(previous) else "正式版"
        lines.append(
            f"\n自上一个{kind} {previous} 以来共 {len(commits)} 条提交（以 git 记录为准）："
        )
    elif nearest:
        lines.append(
            f"\n**首个正式版**：此前的 tag 都是预发布（最近的是 {nearest}），因此下面列出的是"
            f"自项目开始以来的全部 {len(commits)} 条提交（以 git 记录为准）："
        )
    else:
        lines.append(f"\n首个发布，共 {len(commits)} 条提交（以 git 记录为准）：")
    for title, bucket in group(commits):
        lines.append(f"\n### {title}\n")
        lines += [f"- {commit.summary} {_sha_link(commit, repo)}" for commit in bucket]
    if repo:
        url = (
            f"https://github.com/{repo}/compare/{previous}...{tag}"
            if previous
            else f"https://github.com/{repo}/commits/{tag}"
        )
        lines.append(f"\n**完整对比**：{url}")
    return "\n".join(lines)

def render_assets(assets: list[Asset], *, signed: bool | None = None) -> str:
    """产物表 + 校验值 + 校验方法。

    ``signed`` 决定最后一段说不说"未做代码签名"。默认按环境里的签名配置算——
    ``build.render_readme`` 里同一件事踩过一次：签名构建配着一句"本程序未做代码
    签名"，而那句话恰好出现在信任成本最高的地方。
    """
    signed = build.signing_from_env() is not None if signed is None else signed
    lines = [
        "## 产物与校验值",
        "",
        "| 文件 | 大小 | 适合 |",
        "| --- | --- | --- |",
    ]
    lines += [f"| `{item.name}` | {item.size} | {item.role} |" for item in assets]
    lines.append(
        f"\n两件产物功能完全一样，差别只有安装位置。`{build._executable_name()}` 不单独发布"
        "——它带不走许可正文与说明。"
    )
    lines.append("\nSHA-256（与随发布上传的 `.sha256` 是同一份内容）：\n")
    lines.append("```text")
    lines += [f"{item.digest}  {item.name}" for item in assets]
    lines.append("```")
    lines.append(f"\n```powershell\nGet-FileHash .\\{assets[0].name} -Algorithm SHA256\n```")
    if signed:
        lines.append(
            "\n产物带数字签名（属性页 →「数字签名」可以核对签署者）。校验值仍然给出，"
            "它比签名更容易自己动手核对。"
        )
    else:
        lines.append(
            "\n本程序**未做代码签名**，Windows 会显示 SmartScreen 警告（「更多信息」→"
            "「仍要运行」），部分杀软也可能因为「读键盘」这一行为报警。因此校验值是确认"
            "你拿到的确实是这份产物的唯一手段——下载后请先核对再运行。"
        )
    return "\n".join(lines)


def _docs_link(repo: str | None, tag: str, path: str, label: str) -> str:
    if repo:
        return f"[{label}](https://github.com/{repo}/blob/{tag}/{path})"
    return f"{label}（{path}）"


def render(
    *,
    tag: str,
    commits: list[Commit],
    previous: str | None = None,
    nearest: str | None = None,
    assets: list[Asset] | None = None,
    repo: str | None = None,
    version: str | None = None,
    signed: bool | None = None,
) -> str:
    """完整的 Release 正文。"""
    version = version or version_of(tag)
    blocks: list[str] = []
    if version_info.is_prerelease(version):
        blocks.append(
            f"> **预发布版本 {version}。** 功能已经可用，但接口与数据格式在正式版之前"
            "仍可能调整。"
        )
    blocks.append(
        render_changelog(commits, tag=tag, previous=previous, nearest=nearest, repo=repo)
    )
    if assets:
        blocks.append(render_assets(assets, signed=signed))
    blocks.append(
        "安装与卸载、杀软误报、权限、隐私边界见 "
        + _docs_link(repo, tag, "README.md", "README")
        + "、"
        + _docs_link(repo, tag, "docs/faq.md", "常见问题")
        + " 与 "
        + _docs_link(repo, tag, "docs/privacy.md", "隐私说明")
        + "。数据只留在本机：无账号、不联网、无遥测。"
    )
    return "\n\n".join(blocks) + "\n"


# ── GitHub Actions 的出参 ───────────────────────────────────────────────


def _asset_argument(path: Path) -> str:
    """挂到 ``gh release create`` 后面的那个路径。

    尽量相对仓库根、且用正斜杠：出参是**按空格切**的一行，而 Windows runner 上的
    绝对路径迟早会带上一个空格（现在的 runner 上没有，但这不是保证）。
    """
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def github_outputs(
    *, tag: str, version: str, assets: list[Asset] | None = None
) -> dict[str, str]:
    """流水线要的几个值。``prerelease`` 就是 Release 页面上那个徽章的开关。"""
    prerelease = version_info.is_prerelease(version)
    paths = [_asset_argument(item.path) for item in assets or []]
    if any(" " in item for item in paths):
        raise SystemExit(
            f"发布物路径里有空格，出参会被切错：{paths}。把仓库放到不带空格的路径下。"
        )
    return {
        "tag": tag,
        "version": version,
        "prerelease": "true" if prerelease else "false",
        "title": f"{APP_NAME} {version}{'（预发布）' if prerelease else ''}",
        "assets": " ".join(paths),
    }


def emit_github_outputs(
    values: dict[str, str], environ: dict[str, str] | None = None
) -> Path | None:
    """在 Actions 里追加到 ``$GITHUB_OUTPUT``；本地运行时什么都不做，返回 ``None``。"""
    environ = environ if environ is not None else dict(os.environ)
    target = environ.get("GITHUB_OUTPUT")
    if not target:
        return None
    path = Path(target)
    with path.open("a", encoding="utf-8") as handle:
        for key, value in values.items():
            handle.write(f"{key}={value}\n")
    return path


def _argument(argv: list[str], name: str) -> str | None:
    """``--name 值`` / ``--name=值`` 都认。"""
    for index, item in enumerate(argv):
        if item == name and index + 1 < len(argv):
            return argv[index + 1]
        if item.startswith(f"{name}="):
            return item.split("=", 1)[1]
    return None


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if "--help" in argv or "-h" in argv:
        print(USAGE)
        return 0

    tag = _argument(argv, "--tag") or tag_for()
    version = verify_tag(tag)
    prerelease = version_info.is_prerelease(version)
    kind = "预发布" if prerelease else "正式版"
    if "--check-only" in argv:
        print(f"tag {tag} 与代码里的版本 {__version__} 一致（{kind}）")
        return 0

    # tag 还没打时按 HEAD 预览：发版前想看看说明长什么样，是最常用的一次调用。
    rev = tag
    if not rev_exists(tag):
        print(f"（tag {tag} 还不存在，按 HEAD 预览）", file=sys.stderr)
        rev = "HEAD"
    # 基线：预发布跟上一个预发布比，正式版跟上一个正式版比（见 baseline_from）。
    # 先排掉这次要发的那个 tag 自己——它就在 rev 上，留着会让范围恒为空。
    history = [item for item in tags_in_history(rev) if item != tag]
    nearest = history[0] if history else None
    previous = _argument(argv, "--previous") or baseline_from(history, prerelease=prerelease)
    commits = commits_between(previous, rev)
    assets = None if "--no-artifacts" in argv else collect(Path(_argument(argv, "--dist") or DIST))
    text = render(
        tag=tag,
        commits=commits,
        previous=previous,
        nearest=nearest,
        assets=assets,
        repo=_argument(argv, "--repo") or repository(),
        version=version,
    )

    out = _argument(argv, "--out")
    if out:
        Path(out).write_text(text, encoding="utf-8")
        print(f"已写入 {out}：{version}（{kind}），{len(commits)} 条提交")
    else:
        sys.stdout.write(text)
    emit_github_outputs(github_outputs(tag=tag, version=version, assets=assets))
    return 0


if __name__ == "__main__":
    # 见 tools/_console.py：runner 上 stdout 是管道，按 locale 挑到 cp1252，
    # 一行中文输出就能让进程死在 UnicodeEncodeError 上。
    from _console import use_utf8_output

    use_utf8_output()
    sys.exit(main())
