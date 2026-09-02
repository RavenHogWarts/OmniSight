"""工具的输出不该因为控制台编码而失败（10 文档 §11.2）。

**这一组用例来自一次真实的发版失败。** GitHub 的 Windows runner 把子进程的 stdout 接成
管道，Python 于是不走控制台的 Unicode 接口，而是按 locale 挑编码——实测 cp1252。第一次
推 tag 时，`release_notes.py --check-only` **核对通过了**，然后死在打印那句
"tag v0.1.0-alpha.1 与代码里的版本一致"上：`UnicodeEncodeError`，退出码 1，流水线红在
报喜的那一行。

本机的中文控制台（cp936）装得下这些字，所以开发机上永远看不见这件事；英文 Windows 上把
任何一个工具的输出重定向到文件也一样会中。因此两道保证：每个 `tools/` 入口在 `__main__`
里调一次 `use_utf8_output()`，发版流水线另外设 `PYTHONIOENCODING: utf-8`——**两道互不
依赖**，因为"记得在 YAML 里设那个变量"是那种下一个人加一步就会丢的保证。

复现方式（本机可跑）：`PYTHONIOENCODING=cp1252 python tools/release_notes.py --check-only`。
"""

from __future__ import annotations

import io
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from _console import use_utf8_output  # noqa: E402

WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"
GUARD = re.compile(r'if __name__ == "__main__":')


class Recorder:
    """记下 ``reconfigure`` 收到的参数。"""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def reconfigure(self, **kwargs: object) -> None:
        self.calls.append(kwargs)


def test_both_streams_are_switched_to_utf8(monkeypatch):
    out, err = Recorder(), Recorder()
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", err)
    use_utf8_output()
    for stream in (out, err):
        assert stream.calls == [{"encoding": "utf-8", "errors": "replace"}]


def test_a_stream_without_reconfigure_is_left_alone(monkeypatch):
    """pytest 之类会把 ``sys.stdout`` 换成别的对象。"""
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    monkeypatch.setattr(sys, "stderr", object())
    use_utf8_output()  # 不该抛


def test_a_stream_that_refuses_is_not_a_new_failure_point(monkeypatch):
    """这个函数的全部意义是让输出别把进程弄死，它自己更不该成为新的失败点。"""

    class Stubborn:
        def reconfigure(self, **_kwargs: object) -> None:
            raise ValueError("已经 detach 了")

    monkeypatch.setattr(sys, "stdout", Stubborn())
    monkeypatch.setattr(sys, "stderr", Stubborn())
    use_utf8_output()


def _entry_points() -> list[Path]:
    return [
        path
        for path in sorted(TOOLS.glob("*.py"))
        if path.name != "_console.py" and GUARD.search(path.read_text(encoding="utf-8"))
    ]


def test_every_tool_entry_point_hardens_its_output():
    """规则是"是入口就加固"，而不是"看起来会打印中文才加固"。

    后者是个漏的判定：``release_prepare.py`` 的 ``print()`` 里一个中文字都没有（文本由
    ``describe()`` 拼好返回），但它当然会打印中文。写成前者，将来新加的工具也自动在内。
    """
    entries = _entry_points()
    assert len(entries) >= 13, "入口一下少了这么多？先确认不是这条断言过期了"
    missing = [
        path.name
        for path in entries
        if "use_utf8_output()" not in path.read_text(encoding="utf-8")
    ]
    assert not missing, f"这些入口没加固：{missing}"


def test_the_helper_is_imported_inside_the_main_guard():
    """放在模块顶层的话，被测试或别的工具 import 时会顺手改掉调用方的标准输出。"""
    for path in _entry_points():
        text = path.read_text(encoding="utf-8")
        guard = text[GUARD.search(text).start() :]
        assert "from _console import use_utf8_output" in guard, path.name


def test_the_pipeline_sets_the_encoding_too():
    """第二道。与工具里那道互不依赖——YAML 里的环境变量是那种下一个人加一步就会丢的保证，
    而工具里那道管不到 pytest 自己的输出。
    """
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "PYTHONIOENCODING: utf-8" in text
    # 必须在 job 级别（每一步都吃到），不是钉在某一步上。
    job = text.split("runs-on: windows-latest", 1)[1].split("steps:", 1)[0]
    assert "PYTHONIOENCODING" in job


@pytest.mark.parametrize("name", ["release_notes.py", "release_prepare.py", "build.py"])
def test_the_comment_says_why(name: str):
    """三年后看到这行 import 的人，得知道它不是洁癖。"""
    text = (TOOLS / name).read_text(encoding="utf-8")
    assert "cp1252" in text
