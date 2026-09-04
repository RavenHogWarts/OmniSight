"""前端产物的门禁作为测试跑（15 文档 §3.1、§3.2）。

产物（`static/dist`）提交进版本库——`pip install` 路径上没有 Node，wheel 必须自带
打包好的前端。代价是版本库里多了一份**可以过期**的东西：改了 `frontend/src` 却忘了
`pnpm build`，页面加载的仍然是旧代码，而测试全绿、页面正常。这是最难发现的不一致。

`tools/check_bundle.py` 是实现，这里是执行机制。分成"齐全"（纯 Python，永远跑）与
"与源码一致"（要重新构建一次，需要 Node，缺了就跳过）两级——前者拦的是"打了个没有
界面的包"，后者拦的是"产物过期"。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import check_bundle  # noqa: E402


def test_the_bundle_is_present_and_complete():
    problems = check_bundle.exists()
    assert not problems, "前端产物不完整：\n  " + "\n  ".join(problems)


def test_the_manifest_names_exactly_one_entry():
    """入口只能有一个。`web.py:read_bundle` 按 `isEntry` 取第一个——有两个就会
    随字典顺序挑一个，页面加载哪一份取决于构建顺序。
    """
    manifest = json.loads((check_bundle.MANIFEST).read_text(encoding="utf-8"))
    entries = [
        key
        for key, record in manifest.items()
        if isinstance(record, dict) and record.get("isEntry")
    ]
    assert len(entries) == 1, f"清单里有 {len(entries)} 个入口：{entries}"


def test_the_manifest_is_not_inside_a_dot_directory():
    """清单必须在 `dist/` 根。setuptools 的 `**/*` 对点开头的目录不保证展开，
    而 Vite 默认把它写进 `dist/.vite/`——那份 wheel 装出来只有"产物缺失"那张卡。
    """
    relative = check_bundle.MANIFEST.relative_to(check_bundle.DIST)
    assert relative.as_posix() == "manifest.json", relative


def test_the_entry_is_a_module_not_a_classic_script():
    """产物一律 `type="module"`，因此**承担不了需要阻塞执行的活儿**。

    防主题闪白就是那种活儿（06 文档 §3.2）：模块天然 defer，等它跑起来白底已经画完。
    那件事原先由 `static/js/theme.js` 这个普通脚本做，15 文档 §11.3 换成了服务端渲染
    `<html data-theme>`——"产物是模块"这条性质没变，只是不再有第二个脚本受它约束。
    """
    template = (
        ROOT / "src" / "omnisight" / "presentation" / "templates" / "dashboard.html"
    ).read_text(encoding="utf-8")
    assert 'type="module" src="{{ bundle.entry }}"' in template


@pytest.mark.skipif(check_bundle.resolve_command() is None, reason="未装 vite，跳过重新构建")
def test_the_committed_bundle_matches_the_sources():
    """重新构建一次，逐字节比对。这是唯一能真正回答"产物与源码一致吗"的检查。"""
    code, problems = check_bundle.check()
    if code == -1:
        pytest.skip(problems[0])
    assert code == 0 and not problems, "产物与源码不一致：\n  " + "\n  ".join(problems)
