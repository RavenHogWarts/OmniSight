"""发版前的版本号准备（10 文档 §11.5 第 1 步，`tools/release_prepare.py`）。

这个脚本存在的理由是**版本号有两处字面量**：`src/omnisight/__init__.py` 的
`__version__`（面向用户的 `0.1.0-alpha.2`）与 `pyproject.toml` 的 `version`（PEP 440
规范形式 `0.1.0a2`）。手改两处、还要记住两种写法，是那种迟早出错、而且要等到发版
流水线第一步（`release_notes.py --check-only`）才发现的事——那时 tag 已经打完了。

因此这里钉的是三件事：

* **写进去的两处规范化后必须相等**，且改的只有那一行（不顺手把行尾换掉）；
* **推算规则可预测**：0.x 期间的不兼容变更走 minor 而不是 major（升 1.0.0 是"定型了"
  的宣告，不该由一条提交前缀替人做）；预发布线上默认递增序号而不是跳 core；
* **两种"当前版本还没发过"与"已经发过"的分岔**：前者的答案是"什么都不用改，直接打
  tag"，而一个只会 bump 的工具会在这里把版本号白抬一格。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
for entry in (TOOLS, ROOT / "src"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

import release_notes  # noqa: E402
import release_prepare  # noqa: E402
from omnisight import __version__  # noqa: E402


def _commits(*subjects: str) -> list[release_notes.Commit]:
    return [
        release_notes.Commit(sha=f"{index:07x}", subject=subject)
        for index, subject in enumerate(subjects, start=1)
    ]


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """一份只含两处版本字面量的最小"仓库"，行尾刻意混用。"""
    root = tmp_path / "repo"
    (root / "src" / "omnisight").mkdir(parents=True)
    (root / "src" / "omnisight" / "__init__.py").write_bytes(
        b'"""doc."""\r\n\r\n__version__ = "0.1.0-alpha.1"\r\n\r\nAPP_NAME = "OmniSight"\r\n'
    )
    (root / "pyproject.toml").write_bytes(
        b'[project]\nname = "omnisight"\nversion = "0.1.0a1"\nrequires-python = ">=3.12"\n'
        b'\n[tool.ruff]\ntarget-version = "py312"\n'
    )
    return root


# ── 两种写法 ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("given", "user_facing", "pep440"),
    [
        ("0.1.0-alpha.1", "0.1.0-alpha.1", "0.1.0a1"),
        ("0.1.0a1", "0.1.0-alpha.1", "0.1.0a1"),
        ("0.2.0-beta.3", "0.2.0-beta.3", "0.2.0b3"),
        ("1.0.0-rc.2", "1.0.0-rc.2", "1.0.0rc2"),
        ("1.0.0", "1.0.0", "1.0.0"),
        ("1.2", "1.2.0", "1.2"),
    ],
)
def test_the_two_spellings_of_one_version(given, user_facing, pep440):
    assert release_prepare.friendly(given) == user_facing
    assert release_prepare.canonical(given) == pep440


# ── 推算级别 ────────────────────────────────────────────────────────────


def test_commits_are_counted_by_type():
    counts = release_prepare.classify(
        _commits("feat: 甲", "feat: 乙", "fix: 丙", "perf: 丁", "docs: 戊", "随手改的")
    )
    assert counts == {"breaking": 0, "feat": 2, "fix": 1, "perf": 1, "other": 2}


def test_a_breaking_change_outranks_everything_else():
    counts = release_prepare.classify(_commits("feat!: 换掉配置格式", "feat: 乙", "fix: 丙"))
    assert counts["breaking"] == 1 and counts["feat"] == 1


def test_a_breaking_change_before_1_0_is_a_minor_bump():
    """0.x 期间不兼容变更不必升主版本（semver §4）。升到 1.0.0 是"这东西定型了"的
    宣告，不该由一条提交前缀替人做出来。
    """
    counts = release_prepare.classify(_commits("feat!: 换掉配置格式"))
    bump, reason = release_prepare.suggest_bump(counts, zero_major=True)
    assert bump == "minor"
    assert "主版本还是 0" in reason
    assert release_prepare.suggest_bump(counts, zero_major=False)[0] == "major"


@pytest.mark.parametrize(
    ("subjects", "bump"),
    [
        (("feat: 甲", "fix: 乙"), "minor"),
        (("fix: 甲",), "patch"),
        (("perf: 甲",), "patch"),
        (("docs: 甲", "chore: 乙"), None),
        ((), None),
    ],
)
def test_the_suggested_level_follows_the_commits(subjects, bump):
    counts = release_prepare.classify(_commits(*subjects))
    assert release_prepare.suggest_bump(counts, zero_major=True)[0] == bump


# ── 抬版本号 ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("current", "bump", "expected"),
    [
        ("0.1.0", "patch", "0.1.1"),
        ("0.1.0", "minor", "0.2.0"),
        ("0.1.0", "major", "1.0.0"),
        # 预发布后缀被丢掉：--minor 要的是 0.2.0；要 0.2.0-alpha.1 就再加 --pre alpha。
        ("0.1.0-alpha.3", "minor", "0.2.0"),
        ("0.1.0-alpha.3", "patch", "0.1.1"),
    ],
)
def test_a_level_bump_drops_the_prerelease_suffix(current, bump, expected):
    assert release_prepare.apply_bump(current, bump) == expected


def test_a_level_bump_can_start_a_new_prerelease_line():
    assert release_prepare.apply_bump("0.1.0", "minor", channel="alpha") == "0.2.0-alpha.1"
    assert release_prepare.apply_bump("0.9.0", "major", channel="rc") == "1.0.0-rc.1"


def test_an_unknown_level_is_refused():
    with pytest.raises(SystemExit, match="major"):
        release_prepare.apply_bump("0.1.0", "tiny")


def test_a_prerelease_bump_only_moves_the_counter():
    assert release_prepare.bump_prerelease("0.1.0-alpha.1") == "0.1.0-alpha.2"
    assert release_prepare.bump_prerelease("0.1.0a9") == "0.1.0-alpha.10"
    assert release_prepare.bump_prerelease("1.0.0-rc.1") == "1.0.0-rc.2"


def test_switching_channel_restarts_the_counter():
    assert release_prepare.bump_prerelease("0.1.0-alpha.3", channel="beta") == "0.1.0-beta.1"
    # 同一个通道给了 --pre 也只是递增，不会白重置回 1。
    assert release_prepare.bump_prerelease("0.1.0-beta.2", channel="beta") == "0.1.0-beta.3"


def test_a_stable_version_has_no_counter_to_bump():
    with pytest.raises(SystemExit, match="--minor --pre alpha"):
        release_prepare.bump_prerelease("1.0.0")


def test_promoting_a_prerelease_line_just_drops_the_suffix():
    assert release_prepare.to_stable("0.1.0-alpha.3") == "0.1.0"
    assert release_prepare.to_stable("1.0.0rc1") == "1.0.0"
    with pytest.raises(SystemExit, match="已经是正式版"):
        release_prepare.to_stable("1.0.0")


# ── 决定：发过没发过是分岔口 ────────────────────────────────────────────


def test_a_version_that_was_never_tagged_needs_no_bump():
    """一个只会 bump 的工具会在这里把版本号白抬一格，而正确答案是"直接打 tag"。"""
    version, reason = release_prepare.decide(
        "0.1.0-alpha.1",
        counts=release_prepare.classify(_commits("feat: 甲")),
        released=False,
        mode=None,
        channel=None,
    )
    assert version == "0.1.0-alpha.1"
    assert "没有发过" in reason


def test_a_released_prerelease_moves_to_the_next_prerelease():
    version, reason = release_prepare.decide(
        "0.1.0-alpha.1",
        counts=release_prepare.classify(_commits("feat: 甲")),
        released=True,
        mode=None,
        channel=None,
    )
    assert version == "0.1.0-alpha.2"
    assert "递增序号" in reason


def test_a_released_stable_follows_the_commits():
    counts = release_prepare.classify(_commits("feat: 甲"))
    version, _reason = release_prepare.decide(
        "0.1.0", counts=counts, released=True, mode=None, channel=None
    )
    assert version == "0.2.0"


def test_nothing_worth_releasing_refuses_and_says_how_to_override():
    counts = release_prepare.classify(_commits("docs: 甲"))
    with pytest.raises(SystemExit, match="--patch"):
        release_prepare.decide("0.1.0", counts=counts, released=True, mode=None, channel=None)


def test_an_explicit_mode_wins_over_the_suggestion():
    counts = release_prepare.classify(_commits("docs: 甲"))
    for mode, expected in (("patch", "0.1.1"), ("minor", "0.2.0"), ("major", "1.0.0")):
        version, reason = release_prepare.decide(
            "0.1.0", counts=counts, released=True, mode=mode, channel=None
        )
        assert version == expected
        assert f"--{mode}" in reason


def test_is_released_compares_normalized_versions_and_ignores_junk_tags():
    tags = ["随手打的一个 tag", "v0.1.0a1", "v0.0.9"]
    assert release_prepare.is_released("0.1.0-alpha.1", tags)
    assert release_prepare.is_released("0.0.9", tags)
    assert not release_prepare.is_released("0.1.0", tags)


# ── 落到文件里 ──────────────────────────────────────────────────────────


def test_both_literals_are_written_in_their_own_spelling(repo: Path):
    written = release_prepare.write_version("0.2.0-beta.1", root=repo)
    values = release_prepare.read_versions(root=repo)
    assert values["src/omnisight/__init__.py"] == "0.2.0-beta.1"  # 面向用户
    assert values["pyproject.toml"] == "0.2.0b1"  # PEP 440 规范形式
    # 两处规范化后相等，正是 tests/unit/test_version.py 守的那条。
    assert len({release_prepare.canonical(value) for value in values.values()}) == 1
    assert [path.name for path, _value in written] == ["__init__.py", "pyproject.toml"]


def test_writing_does_not_touch_the_line_endings(repo: Path):
    """用 read_text 会把 CRLF 读成 LF，写回去就等于顺手换掉整个文件的行尾——
    一次版本号 bump 变成一份满屏 diff。
    """
    before = (repo / "src" / "omnisight" / "__init__.py").read_bytes()
    release_prepare.write_version("0.2.0", root=repo)
    after = (repo / "src" / "omnisight" / "__init__.py").read_bytes()
    assert after.count(b"\r\n") == before.count(b"\r\n")
    assert b'__version__ = "0.2.0"\r\n' in after
    # pyproject 那份原本是 LF，也不该被换成 CRLF。
    assert b"\r\n" not in (repo / "pyproject.toml").read_bytes()


def test_only_the_version_line_changes(repo: Path):
    """``target-version = "py312"`` 与 ``requires-python`` 就在同一个文件里，
    正则不锚在行首的话会改错行。
    """
    release_prepare.write_version("0.2.0", root=repo)
    text = (repo / "pyproject.toml").read_text(encoding="utf-8")
    assert 'target-version = "py312"' in text
    assert 'requires-python = ">=3.12"' in text
    assert 'version = "0.2.0"' in text


def test_a_file_whose_shape_changed_fails_loudly(repo: Path):
    (repo / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="恰好 1 处"):
        release_prepare.write_version("0.2.0", root=repo)


def test_the_real_repository_still_matches_both_patterns():
    """这两条正则是这个脚本能工作的前提。文件结构一动，这里立刻红。"""
    values = release_prepare.read_versions()
    assert values["src/omnisight/__init__.py"] == __version__
    assert values["pyproject.toml"] == release_prepare.canonical(__version__)


# ── 那一屏输出 ──────────────────────────────────────────────────────────


def test_the_printout_gives_the_exact_commands_to_run():
    item = release_prepare.Plan(
        current="0.1.0-alpha.1", version="0.1.0-alpha.2", reason="当前是预发布，默认递增序号"
    )
    text = release_prepare.describe(item, written=[(release_prepare.ROOT / "pyproject.toml", "x")])
    assert "git tag v0.1.0-alpha.2" in text
    assert 'git commit -m "chore: 发版 0.1.0-alpha.2"' in text
    assert "git push origin v0.1.0-alpha.2" in text
    assert "release_notes.py --no-artifacts" in text  # 推 tag 之前该看的那一眼


def test_nothing_to_commit_means_no_commit_command():
    item = release_prepare.Plan(
        current="0.1.0-alpha.1", version="0.1.0-alpha.1", reason="还没有发过"
    )
    text = release_prepare.describe(item)
    assert not item.changed
    assert "git commit" not in text and "版本号不用改" in text
    assert "git tag v0.1.0-alpha.1" in text


def test_a_dry_run_says_that_nothing_was_touched():
    item = release_prepare.Plan(current="0.1.0", version="0.2.0", reason="1 条 feat")
    assert "没动任何文件" in release_prepare.describe(item, written=None)


def test_the_plan_names_the_tag_in_the_user_facing_spelling():
    item = release_prepare.Plan(current="0.1.0", version="0.1.0a2", reason="x")
    assert item.tag == "v0.1.0-alpha.2"
    assert item.changed
