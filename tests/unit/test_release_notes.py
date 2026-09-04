"""发版说明与发版流水线（10 文档 §11）。

发版的触发条件是**手工打 tag**（`v0.1.0-alpha.1` / `v0.1.0`），此后全自动。也就是
说：从"推一个 tag"到"一个陌生人下载到一个 EXE"之间没有任何人再看一眼。这里钉住
的正是那条路上会**静默**出错的几处——它们的共同点是失败时看起来像成功：

* **tag 与代码里的 `__version__` 对不上**：产物照样构建、Release 照样建，只是发布页
  与它发出去的文件各说各话，而用户核对属性页后唯一合理的解释是"文件被人换过"；
* **预发布判定各写一遍**：迟早出现一个挂着 GitHub "Latest release" 徽章、属性页却
  写着预发布的产物。判定只有一处（`version_info.is_prerelease`，EXE 属性页同源）；
* **浅克隆**：`actions/checkout` 默认深度 1，此时 `git log` 取不到上一个 tag，变更
  日志变空且不报错；
* **校验值与产物不符**：截断的摘要、上一次构建残留的 `.sha256`、算完摘要之后又被
  改动的产物——三种都会让用户核对失败，而"校验不上"在他那边只有一种解释；
* **裸 EXE 被挂上 Release**：它带不走许可正文与说明，等于给出一条绕开分发义务的
  下载路径。

最后几条断言对着 `.github/workflows/release.yml` 的正文——与 `test_build_assemble.py`
断言 `.iss` 是同一个理由：那份文件里的错误只有在真的发一次版时才看得出来。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
for entry in (TOOLS, ROOT / "src"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

import build  # noqa: E402
import release_notes  # noqa: E402
import version_info  # noqa: E402
from omnisight import APP_NAME, __version__  # noqa: E402

WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"
TAG = f"v{__version__}"


@pytest.fixture
def released(tmp_path: Path) -> Path:
    """一个"刚跑完 --release"的 dist/：两件发布物、各自的 .sha256，以及裸 EXE。

    裸 EXE 一并放进来是有意的：它是构建产物、要被杀软扫、但**不发布**，而这条边界
    正是下面几个用例要钉的东西。
    """
    dist = tmp_path / "dist"
    dist.mkdir()
    published = set(build.published_names())
    for name in (*published, build._executable_name()):
        path = dist / name
        path.write_bytes(f"payload of {name}".encode())
        if name in published:
            digest = build.sha256_of(path)
            (dist / f"{name}.sha256").write_text(f"{digest}  {name}\n", encoding="utf-8")
    return dist


def _commits(*subjects: str) -> list[release_notes.Commit]:
    return [
        release_notes.Commit(sha=f"{index:07x}", subject=subject)
        for index, subject in enumerate(subjects, start=1)
    ]


def _workflow() -> str:
    """流水线的**有效内容**：注释行剔掉。

    不剔的话，断言会命中注释里提到的东西——"push 与 pull_request 上不再有 job"
    这句话本身就会让"没有 pull_request 触发器"那条用例通过或失败得毫无意义。
    """
    lines = WORKFLOW.read_text(encoding="utf-8").splitlines()
    return "\n".join(line for line in lines if not line.strip().startswith("#"))


# ── 变更日志：以 git 提交记录为准 ───────────────────────────────────────


@pytest.mark.parametrize(
    ("subject", "section", "summary"),
    [
        ("feat: 完成 M6 发布准备", "新增", "完成 M6 发布准备"),
        ("fix: ACL 判断修复", "修复", "ACL 判断修复"),
        ("fix(tray): 图标不变灰", "修复", "tray: 图标不变灰"),
        ("perf: 应用热力图改点查", "性能", "应用热力图改点查"),
        ("refactor: 拆开采集管道", "重构", "拆开采集管道"),
        ("docs: 补 faq 里的杀软那一节", "文档", "补 faq 里的杀软那一节"),
        ("tests: 补两条断言", "测试", "补两条断言"),
        ("chore: 升级 ruff", "构建与杂项", "升级 ruff"),
        ("ci: 换 runner", "构建与杂项", "换 runner"),
        ("revert: 撤回上一条", "回退", "撤回上一条"),
        ("feat!: 换掉配置文件格式", "不兼容变更", "换掉配置文件格式"),
        ("fix(storage)!: 重建聚合表", "不兼容变更", "storage: 重建聚合表"),
        # 认不出前缀的照样出现——分类是附加价值，不是准入门槛。
        ("随手改了点东西", "其他", "随手改了点东西"),
        ("Merge branch 'x'", "其他", "Merge branch 'x'"),
        ("WIP: 待续", "其他", "WIP: 待续"),
    ],
)
def test_a_commit_lands_in_its_section_with_the_prefix_stripped(subject, section, summary):
    commit = release_notes.Commit(sha="abc1234", subject=subject)
    assert commit.section == section
    assert commit.summary == summary


def test_no_commit_is_ever_dropped():
    """一条提交从发版说明里消失，是"以 git 记录为准"这句话唯一不能出的错。"""
    subjects = ("feat: 甲", "随手改的", "fix: 乙", "chore: 丙", "feat!: 丁")
    commits = _commits(*subjects)
    body = release_notes.render_changelog(commits, tag=TAG)
    assert all(commit.sha in body for commit in commits)
    assert sum(len(bucket) for _title, bucket in release_notes.group(commits)) == len(subjects)


def test_breaking_changes_are_rendered_first():
    """它是唯一"不看就会踩到"的一类，排在后面等于没写。"""
    body = release_notes.render_changelog(_commits("feat: 甲", "feat!: 破坏性的乙"), tag=TAG)
    assert body.index("### 不兼容变更") < body.index("### 新增")


def test_the_first_release_says_so_instead_of_pointing_at_a_tag_that_does_not_exist():
    body = release_notes.render_changelog(_commits("feat: 甲"), tag=TAG, previous=None)
    assert "首个发布" in body
    assert "以来" not in body


def test_two_tags_on_one_commit_are_stated_not_shown_as_an_empty_section():
    """把 alpha 原样转正时提交范围是空的——这是正确结果，不是故障。"""
    body = release_notes.render_changelog([], tag="v0.1.0", previous="v0.1.0-alpha.1")
    assert "没有新提交" in body
    assert "###" not in body


def test_sha_links_appear_only_when_the_repository_is_known():
    commits = _commits("feat: 甲")
    linked = release_notes.render_changelog(commits, tag=TAG, repo="owner/name")
    plain = release_notes.render_changelog(commits, tag=TAG, repo=None)
    assert "https://github.com/owner/name/commit/" in linked
    assert "https://" not in plain  # 猜一个仓库地址比不给链接更坏


def test_parse_log_splits_on_the_unit_separator_not_on_whitespace():
    """提交标题里出现制表符罕见但合法，而一次错切会把标题的一半当成 sha。"""
    commits = release_notes.parse_log("abc1234\x1ffeat: 带\t制表符 的标题\n\nfeed999\x1ffix: 乙")
    assert [commit.sha for commit in commits] == ["abc1234", "feed999"]
    assert commits[0].summary == "带\t制表符 的标题"


# ── tag 与版本号 ────────────────────────────────────────────────────────


def test_a_tag_that_disagrees_with_the_code_is_refused_before_anything_is_built():
    with pytest.raises(SystemExit) as failure:
        release_notes.verify_tag("v0.2.0", "0.1.0-alpha.1")
    message = str(failure.value)
    assert "__version__" in message and "pyproject.toml" in message
    assert "v0.1.0-alpha.1" in message  # 直接给出该用的那个 tag，省一次翻文档


def test_the_two_pep440_spellings_of_one_version_are_the_same_version():
    """``v0.1.0a1`` 与 ``0.1.0-alpha.1`` 按 PEP 440 相等，拒绝它只会逼人去查规范。"""
    assert release_notes.verify_tag("v0.1.0a1", "0.1.0-alpha.1") == "0.1.0-alpha.1"
    assert release_notes.verify_tag("0.1.0-alpha.1", "0.1.0-alpha.1") == "0.1.0-alpha.1"
    assert release_notes.verify_tag(TAG) == __version__


def test_the_returned_version_is_the_one_the_artifacts_display():
    """标题写 tag 上的拼法、属性页写另一种，是没必要制造的第二处不一致。"""
    assert release_notes.verify_tag("v0.1.0a1", "0.1.0-alpha.1") != "0.1.0a1"


def test_check_only_verifies_and_stops(capsys):
    """流水线最前面那一步：只核对，不生成、不构建、不联网。"""
    assert release_notes.main(["--tag", TAG, "--check-only"]) == 0
    printed = capsys.readouterr().out
    assert TAG in printed and __version__ in printed and "一致" in printed


def test_check_only_of_a_wrong_tag_fails_the_pipeline():
    with pytest.raises(SystemExit):
        release_notes.main(["--tag", "v9.9.9", "--check-only"])


def test_the_current_tag_is_what_the_pipeline_expects():
    """这条是给"改了版本号忘了改 tag 格式"留的：v + 版本串，别的写法这条会红。"""
    assert release_notes.tag_for() == f"v{__version__}"
    assert release_notes.version_of(release_notes.tag_for()) == __version__


# ── 预发布还是正式版 ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("version", "prerelease"),
    [
        ("0.0.1-alpha.1", True),
        ("0.1.0-beta.1", True),
        ("1.0.0-rc.1", True),
        ("0.1.0a1", True),
        ("0.0.1", False),
        ("1.0.0", False),
    ],
)
def test_prerelease_is_decided_by_the_version_string(version, prerelease):
    values = release_notes.github_outputs(tag=f"v{version}", version=version)
    assert values["prerelease"] == ("true" if prerelease else "false")
    assert ("（预发布）" in values["title"]) is prerelease
    # 与 EXE 属性页那个"（预发布）"标记同源：两处各写一遍判定迟早会不一致。
    assert values["prerelease"] == ("true" if version_info.is_prerelease(version) else "false")


def test_the_release_title_names_the_product_and_the_version():
    values = release_notes.github_outputs(tag="v1.0.0", version="1.0.0")
    assert values["title"] == f"{APP_NAME} 1.0.0"


def test_a_prerelease_body_says_so_at_the_top():
    """Release 页面上那个徽章容易被漏看，正文第一行不会。"""
    alpha = release_notes.render(
        tag="v0.1.0-alpha.1", commits=_commits("feat: 甲"), version="0.1.0-alpha.1"
    )
    assert alpha.startswith("> **预发布版本 0.1.0-alpha.1")
    stable = release_notes.render(tag="v1.0.0", commits=_commits("feat: 甲"), version="1.0.0")
    assert "预发布" not in stable


# ── 出参：流水线拿它决定挂什么、发成什么 ─────────────────────────────


def test_outputs_are_written_only_inside_actions(tmp_path: Path):
    assert release_notes.emit_github_outputs({"tag": TAG}, {}) is None
    target = tmp_path / "outputs.txt"
    assert release_notes.emit_github_outputs({"tag": TAG}, {"GITHUB_OUTPUT": str(target)}) == target
    assert target.read_text(encoding="utf-8") == f"tag={TAG}\n"


def test_every_output_value_stays_on_one_line():
    """``$GITHUB_OUTPUT`` 是按行解析的：任何一个值里带换行，后面的键会静默丢失。"""
    values = release_notes.github_outputs(tag=TAG, version=__version__)
    assert all("\n" not in value for value in values.values())
    assert set(values) == {"tag", "version", "prerelease", "title", "assets"}


def test_assets_are_handed_over_as_repo_relative_paths():
    asset = release_notes.Asset(path=release_notes.DIST / build.portable_name(), digest="0" * 64)
    values = release_notes.github_outputs(tag=TAG, version=__version__, assets=[asset])
    assert values["assets"] == f"dist/{build.portable_name()}"


def test_a_path_with_a_space_is_refused_instead_of_silently_split():
    asset = release_notes.Asset(path=Path("D:/some dir/OmniSight-Setup.exe"), digest="0" * 64)
    with pytest.raises(SystemExit, match="空格"):
        release_notes.github_outputs(tag=TAG, version=__version__, assets=[asset])


# ── 发布物与校验值 ──────────────────────────────────────────────────────


def test_the_bare_exe_is_never_attached_to_a_release(released: Path):
    """它带不走 LICENSE、许可清单与 README.txt——发布页上多挂一个它，等于给出一条
    绕开分发义务的下载路径（``build.published_names`` 的理由）。
    """
    names = [item.name for item in release_notes.collect(released)]
    assert names == [build.installer_name(), build.portable_name()]
    assert build._executable_name() not in names


def test_the_installer_comes_first_because_that_is_what_most_people_want(released: Path):
    assert release_notes.collect(released)[0].name == build.installer_name()


def test_a_missing_artifact_stops_the_release(released: Path):
    """Release 页面上"这次只发了便携版"与"安装包没构建出来"长得一模一样。"""
    (released / build.installer_name()).unlink()
    with pytest.raises(SystemExit, match="找不到发布物"):
        release_notes.collect(released)


def test_a_missing_checksum_file_stops_the_release(released: Path):
    """``.sha256`` 要随产物一起发布——用户核对下载靠它。"""
    (released / f"{build.portable_name()}.sha256").unlink()
    with pytest.raises(SystemExit, match=r"\.sha256"):
        release_notes.collect(released)


def test_a_checksum_that_does_not_match_the_artifact_stops_the_release(released: Path):
    """摘要算完之后产物又被改动过，或者 dist/ 里混着上一次构建的残留。发出去的话，
    用户核对失败时唯一的解释是"这个文件被人动过"。
    """
    name = build.portable_name()
    (released / f"{name}.sha256").write_text(f"{'0' * 64}  {name}\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="不一致"):
        release_notes.collect(released)


def test_the_body_gives_the_full_digest_and_the_command_to_check_it(released: Path):
    assets = release_notes.collect(released)
    text = release_notes.render(
        tag=TAG, commits=_commits("feat: 甲"), assets=assets, signed=False
    )
    for item in assets:
        assert item.digest in text  # 截断的摘要没法用来核对任何东西
        assert item.name in text
    assert "Get-FileHash" in text
    assert "SHA256" in text


def test_the_notes_stop_claiming_unsigned_when_the_build_is_signed(released: Path):
    """"本程序未做代码签名"在签名构建里是假话，而它出现在信任成本最高的那一屏上
    （``build.render_readme`` 里同一件事踩过一次）。
    """
    assets = release_notes.collect(released)
    unsigned = release_notes.render_assets(assets, signed=False)
    signed = release_notes.render_assets(assets, signed=True)
    assert "未做代码签名" in unsigned
    assert "未做代码签名" not in signed and "数字签名" in signed
    assert "Get-FileHash" in signed  # 签名之后校验值仍然要给


def test_whether_the_build_is_signed_comes_from_the_same_place_as_the_readme(
    released: Path, monkeypatch
):
    monkeypatch.setenv("OMNISIGHT_SIGN_THUMBPRINT", "AB12")
    assert "未做代码签名" not in release_notes.render_assets(release_notes.collect(released))
    monkeypatch.delenv("OMNISIGHT_SIGN_THUMBPRINT")
    assert "未做代码签名" in release_notes.render_assets(release_notes.collect(released))


def test_the_body_points_at_the_docs_that_answer_the_next_questions(released: Path):
    text = release_notes.render(
        tag=TAG, commits=_commits("feat: 甲"), assets=release_notes.collect(released),
        repo="owner/name",
    )
    # 链接钉在这个 tag 上：旧版本的说明应当指向它自己那一版文档。
    assert f"https://github.com/owner/name/blob/{TAG}/docs/faq.md" in text
    assert f"https://github.com/owner/name/blob/{TAG}/docs/privacy.md" in text
    assert "无账号、不联网、无遥测" in text


# ── git：取记录的那一步 ─────────────────────────────────────────────────


def test_a_shallow_clone_is_refused_instead_of_producing_an_empty_changelog(monkeypatch):
    """``actions/checkout`` 默认深度 1。那时 ``git log`` 取不到上一个 tag，变更日志
    是空的——而且**不报错**，发出去才看得见。
    """
    monkeypatch.setattr(release_notes, "is_shallow", lambda **_kwargs: True)
    with pytest.raises(SystemExit, match="fetch-depth"):
        release_notes.commits_between("v0.1.0", "v0.2.0")


def test_tags_in_history_reads_the_decorations_in_order(monkeypatch):
    """一个提交上可以有多个 tag（把 alpha 原样转正），它们在同一行装饰里。"""
    decorations = "\n".join(
        [
            "HEAD -> master, tag: v0.2.0, tag: v0.2.0-rc.1, origin/master",
            "",
            "tag: v0.2.0-alpha.1",
            "tag: v0.1.0",
        ]
    )
    monkeypatch.setattr(release_notes, "_git", lambda _args, **_kwargs: (0, decorations, ""))
    assert release_notes.tags_in_history("HEAD") == [
        "v0.2.0",
        "v0.2.0-rc.1",
        "v0.2.0-alpha.1",
        "v0.1.0",
    ]


def test_tags_are_ordered_by_history_not_by_when_they_were_created(monkeypatch):
    """``git tag --sort=-creatordate`` 会被"给旧提交补打一个 tag"骗到，而基线选错一个，
    整份变更日志就跟着错。所以问的是 ``git log``。
    """
    seen: list[list[str]] = []

    def fake(args, **_kwargs):
        seen.append(args)
        return 0, "tag: v0.1.0", ""

    monkeypatch.setattr(release_notes, "_git", fake)
    release_notes.tags_in_history("v0.2.0")
    assert seen[0][0] == "log" and "--decorate-refs=refs/tags" in seen[0]
    assert not any("creatordate" in item for item in seen[0])
    # --simplify-by-decoration 也不行：实测会漏掉根提交上的 tag（见 tags_in_history）。
    assert "--simplify-by-decoration" not in seen[0]


# ── 基线：pre 跟 pre 比，正式版跟正式版比 ──────────────────────────────


HISTORY = ["v0.2.0-rc.1", "v0.2.0-alpha.2", "v0.2.0-alpha.1", "v0.1.0", "v0.1.0-beta.1"]


def test_a_prerelease_compares_against_the_previous_prerelease():
    assert release_notes.baseline_from(HISTORY, prerelease=True) == "v0.2.0-rc.1"


def test_a_stable_release_skips_every_prerelease_in_between():
    """``v0.2.0`` 拿 ``v0.2.0-rc.1`` 当基线的话，说明里只剩 rc 之后那几条提交——而这个
    正式版真正交付的东西全在它前面。一份"看起来什么都没改"的正式版说明比没有更误导人。
    """
    assert release_notes.baseline_from(HISTORY, prerelease=False) == "v0.1.0"


def test_the_kind_of_a_tag_is_judged_by_pep440_not_by_a_dash():
    """``v0.1.0a1`` 是合法的预发布写法，而它**没有连字符**——把判定写成 ``v*-*``
    这样的 glob 丢给 git，正是会在这里出错（而且是静默出错）。
    """
    assert release_notes.is_prerelease_tag("v0.1.0a1")
    assert release_notes.is_prerelease_tag("v1.0.0.dev0")
    assert not release_notes.is_prerelease_tag("v1.0.0")
    assert release_notes.baseline_from(["v0.1.0a1", "v0.0.9"], prerelease=True) == "v0.1.0a1"
    assert release_notes.baseline_from(["v0.1.0a1", "v0.0.9"], prerelease=False) == "v0.0.9"


def test_the_first_stable_release_has_no_baseline_and_lists_everything():
    """只会发生在"第一个正式版"上，而那时"自项目开始以来"正是它要交付的东西。"""
    only_prereleases = ["v0.1.0-alpha.2", "v0.1.0-alpha.1"]
    assert release_notes.baseline_from(only_prereleases, prerelease=False) is None


def test_a_prerelease_without_an_earlier_prerelease_falls_back_to_the_last_tag():
    """退回上一个正式版，而不是列出全部历史：用户此刻装着的就是它。"""
    assert release_notes.baseline_from(["v1.0.0", "v0.9.0"], prerelease=True) == "v1.0.0"


def test_no_tags_at_all_is_a_first_release_for_both_kinds():
    assert release_notes.baseline_from([], prerelease=True) is None
    assert release_notes.baseline_from([], prerelease=False) is None


def test_the_notes_say_which_kind_the_baseline_was():
    """正式版的清单会包含预发布里已经出现过的改动。不说明基线是哪一类的话，跟着预发布
    走的人会以为重复了。
    """
    commits = _commits("feat: 甲")
    against_stable = release_notes.render_changelog(commits, tag="v0.2.0", previous="v0.1.0")
    against_pre = release_notes.render_changelog(
        commits, tag="v0.2.0-rc.2", previous="v0.2.0-rc.1"
    )
    assert "自上一个正式版 v0.1.0 以来" in against_stable
    assert "自上一个预发布 v0.2.0-rc.1 以来" in against_pre


def test_the_first_stable_explains_why_the_list_is_that_long():
    """读者看到 200 条提交时的第一个问题就是这个。"""
    body = release_notes.render_changelog(
        _commits("feat: 甲", "fix: 乙"), tag="v0.1.0", previous=None, nearest="v0.1.0-rc.1"
    )
    assert "首个正式版" in body and "v0.1.0-rc.1" in body
    # 完整历史时不该指向一个 compare 链接（那需要两个端点）。
    assert "首个发布" not in body


def test_git_output_is_decoded_as_utf8_and_not_by_the_locale(monkeypatch):
    """中文标题按 cp936 的首选编码解码会变成乱码，然后被原样抄进发布页面。"""
    seen: dict[str, list[str]] = {}

    def fake_run(command, **_kwargs):
        seen["command"] = command
        return SimpleNamespace(returncode=0, stdout="完成 M6 发布准备".encode(), stderr=b"")

    monkeypatch.setattr(release_notes.subprocess, "run", fake_run)
    assert release_notes.git("log") == "完成 M6 发布准备"
    # 谁的 ~/.gitconfig 里设了 gbk，上一条就白做了——所以显式指定。
    assert "i18n.logOutputEncoding=UTF-8" in seen["command"]


def test_a_failing_git_says_what_it_was_running(monkeypatch):
    monkeypatch.setattr(release_notes, "_git", lambda _args, **_kwargs: (128, "", "fatal: 坏了"))
    with pytest.raises(SystemExit, match="fatal: 坏了"):
        release_notes.git("log", "nope..HEAD")


def test_the_repository_is_read_from_the_remote_when_actions_did_not_say(monkeypatch):
    monkeypatch.setattr(
        release_notes, "git_quiet", lambda *_args, **_kwargs: "git@github.com:owner/name.git"
    )
    assert release_notes.repository({}) == "owner/name"
    assert release_notes.repository({"GITHUB_REPOSITORY": "actions/said"}) == "actions/said"
    monkeypatch.setattr(release_notes, "git_quiet", lambda *_args, **_kwargs: "https://elsewhere/x")
    assert release_notes.repository({}) is None  # 猜一个地址比不给链接更坏


@pytest.mark.skipif(shutil.which("git") is None, reason="没有 git 可用")
def test_against_a_real_repository(tmp_path: Path):
    """假的 ``_git`` 认不出写错的参数——装饰的解析、范围端点、``--no-merges``、以及
    "同类基线"在真实历史上的结果，都只有真跑一次 git 才能验。

    造出来的历史（旧 → 新）：

        v0.1.0-alpha.1 → v0.1.0 → v0.2.0-alpha.1 → v0.2.0-alpha.2 → v0.2.0
    """
    repo = tmp_path / "repo"
    repo.mkdir()

    def run(*args: str) -> None:
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)

    def commit(message: str, tag: str) -> None:
        run("commit", "--allow-empty", "-q", "-m", message)
        run("tag", tag)

    run("init", "-q", "-b", "main")
    run("config", "user.email", "t@example.com")
    run("config", "user.name", "T")
    run("config", "commit.gpgsign", "false")
    commit("feat: 第一件事", "v0.1.0-alpha.1")
    commit("fix: 第二件事", "v0.1.0")
    commit("docs: 第三件事", "v0.2.0-alpha.1")
    commit("feat: 第四件事", "v0.2.0-alpha.2")
    commit("perf: 第五件事", "v0.2.0")

    assert release_notes.rev_exists("v0.2.0", cwd=repo)
    assert not release_notes.rev_exists("v9.9.9", cwd=repo)
    assert not release_notes.is_shallow(cwd=repo)
    assert release_notes.tags_in_history("v0.2.0", cwd=repo) == [
        "v0.2.0",
        "v0.2.0-alpha.2",
        "v0.2.0-alpha.1",
        "v0.1.0",
        "v0.1.0-alpha.1",
    ]

    def notes_for(tag: str) -> tuple[str | None, list[str]]:
        """把 main() 里那三行照抄一遍：排掉自己 → 选同类基线 → 取范围。"""
        history = [item for item in release_notes.tags_in_history(tag, cwd=repo) if item != tag]
        baseline = release_notes.baseline_from(
            history, prerelease=release_notes.is_prerelease_tag(tag)
        )
        commits = release_notes.commits_between(baseline, tag, cwd=repo)
        return baseline, [item.summary for item in commits]

    # 正式版跨过中间那两个预发布，回到上一个正式版：三条提交全在里面。
    assert notes_for("v0.2.0") == ("v0.1.0", ["第五件事", "第四件事", "第三件事"])
    # 预发布只跟上一个预发布比：一条。
    assert notes_for("v0.2.0-alpha.2") == ("v0.2.0-alpha.1", ["第四件事"])
    # 第一个正式版之前只有预发布 → 没有基线，列出全部历史。
    assert notes_for("v0.1.0") == (None, ["第二件事", "第一件事"])
    # 第一个预发布之前什么都没有。
    assert notes_for("v0.1.0-alpha.1") == (None, ["第一件事"])

# ── 流水线本身（.github/workflows/release.yml）────────────────────────


def test_there_is_exactly_one_workflow_and_it_only_releases():
    """**只有一条流水线，而它只做发布该做的事。**

    这件事反复过两轮：10 文档 §11.1 为省额度移除了常驻 CI；15 文档 §9 因为"产物提交进
    版本库"把它加回来；现在又去掉了，并且连发布流水线里的测试与静态检查一起去掉。理由
    是那些检查在本地跑得到，而它们在 runner 上的失败模式——十几分钟后红在一条本地早就
    跑过的检查上——比它们挡住的东西更常见。

    **代价要写明白**：现在没有任何自动化在每次推送时验证任何东西。"改了 frontend/src
    却忘了 pnpm build"这一类只能靠本地 `tools/check_bundle.py --check`。唯一的缓解是
    发布物里的前端由 `build.py --release` 现场用 Vite 重新构建（见下一条），因此**发出去
    的 EXE 不会带过期前端**——过期只会留在版本库里。

    这条用例的作用是让"又悄悄加回一条流水线"和"又悄悄塞进一道 pytest"都得先改它。
    """
    workflows = sorted(path.name for path in (ROOT / ".github" / "workflows").glob("*.yml"))
    assert workflows == ["release.yml"], workflows
    text = _workflow()
    for absent in (
        "ruff check .",
        "python -m pytest",
        "check_frontend.py",
        "check_types.py",
        "check_bundle.py",
        "pull_request",
    ):
        assert absent not in text, f"发布流水线里不该有 {absent}"


def test_the_only_check_left_is_a_distribution_obligation():
    """许可快照那一道留着，因为它不是测试。

    `tools/licenses.py` 读的是提交进版本库的快照（`frontend/npm-licenses.json`），不读
    node_modules——发布流水线上重新生成 THIRD_PARTY_NOTICES.md 用的就是那份快照。快照
    过期意味着**发出去的许可清单少列或错列依赖**，而那是许可证要求的东西，不是"测试没
    过"。它只比对两个文件，不到一秒，因此没有"省时间"这个动机去掉它。
    """
    assert "tools/npm_licenses.py --check" in _workflow()


def test_the_release_pipeline_installs_node():
    """产物必须由**当前源码**编出来。装了 Node，tools/build.py 才会重新构建而不是
    用版本库里那份提交的产物（那条回退是给 pip 路径留的，发布不该走它）。
    """
    text = _workflow()
    assert "pnpm/action-setup" in text
    assert "pnpm install --frozen-lockfile" in text


def test_it_triggers_on_version_tags_only():
    text = _workflow()
    assert '"v*"' in text
    assert "pull_request" not in text
    assert "branches" not in text


def test_the_checkout_is_deep_enough_for_the_changelog():
    """脚本挡了浅克隆一层，这里钉住另一层——两层都没有的话，第一次发版会得到一份
    空的变更日志，而流水线全绿。
    """
    assert "fetch-depth: 0" in _workflow()


def test_the_pipeline_does_the_three_things_only_it_can_do():
    """流水线里剩下的都是**本地做不了或不该由本地做**的事，这条钉住它们还在。

    * `--check-only`：核对 tag 与 `__version__`。放在最前面——"发布页写 0.2.0、EXE 属性页
      写 0.1.0-alpha.1"这种产物一旦发出去，用户唯一合理的解释是"文件被人换过"。
    * `build.py --release`：产物必须由 runner 构建。本地构建的不是同一批字节，而校验值
      是用户确认拿到的确实是这份产物的唯一手段。
    * `npm_licenses.py --check`：分发义务，见上一条用例。

    **冒烟测试不在这里，也不在别处**：它是唯一碰过"真正发出去的那份字节"的东西，去掉
    之后没有任何自动化验证过产物能不能启动——它是 10 文档 §11.5 第 5 步的人工步骤
    （对**下载到的** EXE 跑一次）。GPL 门禁不受影响：`build.py --release` 自己就会因
    GPL 系依赖失败（`_regenerate_licenses`）。
    """
    text = _workflow()
    for gate in ("--check-only", "tools/build.py --release", "npm_licenses.py --check"):
        assert gate in text, f"{gate} 从流水线里消失了"


def test_the_version_gate_runs_before_anything_is_built():
    """构建完再发现 tag 与版本号对不上，等于白跑十几分钟。"""
    text = _workflow()
    assert text.index("--check-only") < text.index("tools/build.py --release")


def test_the_token_is_narrowed_to_what_a_release_needs():
    assert "contents: write" in _workflow()


def test_the_tag_reaches_the_scripts_through_the_environment():
    """tag 名是外部输入。``${{ }}`` 内联展开会把它直接拼进 shell 脚本文本里。"""
    text = _workflow()
    assert "TAG: ${{ github.ref_name }}" in text
    assert "${{ github.ref_name }}" not in text.replace("TAG: ${{ github.ref_name }}", "")


def test_the_publish_step_uploads_exactly_what_the_tool_listed():
    """产物名字只有 tools/build.py 一处真源。在 YAML 里再抄一遍，改名的那天
    Release 会静默少挂一件——而"少一件"看起来和"这次就发了一件"一模一样。
    """
    publish = _workflow().split("- name: 建 Release", 1)[1]
    assert "steps.notes.outputs.assets" in publish
    assert build._executable_name() not in publish
    assert "--verify-tag" in publish  # 否则 gh 会顺手从默认分支建一个 tag


def test_the_prerelease_flag_comes_from_the_tool_not_from_a_yaml_condition():
    publish = _workflow().split("- name: 建 Release", 1)[1]
    assert "steps.notes.outputs.prerelease" in publish
    # 值直接来自出参，而且**每次都显式传**（``--prerelease=true`` / ``=false``）：在 YAML
    # 里写个 contains(ref_name, '-') 就是第二处判定；而重跑发布时漏传这一项，会把
    # Release 上一次的状态原样留着。
    assert "--prerelease=$($env:PRERELEASE)" in publish
    assert "contains(" not in publish
