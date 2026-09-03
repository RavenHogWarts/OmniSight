"""许可清单生成（10 文档 §1.2）。

重点测**门禁规则本身**：GPL/AGPL 拦下、LGPL 放行但挂义务说明——这条界线是
有意的决策（托盘与键盘兜底都是 LGPL 且无可替代），不是正则的巧合。
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import licenses  # noqa: E402


@pytest.fixture
def installed():
    """真实安装的包（开发环境必有 flask / blinker），用来验证"能真的读到正文"。"""
    from importlib import metadata

    return metadata.distribution


class FakeEntry:
    """``dist.files`` 的元素：字符串是相对 site-packages 的路径，``locate()`` 给绝对路径。"""

    def __init__(self, path: str, real: Path) -> None:
        self.path = path
        self.real = real

    def __str__(self) -> str:
        return self.path

    def locate(self) -> Path:
        return self.real


class FakeDist:
    """够用的 ``Distribution`` 替身：只有 ``files`` 与 ``metadata.get_all``。"""

    def __init__(self, root: Path, names: list[str], declared: list[str] | None = None) -> None:
        self.files = []
        for name in names:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                target.write_text(f"content of {name}\n", encoding="utf-8")
            self.files.append(FakeEntry(name, target))
        self.metadata = SimpleNamespace(get_all=lambda key: declared or [])


@pytest.mark.parametrize(
    ("name", "forbidden", "lgpl"),
    [
        ("GPLv3", True, False),
        ("GPL v3", True, False),
        ("GNU General Public License v3 (GPLv3)", True, False),
        ("AGPLv3", True, False),
        ("AGPL-3.0-only", True, False),
        ("LGPLv3", False, True),
        ("LGPL v2.1", False, True),
        ("LGPL-3.0-or-later", False, True),
        ("MIT", False, False),
        ("MIT-CMU", False, False),
        ("BSD-3-Clause", False, False),
        ("Apache-2.0", False, False),
        ("PSF-2.0", False, False),
        ("Mozilla Public License 2.0 (MPL 2.0)", False, False),
        ("未声明", False, False),
    ],
)
def test_the_gate_separates_strong_copyleft_from_lgpl(name, forbidden, lgpl):
    """``\\bGPL\\b`` 对 "GPLv3" 不命中（v 是单词字符），门禁必须真的拦得住它
    要拦的东西——这条测试就是把那次踩坑钉死。"""
    assert bool(licenses.FORBIDDEN_LICENSE_PATTERN.search(name)) is forbidden
    assert bool(licenses.LGPL_PATTERN.search(name)) is lgpl


def test_requirement_parsing_splits_markers_and_names():
    assert licenses._split_marker("pywin32==311 ; sys_platform == \"win32\"") == (
        "pywin32",
        'sys_platform == "win32"',
    )
    assert licenses._split_marker("flask==3.1.1") == ("flask", None)
    assert licenses._split_marker("pynput>=1.7,<2 ; python_version >= '3.8'")[0] == "pynput"


def test_requirement_names_honor_platform_markers(tmp_path: Path, monkeypatch):
    """环境标记按当前解释器求值：本机装不上的包不该出现在清单里（声称分发了
    没分发的东西，与漏列同样是错的）。"""
    requirement = tmp_path / "requirements.txt"
    other = tmp_path / "requirements-optional.txt"
    this_platform = sys.platform
    requirement.write_text(
        "# 注释行\n"
        "flask==3.1.1\n"
        f"not-for-here==1.0 ; sys_platform != \"{this_platform}\"\n"
        f"for-here==1.0 ; sys_platform == \"{this_platform}\"\n"
        "-r 不支持的选项行也跳过\n",
        encoding="utf-8",
    )
    other.write_text("", encoding="utf-8")
    monkeypatch.setattr(licenses, "ROOT", tmp_path)
    names = licenses._requirement_names((requirement.name, other.name))
    assert names == {"flask", "for-here"}


def test_closure_walks_transitive_dependencies():
    """闭包至少要走到第二层：flask → click/blinker/itsdangerous/…（开发环境必装）。"""
    closure = licenses._closure({"flask"})
    assert "flask" in closure
    assert "click" in closure or "blinker" in closure
    assert "omnisight" not in closure  # 自身不属于第三方
    assert "pytest" not in closure  # extra/dev 组不随产物分发


def test_notices_render_carries_the_lgpl_obligation_note():
    packages = [
        licenses.Package("pystray", "0.19.5", "LGPLv3", "https://example.org", (("COPYING", "x"),)),
        licenses.Package("flask", "3.1.1", "BSD-3-Clause", "https://example.org", (("L", "x"),)),
    ]
    text = licenses.render_notices(packages)
    assert "| pystray | 0.19.5 | LGPLv3 |" in text
    assert "LGPL" in text and "pystray" in text.split("共 2 个包")[1]
    assert "重新构建" in text  # 义务的行使方式要写明白


def test_notices_render_without_lgpl_packages_has_no_note():
    packages = [licenses.Package("flask", "3.1.1", "BSD-3-Clause", "", (("L", "x"),))]
    assert "LGPL" not in licenses.render_notices(packages).split("共 1 个包")[1]


def test_license_text_of_an_installed_package_is_the_real_license(installed):
    """**真的正文，不是兜底文案。**

    M6 之前这里只断言"非空"，而实现里的兜底文案恰好也非空——于是"22 个包全都取不到
    正文"这个 bug 在测试里和正常情况长得一模一样。根因是 ``dist.read_text()`` 解析的
    是 dist-info 目录内的路径，而 ``dist.files`` 给的是相对 site-packages 的路径，
    喂进去永远 ``None``。现在断言许可条文本身的措辞。
    """
    files = licenses._license_files(installed("flask"))
    assert files, "flask 的 wheel 一定随附 LICENSE.txt"
    path, text = files[0]
    assert path.endswith("LICENSE.txt")
    assert "Redistribution and use in source and binary forms" in text  # BSD-3-Clause 正文
    assert "Copyright" in text


def test_license_files_are_found_in_both_wheel_layouts(installed):
    """新式 wheel 放 ``dist-info/licenses/``，老式直接放 ``dist-info/`` 根。
    只认一处的实现会漏掉另一半，而漏掉的表现是"这个包没有许可正文"。"""
    modern = licenses._license_files(installed("flask"))[0][0]
    legacy = licenses._license_files(installed("blinker"))[0][0]
    assert "/licenses/" in modern
    assert "/licenses/" not in legacy and legacy.endswith("LICENSE.txt")


def test_generate_writes_both_files_and_reports_forbidden(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(licenses, "ROOT", tmp_path)
    monkeypatch.setattr(
        licenses,
        "collect",
        lambda: [
            licenses.Package("a", "1", "MIT", "", (("LICENSE", "text"),)),
            licenses.Package("bad", "1", "GPLv3", "", (("LICENSE", "text"),)),
        ],
    )
    packages, forbidden = licenses.generate(
        notices=tmp_path / "NOTICES.md", licenses=tmp_path / "LICENSES.txt"
    )
    assert len(packages) == 2
    assert [pkg.name for pkg in forbidden] == ["bad"]
    assert "GPLv3" in (tmp_path / "NOTICES.md").read_text(encoding="utf-8")
    assert "bad 1" in (tmp_path / "LICENSES.txt").read_text(encoding="utf-8")


def test_the_licenses_file_uses_crlf(tmp_path: Path, monkeypatch):
    """它随 zip 分发，读它的人用记事本；顺带让 Windows 与 Linux 构建产出同样的字节。"""
    monkeypatch.setattr(licenses, "ROOT", tmp_path)
    monkeypatch.setattr(
        licenses, "collect", lambda: [licenses.Package("a", "1", "MIT", "", (("L", "t"),))]
    )
    licenses.generate(notices=tmp_path / "N.md", licenses=tmp_path / "L.txt")
    raw = (tmp_path / "L.txt").read_bytes()
    assert b"\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b"")


# ── 许可文件的挑选（M6 修正的那个 bug 的周边）────────────────────────────


def test_source_code_is_never_mistaken_for_a_license(tmp_path: Path):
    """``^licen[cs]e`` 会命中 ``licenses.py``——把一段 Python 源码印进许可文件。"""
    dist = FakeDist(tmp_path, ["pkg/licenses.py", "pkg/license.txt"])
    assert [path for path, _ in licenses._license_files(dist)] == ["pkg/license.txt"]


def test_license_body_comes_before_authors_and_notice(tmp_path: Path):
    dist = FakeDist(tmp_path, ["d/AUTHORS.md", "d/NOTICE", "d/LICENSE"])
    assert [path for path, _ in licenses._license_files(dist)] == [
        "d/LICENSE",
        "d/NOTICE",
        "d/AUTHORS.md",
    ]


def test_identical_copies_are_printed_once(tmp_path: Path):
    """pywin32 在四个包目录里各放一份一模一样的 license.txt，照抄四遍只会让读者
    以为自己看错了。"""
    dist = FakeDist(tmp_path, ["a/license.txt", "b/license.txt", "c/LICENSE"])
    (tmp_path / "a" / "license.txt").write_text("same text\n", encoding="utf-8")
    (tmp_path / "b" / "license.txt").write_text("same text\n", encoding="utf-8")
    (tmp_path / "c" / "LICENSE").write_text("different\n", encoding="utf-8")
    found = licenses._license_files(dist)
    assert [path for path, _ in found] == ["a/license.txt", "c/LICENSE"]


def test_a_file_named_by_metadata_is_picked_up_even_with_an_odd_name(tmp_path: Path):
    dist = FakeDist(tmp_path, ["d/EULA.txt"], declared=["EULA.txt"])
    assert [path for path, _ in licenses._license_files(dist)] == ["d/EULA.txt"]


def test_empty_license_files_are_skipped(tmp_path: Path):
    dist = FakeDist(tmp_path, ["d/LICENSE"])
    (tmp_path / "d" / "LICENSE").write_text("   \n", encoding="utf-8")
    assert licenses._license_files(dist) == []


# ── 项目地址与 LGPL 组件 ─────────────────────────────────────────────────


def test_homepage_accepts_every_spelling_of_the_source_label():
    """``Source Code`` / ``Sources`` 不等于 ``source``，逐字比对会让 cffi、clr_loader
    这类包在清单里显示"—"——空白会被读成"这个包查不到出处"。"""
    for label in ("Source Code", "Sources", "Repository", "GitHub"):
        dist = SimpleNamespace(
            metadata=SimpleNamespace(
                get=lambda _key: None,
                get_all=lambda _key, label=label: [f"{label}, https://example.org/x"],
            )
        )
        assert licenses._homepage(dist) == "https://example.org/x"


def test_homepage_prefers_the_project_page_over_docs_and_downloads():
    dist = SimpleNamespace(
        metadata=SimpleNamespace(
            get=lambda _key: None,
            get_all=lambda _key: [
                "Documentation, https://docs.example.org",
                "Download, https://example.org/releases",
                "Homepage, https://example.org",
            ],
        )
    )
    assert licenses._homepage(dist) == "https://example.org"


def test_bundled_lgpl_is_reported_even_when_metadata_says_otherwise():
    """pywin32 的元数据只写 PSF，wheel 里却捆着 LGPL-2.1 的 adodbapi。按标识判的话，
    这条义务在清单上完全看不见。"""
    pkg = licenses.Package(
        "pywin32",
        "311",
        "PSF",
        "",
        (("adodbapi/license.txt", "GNU LESSER GENERAL PUBLIC LICENSE\n\nVersion 2.1"),),
    )
    assert pkg.lgpl is False
    assert pkg.lgpl_components == ("adodbapi/license.txt",)
    text = licenses.render_notices([pkg])
    assert "adodbapi/license.txt" in text and "PSF" in text


def test_a_passing_mention_of_lgpl_is_not_an_lgpl_component():
    """Pillow 的 LICENSE 转载了 XZ Utils 的文档，里面逐条列出各许可文件名。
    宽松匹配会让清单多出一条**不实的** LGPL 义务声明（实测踩到）。"""
    mention = "Pillow license\n" + "x" * 2000 + (
        "\n    The following license texts are included:\n"
        "      - COPYING.LGPLv2.1: GNU Lesser General Public License version 2.1\n"
    )
    pkg = licenses.Package("pillow", "11.3.0", "MIT-CMU", "", (("LICENSE", mention),))
    assert pkg.lgpl_components == ()


def test_declared_lgpl_packages_are_not_double_counted():
    pkg = licenses.Package(
        "pystray", "0.19.5", "LGPLv3", "", (("COPYING", "GNU LESSER GENERAL PUBLIC LICENSE"),)
    )
    assert pkg.lgpl is True and pkg.lgpl_components == ()


# ── 许可正文文件的排版 ───────────────────────────────────────────────────


@pytest.fixture
def three_packages() -> list[licenses.Package]:
    return [
        licenses.Package("alpha", "1.0", "MIT", "https://a.example", (("A/LICENSE", "MIT 正文"),)),
        licenses.Package("beta", "2.0", licenses.UNDECLARED, "", (("B/LICENSE", "某许可正文"),)),
        licenses.Package("gamma", "3.0", "BSD-3-Clause", "https://c.example", ()),
    ]


def test_the_title_appears_exactly_once(three_packages):
    """``"标题\\n" "=" * 80`` 会先做字面量拼接再整体重复 80 遍——旧实现的文件开头是
    80 行标题。这条断言就是为了让那种排版事故不可能再悄悄通过。"""
    text = licenses.render_licenses(three_packages)
    assert text.count("第三方许可正文") == 1
    assert text.startswith(licenses.RULE)


def test_the_index_lists_every_package_once(three_packages):
    """索引是这份文件唯一的导航手段（纯文本没有目录跳转）。"""
    text = licenses.render_licenses(three_packages)
    index = text.split("每一节给出")[0]
    for number, pkg in enumerate(three_packages, start=1):
        assert f"{number}. {pkg.name} {pkg.version}" in index
    assert "未声明（见该节正文）" in index  # 未声明时指向正文，不留空


def test_each_package_gets_a_numbered_section_with_uniform_fields(three_packages):
    text = licenses.render_licenses(three_packages)
    body = text.split("每一节给出")[1]
    # 嵌入素材（tools/licenses.py 的 EMBEDDED_ASSETS）也各占一节，字段与包一致——
    # 写成加法而不是写死 4，加第二项素材时这条不该红。
    expected = len(three_packages) + len(licenses.EMBEDDED_ASSETS)
    assert body.count("许可标识：") == expected
    assert body.count("项目地址：") == expected  # 字段齐整，缺地址也占位
    assert "项目地址：（元数据未提供）" in body
    assert "--- A/LICENSE ---\nMIT 正文" in body


def test_embedded_assets_are_declared_in_both_manifests(three_packages):
    """非 Python 素材的义务同样要出现在清单里，而不是只藏在生成文件的注释里。

    lucide 的图标几何被搬进 `templates/_icon_sprite.html`（生成器 `tools/icons.py`），
    因此它随产物分发。`importlib.metadata` 看不见 npm 的东西，所以这一节是手工声明的
    ——这条用例是它唯一的执行机制。
    """
    assert licenses.EMBEDDED_ASSETS, "EMBEDDED_ASSETS 空了？lucide 的图标还在产物里"
    notices = licenses.render_notices(three_packages)
    texts = licenses.render_licenses(three_packages)
    for asset in licenses.EMBEDDED_ASSETS:
        assert asset["name"] in notices
        assert asset["embedded"] in notices  # 说清搬了什么、搬进哪个文件
        assert asset["license_text"] in texts  # 正文逐字进 LICENSES


def _section(text: str, header: str) -> str:
    """取某一节的正文。

    索引里也有 "3. gamma 3.0" 这样的字样，所以按**独占一行**的标题定位，再切到下一条
    分隔线为止。
    """
    after = text.split(f"\n{header}\n")[-1]
    parts = after.split(licenses.RULE)
    return parts[1] if len(parts) > 1 else after


def test_a_package_without_bundled_text_says_so_and_says_where_to_look(three_packages):
    section = _section(licenses.render_licenses(three_packages), "3. gamma 3.0")
    assert "未随附许可正文文件" in section
    assert "项目地址" in section


def test_an_undeclared_license_points_at_the_text_below(three_packages):
    section = _section(licenses.render_licenses(three_packages), "2. beta 2.0")
    assert "以下正文为准" in section
    assert "某许可正文" in section
