"""表驱动的适配器解码测试（11 文档 §8.1）。

**这一层的存在本身就是一条架构约束的执行机制。** 它断言的是"解码是纯函数、副作用
留在事件泵里"——只要这条成立，macOS / Linux 的解码逻辑就能在 Windows 开发机与
ubuntu CI 上被完整测试，无需真实设备、无需运行在该平台上。反过来，如果哪个适配器
把解码和系统调用揉在一起，这层测试立刻失效，因此**"解码必须可离线测试"是适配器的
验收标准之一**，不是建议。

所以本文件里没有一处 ``pytest.mark.windows_only``，也没有一次 ``sys.platform`` 判断。

原生码在 fixture 里写成 ``"0x2A"`` 这样的十六进制字符串：JSON 没有十六进制字面量，
而扫描码只有以十六进制形式才能与微软文档逐行核对——``42`` 看不出是左 Shift。
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from pathlib import Path

import pytest

from omnisight.adapters.windows import keymap_native as windows_native

NATIVE_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "native_events"

#: 一次解码的结果：``(key_id, is_down)``。``key_id`` 为 ``None`` 表示这份报文
#: 不构成一次按键（前缀段），或该键不在映射表内。
Decoded = tuple[str | None, bool]
Decoder = Callable[[Iterable[dict]], list[Decoded]]


def _as_int(value: int | str) -> int:
    """接受 ``26`` 与 ``"0x1A"`` 两种写法。"""
    return value if isinstance(value, int) else int(value, 16)


def _decode_windows(events: Iterable[dict]) -> list[Decoded]:
    decoded: list[Decoded] = []
    for event in events:
        key_id, _usage, is_down = windows_native.resolve(
            _as_int(event["vk"]), _as_int(event["scan"]), _as_int(event["flags"])
        )
        decoded.append((key_id, is_down))
    return decoded


#: M8/M9 在这里各加一行，自己的 fixture 就自动被全部用例覆盖。
DECODERS: dict[str, Decoder] = {"windows": _decode_windows}


def decoder_for(platform_id: str) -> Decoder:
    decoder = DECODERS.get(platform_id)
    if decoder is None:  # pragma: no cover - 只在 fixture 写错平台名时触发
        pytest.fail(f"没有 {platform_id} 的解码器，fixture 无法被验证")
    return decoder


def _fixtures() -> list[Path]:
    files = sorted(NATIVE_FIXTURES.glob("*.json"))
    assert files, "fixture 目录空了——这层测试会静默变成 0 个用例"
    return files


@pytest.mark.parametrize("fixture", _fixtures(), ids=lambda path: path.stem)
def test_native_sequence_produces_expected_key_ids(fixture: Path):
    """同样的字节进去，同样的 key_id 出来，与宿主操作系统无关。"""
    case = json.loads(fixture.read_text(encoding="utf-8"))
    decoder = decoder_for(case["platform"])
    expected = [(key_id, is_down) for key_id, is_down in case["expected"]]
    assert decoder(case["events"]) == expected, case["description"]


def test_every_fixture_declares_a_platform_and_a_reason():
    """fixture 是给人读的：没有说明的录制数据在半年后没人知道它在防什么。"""
    for fixture in _fixtures():
        case = json.loads(fixture.read_text(encoding="utf-8"))
        assert case["platform"] in DECODERS
        assert case.get("description"), f"{fixture.name} 缺少 description"
        assert len(case["events"]) == len(case["expected"]), f"{fixture.name} 长度不匹配"
