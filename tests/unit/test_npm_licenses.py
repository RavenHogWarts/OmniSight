"""随产物分发的 npm 包必须进许可清单（15 文档 §3.5）。

`static/dist` 里打进了 react / react-dom / lucide-react 的代码。MIT 与 ISC 都要求
副本保留版权与许可声明，而产物随 wheel 与 EXE 分发——**这是分发义务，不是可选项**。

难点在于执行时机：清单在发布流水线上生成，那里只 `pip install`，没有 node_modules。
所以采集结果是一份提交进版本库的快照（`frontend/npm-licenses.json`），下面这几条
分别盯住"快照本身没问题""快照进了清单""快照没过期"三件事。只有最后一条需要 Node。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import licenses  # noqa: E402
import npm_licenses  # noqa: E402


@pytest.fixture(scope="module")
def snapshot() -> list[dict[str, str]]:
    packages = npm_licenses.load()
    assert packages, "快照是空的——跑 `python tools/npm_licenses.py`"
    return packages


def test_the_snapshot_covers_every_runtime_dependency(snapshot):
    """`package.json` 的每个 `dependencies` 都要在快照里。

    只查直接依赖：传递依赖由采集器算闭包，而"闭包算对了"由下面那条漂移检查保证。
    """
    names = {pkg["name"] for pkg in snapshot}
    missing = sorted(set(npm_licenses.direct_dependencies()) - names)
    assert not missing, f"这些运行时依赖不在许可快照里：{missing}"


def test_dev_dependencies_stay_out_of_the_snapshot(snapshot):
    """开发期依赖不进产物，因此列进清单等于声称分发了没分发的东西。

    与 `tools/licenses.py` 对 requirements-dev.txt 的处理同一条原则。
    """
    names = {pkg["name"] for pkg in snapshot}
    for tool in ("vite", "typescript", "lucide-static", "playwright-core"):
        assert tool not in names, f"{tool} 是开发期依赖，不该进随产物分发的清单"


def test_every_package_has_a_license_identifier_and_body(snapshot):
    """标识与正文都要有。缺正文时 MIT/ISC 的"保留声明"义务无从履行。"""
    for pkg in snapshot:
        assert pkg["license"], f"{pkg['name']} 没有许可标识"
        assert pkg["license_text"], f"{pkg['name']} 没有许可正文"
        assert pkg["version"], f"{pkg['name']} 没有版本"


def test_no_strong_copyleft_in_the_frontend(snapshot):
    """红线与 Python 侧同一条：强著佐权与单文件静态分发不相容。"""
    assert not npm_licenses.forbidden(snapshot)


def test_the_snapshot_reaches_both_manifests(snapshot):
    """采集了但没进清单等于没采集。"""
    notices = licenses.render_notices([])
    texts = licenses.render_licenses([])
    for pkg in snapshot:
        assert pkg["name"] in notices, f"{pkg['name']} 不在 THIRD_PARTY_NOTICES.md 里"
        assert pkg["license_text"] in texts, f"{pkg['name']} 的正文不在 LICENSES 里"


def test_the_notice_explains_how_they_get_into_the_artifact(snapshot):
    """清单要说清"打进 dist"这件事——npm 包在产物里没有可辨认的包边界，
    读者只能靠这份说明知道里面有什么。
    """
    notices = licenses.render_notices([])
    assert "static/dist" in notices
    assert "dependencies" in notices


def test_the_snapshot_is_not_stale():
    """快照与装着的 node_modules 一致。**没装就跳过**（同 test_frontend_js.py）。"""
    if not (ROOT / "node_modules" / "react" / "package.json").is_file():
        pytest.skip("没有 node_modules（跑 `pnpm install`）")
    assert npm_licenses.main(["--check"]) == 0, "快照已过期，跑 `python tools/npm_licenses.py`"


def test_transitive_dependencies_are_resolved_through_the_pnpm_store():
    """pnpm 的布局不是扁平的：传递依赖在 .pnpm 下。

    实测这一条的理由：写死 `node_modules/<name>` 的版本在 react-dom 的 `scheduler`
    上当场就炸，而 scheduler 是 MIT，漏了它清单就是不实的。
    """
    if not (ROOT / "node_modules" / "react-dom" / "package.json").is_file():
        pytest.skip("没有 node_modules")
    names = {pkg["name"] for pkg in npm_licenses.collect()}
    assert "scheduler" in names, "传递依赖没被采集到——pnpm 的 .pnpm 布局没解析对"
