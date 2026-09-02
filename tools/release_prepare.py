"""发版前的版本号准备（10 文档 §11.5 第 1 步）。

release-please 那类工具做三件事：**从提交记录算出下一个版本号**、**改掉版本字面量**、
开一个 PR 等人合并。这里做前两件，第三件不做——发版的触发条件是**手工打 tag**，这是
用户定的边界；而 release-please 的工作方式需要一条 push 触发的常驻 CI，那正是批次 4
移除掉的东西。同一套计算放在本地跑：一条命令、立刻出结果、改的是工作区里的文件，
你自己看一眼再提交。

**版本号有两处字面量**，这个脚本的存在理由一半在此：``src/omnisight/__init__.py`` 的
``__version__``（面向用户的写法，``0.1.0-alpha.2``）与 ``pyproject.toml`` 的 ``version``
（PEP 440 规范形式，``0.1.0a2``）。手改两处、还要记住两种写法，是那种迟早出错而且要等
到发版流水线第一步才发现的事（``tools/release_notes.py --check-only`` 会拦，但那时你
已经打完 tag 了）。

**推算规则**（semver + 0.x 的例外）：

===================  ============================================================
提交里有             建议
===================  ============================================================
不兼容变更（``!``）  major；但主版本还是 0 时走 **minor**（0.x 期间不兼容变更不必
                     升主版本，semver §4——``0.1.0`` → ``1.0.0`` 是"这东西定型了"
                     的宣告，不该由一条提交前缀替你做）
``feat:``            minor
``fix:`` / ``perf:`` patch
其他                 **不建议发版**（只有文档或杂项改动），退出码 1
===================  ============================================================

当前版本是预发布时，"下一个"默认是**递增预发布序号**（``0.1.0-alpha.1`` →
``0.1.0-alpha.2``），而不是按上表跳 core：在一条预发布线上，下一次要发的就是这条线的
下一个；转正（``--stable``）或换 core（``--minor``）都是决定，不该是默认。

当前版本**还没发过**（没有对应的 tag）时什么都不改：那时的答案是"直接打 tag"。
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

for _entry in (ROOT / "src", Path(__file__).resolve().parent):
    if str(_entry) not in sys.path:
        sys.path.insert(0, str(_entry))

import release_notes  # noqa: E402  基线选择、提交解析、tag 列举只此一份
from omnisight import __version__  # noqa: E402

#: 版本字面量的两处落点。``pattern`` 必须锚在行首（``pyproject.toml`` 里还有
#: ``target-version`` 与 ``requires-python``，不锚就会改错行），而且要容忍行尾的 CR——
#: 本仓库这两个文件的行尾一个 CRLF 一个 LF，只写 ``$`` 会在 CRLF 那份上匹配不到，
#: 而"匹配不到"看起来和"没有版本号"一模一样。
VERSION_FILES = (
    (
        "src/omnisight/__init__.py",
        re.compile(r'^__version__ = "([^"]+)"\r?$', re.MULTILINE),
        "user",
    ),
    ("pyproject.toml", re.compile(r'^version = "([^"]+)"\r?$', re.MULTILINE), "canonical"),
)

#: PEP 440 的预发布字母 ↔ 面向用户的拼法。``0.1.0a2`` 与 ``0.1.0-alpha.2`` 是同一个
#: 版本，前者进 ``pyproject.toml``，后者进属性页与发布物名（见 ``__init__.py`` 的说明）。
SPELLING = {"a": "alpha", "b": "beta", "rc": "rc"}
CHANNELS = {"alpha": "a", "a": "a", "beta": "b", "b": "b", "rc": "rc", "c": "rc"}

BUMPS = ("major", "minor", "patch")

USAGE = """用法：python tools/release_prepare.py [选项]

  （无选项）      按提交记录算出下一个版本号，改掉两处字面量，打印接下来的命令。
  --dry-run       只看建议与预览，不动任何文件。
  --major/--minor/--patch   自己定级别（默认按提交记录算）。
  --pre alpha|beta|rc       结果取该通道的预发布（--minor --pre alpha → 0.2.0-alpha.1）。
  --prerelease    只递增预发布序号（0.1.0-alpha.1 → 0.1.0-alpha.2）。
  --stable        把当前这条预发布线转正（0.1.0-alpha.3 → 0.1.0）。
  --version X     直接指定，跳过一切推算。

它只改工作区里的两个文件，不提交、不打 tag、不推送——发版的触发条件是手工打 tag。
改完会打印该跑的三条命令，以及这次发版说明的变更部分预览。"""


def _version(text: str):
    from packaging.version import Version

    return Version(text)


def friendly(version: str) -> str:
    """PEP 440 的任意写法 → 面向用户的那一种（``0.1.0a2`` → ``0.1.0-alpha.2``）。"""
    parsed = _version(version)
    core = ".".join(str(part) for part in (*parsed.release, 0, 0)[:3])
    if parsed.pre is None:
        return core
    letter, number = parsed.pre
    return f"{core}-{SPELLING.get(letter, letter)}.{number}"


def canonical(version: str) -> str:
    """→ PEP 440 规范形式（``0.1.0-alpha.2`` → ``0.1.0a2``），进 ``pyproject.toml``。"""
    return str(_version(version))


def classify(commits: list[release_notes.Commit]) -> dict[str, int]:
    """按类型数一遍提交。``other`` 里是文档、测试、杂项与认不出前缀的。"""
    counts = dict.fromkeys(("breaking", "feat", "fix", "perf", "other"), 0)
    for commit in commits:
        head = release_notes._HEADER.match(commit.subject)
        kind = (head["type"].lower() if head else "") if head else ""
        if commit.breaking:
            counts["breaking"] += 1
        elif kind in {"feat", "feature"}:
            counts["feat"] += 1
        elif kind in {"fix", "bugfix"}:
            counts["fix"] += 1
        elif kind == "perf":
            counts["perf"] += 1
        else:
            counts["other"] += 1
    return counts


def suggest_bump(counts: dict[str, int], *, zero_major: bool) -> tuple[str | None, str]:
    """提交记录 → 建议的级别与**理由**（理由要打印出来：它是你复核这个建议的唯一材料）。"""
    if counts["breaking"]:
        if zero_major:
            return "minor", (
                f"{counts['breaking']} 条不兼容变更，但主版本还是 0"
                "——0.x 期间不兼容变更走 minor（升到 1.0.0 是「这东西定型了」的宣告，"
                "不该由一条提交前缀替你做）"
            )
        return "major", f"{counts['breaking']} 条不兼容变更"
    if counts["feat"]:
        return "minor", f"{counts['feat']} 条 feat"
    if counts["fix"] or counts["perf"]:
        return "patch", f"{counts['fix']} 条 fix、{counts['perf']} 条 perf"
    return None, f"没有 feat / fix / perf / 不兼容变更（另有 {counts['other']} 条文档或杂项）"


def apply_bump(current: str, bump: str, *, channel: str | None = None) -> str:
    """按级别抬 core，**丢掉原有的预发布后缀**。

    ``--minor`` 作用在 ``0.1.0-alpha.1`` 上给的是 ``0.2.0`` 而不是 ``0.2.0-alpha.1``：
    要后者就再加 ``--pre alpha``。一个开关只做一件事，比一个开关按当前状态给出两种
    结果好记。
    """
    if bump not in BUMPS:
        raise SystemExit(f"不认识的级别 {bump}（只有 {'/'.join(BUMPS)}）")
    major, minor, patch = (*_version(current).release, 0, 0)[:3]
    if bump == "major":
        major, minor, patch = major + 1, 0, 0
    elif bump == "minor":
        minor, patch = minor + 1, 0
    else:
        patch += 1
    core = f"{major}.{minor}.{patch}"
    return f"{core}-{channel}.1" if channel else core


def bump_prerelease(current: str, *, channel: str | None = None) -> str:
    """递增预发布序号；给了 ``channel`` 就换通道并从 1 开始。"""
    parsed = _version(current)
    core = ".".join(str(part) for part in (*parsed.release, 0, 0)[:3])
    if channel:
        letter = CHANNELS[channel]
        if parsed.pre is not None and parsed.pre[0] == letter:
            return f"{core}-{SPELLING[letter]}.{parsed.pre[1] + 1}"
        return f"{core}-{SPELLING[letter]}.1"
    if parsed.pre is None:
        raise SystemExit(
            f"{current} 不是预发布，没有序号可递增。"
            "先决定要发哪个版本的预发布，例如 --minor --pre alpha。"
        )
    letter, number = parsed.pre
    return f"{core}-{SPELLING.get(letter, letter)}.{number + 1}"


def to_stable(current: str) -> str:
    """把预发布线转正：``0.1.0-alpha.3`` → ``0.1.0``。"""
    parsed = _version(current)
    if parsed.pre is None and not parsed.is_devrelease:
        raise SystemExit(f"{current} 已经是正式版了。")
    return ".".join(str(part) for part in (*parsed.release, 0, 0)[:3])


def write_version(version: str, *, root: Path = ROOT) -> list[tuple[Path, str]]:
    """把两处字面量改成同一个版本，返回 ``(文件, 写进去的字符串)``。

    每处都要求**恰好命中一次**：零次或多次都说明文件结构变了，而静默漏改一处的后果是
    ``tests/unit/test_version.py`` 红掉。那个红是好事，但更好的是这里就不让它发生。

    读写都用 ``newline=""``：不改动原文件的行尾。用 ``read_text`` 会把 CRLF 读成 LF，
    写回去就等于顺手把整个文件的行尾换掉——一次版本号 bump 变成一份满屏 diff。
    """
    written: list[tuple[Path, str]] = []
    for relative, pattern, form in VERSION_FILES:
        path = root / relative
        with path.open(encoding="utf-8", newline="") as handle:
            text = handle.read()
        found = pattern.findall(text)
        if len(found) != 1:
            raise SystemExit(
                f"{relative} 里匹配到 {len(found)} 处版本字面量（应当恰好 1 处）——"
                "文件结构变了，release_prepare 的正则要跟着改。"
            )
        wanted = friendly(version) if form == "user" else canonical(version)
        replaced = pattern.sub(
            lambda match, target=wanted: match.group(0).replace(match.group(1), target),
            text,
            count=1,
        )
        with path.open("w", encoding="utf-8", newline="") as handle:
            handle.write(replaced)
        written.append((path, wanted))
    return written


def read_versions(*, root: Path = ROOT) -> dict[str, str]:
    """读回两处字面量，供改完之后自检。"""
    values: dict[str, str] = {}
    for relative, pattern, _form in VERSION_FILES:
        with (root / relative).open(encoding="utf-8", newline="") as handle:
            found = pattern.findall(handle.read())
        values[relative] = found[0] if found else ""
    return values


def _maybe_canonical(text: str) -> str | None:
    from packaging.version import InvalidVersion

    try:
        return canonical(text)
    except InvalidVersion:
        return None


def is_released(version: str, tags: list[str]) -> bool:
    """这个版本有没有对应的 tag。

    按 PEP 440 规范化之后比：``v0.1.0a1`` 与 ``v0.1.0-alpha.1`` 是同一个版本，
    而"已经发过了"这个判断错一次的代价是把同一个版本再发一遍。
    """
    target = _maybe_canonical(version)
    return any(_maybe_canonical(release_notes.version_of(tag)) == target for tag in tags)


@dataclass(frozen=True, slots=True)
class Plan:
    """这次准备要做什么。``version`` 与 ``current`` 相同时表示"什么都不用改"。"""

    current: str
    version: str
    reason: str
    counts: dict[str, int] = field(default_factory=dict)
    nearest: str | None = None
    baseline: str | None = None

    @property
    def changed(self) -> bool:
        return canonical(self.version) != canonical(self.current)

    @property
    def tag(self) -> str:
        return f"v{friendly(self.version)}"


def decide(
    current: str, *, counts: dict[str, int], released: bool, mode: str | None, channel: str | None
) -> tuple[str, str]:
    """→ ``(下一个版本, 理由)``。理由会被打印出来：它是复核这个建议的唯一材料。"""
    if mode in BUMPS:
        return apply_bump(current, mode, channel=channel), f"你指定了 --{mode}"
    if mode == "prerelease":
        target = bump_prerelease(current, channel=channel)
        return target, f"你指定了 --prerelease{f' --pre {channel}' if channel else ''}"
    if mode == "stable":
        return to_stable(current), "你指定了 --stable"
    if not released:
        return current, f"{current} 还没有发过（没有对应的 tag）——不用改版本号，直接打 tag"
    if _version(current).pre is not None:
        return bump_prerelease(current, channel=channel), "当前是预发布，默认递增序号"
    bump, reason = suggest_bump(counts, zero_major=_version(current).release[0] == 0)
    if bump is None:
        raise SystemExit(
            f"{reason}——按提交记录不该发版。真要发就自己定级别："
            "--patch / --minor / --major，或者 --version X。"
        )
    return apply_bump(current, bump, channel=channel), reason


def plan(argv: list[str], *, current: str = __version__, cwd: Path | None = None) -> Plan:
    """把命令行与 git 历史合成一个 :class:`Plan`，不动任何文件。"""
    channel = release_notes._argument(argv, "--pre")
    if channel is not None:
        if channel.lower() not in CHANNELS:
            raise SystemExit(f"--pre 只认 alpha / beta / rc，收到 {channel}")
        channel = SPELLING[CHANNELS[channel.lower()]]

    mode = next((name for name in (*BUMPS, "prerelease", "stable") if f"--{name}" in argv), None)
    if mode is None and channel:
        # 只给了 --pre：那是"换个通道"，等价于 --prerelease --pre X。
        mode = "prerelease"

    tags = release_notes.tags_in_history("HEAD", cwd=cwd)
    nearest = tags[0] if tags else None
    # **判级别用"自最近一个 tag 以来"的提交**：问的是"上次发出去之后攒了多大的改动"，
    # 与发版说明的基线（按同类选，见 release_notes.baseline_from）是两个不同的问题。
    counts = classify(release_notes.commits_between(nearest, "HEAD", cwd=cwd))

    explicit = release_notes._argument(argv, "--version")
    if explicit:
        version, reason = friendly(explicit), "你直接指定了版本号"
    else:
        version, reason = decide(
            current,
            counts=counts,
            released=is_released(current, tags),
            mode=mode,
            channel=channel,
        )
    version = friendly(version)
    # 预览的基线按**新版本**的类别选：那才是发版说明真正会用的那一个。
    baseline = release_notes.baseline_from(
        tags, prerelease=release_notes.is_prerelease_tag(f"v{version}")
    )
    return Plan(
        current=current,
        version=version,
        reason=reason,
        counts=counts,
        nearest=nearest,
        baseline=baseline,
    )


def describe(item: Plan, *, written: list[tuple[Path, str]] | None = None) -> str:
    """打印出来的那一屏。"""
    lines = [
        f"当前版本  {item.current}",
        f"下一个    {item.version}   （{item.reason}）",
        f"tag       {item.tag}",
    ]
    since = f"自 {item.nearest} 以来" if item.nearest else "自项目开始以来"
    counted = "、".join(
        f"{count} 条 {label}"
        for label, count in (
            ("不兼容", item.counts.get("breaking", 0)),
            ("feat", item.counts.get("feat", 0)),
            ("fix", item.counts.get("fix", 0)),
            ("perf", item.counts.get("perf", 0)),
            ("其他", item.counts.get("other", 0)),
        )
        if count
    )
    lines.append(f"提交      {since}：{counted or '无'}")
    if item.baseline:
        lines.append(f"说明基线  {item.baseline}（同类的上一个 tag）")
    else:
        lines.append("说明基线  无（发版说明会列出全部历史）")

    if not item.changed:
        lines.append("\n版本号不用改。接下来：")
    elif written:
        lines.append("\n已改：")
        for path, value in written:
            lines.append(f"  {path.relative_to(ROOT).as_posix()}  →  {value}")
        lines.append("\n接下来：")
    else:
        lines.append("\n（--dry-run：没动任何文件）如果照这个方案来，接下来是：")

    if item.changed:
        paths = " ".join(relative for relative, _pattern, _form in VERSION_FILES)
        lines += [
            f"  git add {paths}",
            f'  git commit -m "chore: 发版 {item.version}"',
        ]
    lines.append(f"  git tag {item.tag}")
    # 版本号没改就没有要提交的东西，也就不必先 push 分支。
    lines.append(
        f"  git push && git push origin {item.tag}"
        if item.changed
        else f"  git push origin {item.tag}"
    )
    lines += [
        "",
        "推 tag 之前先看一眼发版说明：",
        "  .venv/Scripts/python tools/release_notes.py --no-artifacts",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if "--help" in argv or "-h" in argv:
        print(USAGE)
        return 0
    item = plan(argv)
    written: list[tuple[Path, str]] | None = None
    if item.changed and "--dry-run" not in argv:
        written = write_version(item.version)
        # 自检：两处字面量必须规范化后相等，这正是 tests/unit/test_version.py 守的那条。
        values = read_versions()
        if len({_maybe_canonical(value) for value in values.values()}) != 1:
            raise SystemExit(f"写完之后两处版本号不一致：{values}")
    print(describe(item, written=written))
    return 0


if __name__ == "__main__":
    sys.exit(main())
