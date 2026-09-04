"""前端的 Node 测试从 pytest 里跑一遍（11 文档 §8.4）。

**为什么要有这一层包装**：CI 只跑 `pytest`。前端的纯函数测试如果只能手工执行，
三个月后它们就会静默失效——与"架构约束必须有执行机制"是同一条道理。

Node 不在时**跳过而不是失败**：项目坚持零 Node 工具链（07 文档 §2），Node 只是
"如果有就用"的开发期便利。Windows 上装了 Node 的机器会跑到；CI 镜像里装了也会跑到。

`layouts.json` 每次运行前从 `capture/layouts.py` 重新导出：这让键盘布局的测试
真正是**跨语言契约**——前端吃的是后端此刻的布局数据，而不是某次手工导出的快照。
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_TESTS = ROOT / "tests" / "frontend"


def _write_layout_fixture() -> Path:
    from omnisight.capture import layouts

    payload = {
        family: layout.to_dict(source="test") for family, layout in layouts.FAMILIES.items()
    }
    path = FRONTEND_TESTS / "layouts.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


@pytest.mark.skipif(shutil.which("node") is None, reason="未安装 Node，跳过前端单元测试")
def test_frontend_unit_tests_pass():
    _write_layout_fixture()
    files = sorted(
        path.name for pattern in ("*.test.ts", "*.test.js") for path in FRONTEND_TESTS.glob(pattern)
    )
    assert files, "tests/frontend 下没有测试文件——前端纯函数失去了保护"
    result = subprocess.run(
        [
            shutil.which("node"),
            "--test",
            # 用例是 .ts（15 文档方案 A 之后源码是 TS）。Node 22 能直接执行它们，
            # 因此"零依赖也能测纯函数"这条路保住了——不必为跑几个纯函数引入 vitest。
            "--experimental-strip-types",
            "--no-warnings",
            *[f"tests/frontend/{name}" for name in files],
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    if result.returncode != 0:
        # 把 node 的 TAP 输出原样带出来，否则失败信息只有一个退出码。
        sys.stdout.write(result.stdout)
        sys.stderr.write(result.stderr)
    assert result.returncode == 0, "前端 Node 测试失败（详见上方 TAP 输出）"


def test_layout_fixture_covers_every_implemented_family():
    """导出的 fixture 必须覆盖全部已实现布局族，否则渲染器测试会漏掉一族。"""
    from omnisight.capture import layouts

    payload = json.loads(_write_layout_fixture().read_text(encoding="utf-8"))
    assert set(payload) == set(layouts.IMPLEMENTED_FAMILIES)
    for family, layout in payload.items():
        assert layout["rows"], family
        assert layout["unit_hint"]["rows"] == len(layout["rows"])
