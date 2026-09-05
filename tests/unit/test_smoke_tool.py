"""冒烟工具自己的几条不变量（``tools/smoke.py``）。

它跑的是**打包产物**，因此它的失败最容易变成一句猜不出下一步的话。这四条钉住的正是
那几处："换端口"这个机制要真的有效、"已有实例在跑"要说得出该做什么、`--port` 不能被
当成产物路径、以及**不许吃掉别人的 config.json**。

不启动任何产物：这里验的是工具的判断与文案，产物那一半由 `python tools/smoke.py` 自己跑。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import smoke  # noqa: E402
from omnisight.core.config import ServerConfig  # noqa: E402
from omnisight.core.lifecycle import EXIT_ALREADY_RUNNING  # noqa: E402


class _Exited:
    """``subprocess.Popen`` 的替身：已经以某个退出码结束了。"""

    def __init__(self, code: int) -> None:
        self._code = code

    def poll(self) -> int:
        return self._code


def test_the_smoke_port_is_not_the_one_the_users_own_instance_listens_on():
    """冒烟不许和用户自己那份抢端口。

    端口撞了是**硬失败**（core/lifecycle.py 绑定失败那一段没有回退），而默认端口上多半
    正跑着用户装的那一份。这条在"有人把默认端口改成 6101"的那一天会红——那时两个数字
    重合，而症状会是一次莫名的启动失败。
    """
    assert ServerConfig().port != smoke.SMOKE_PORT


def test_the_exit_code_for_already_running_is_read_from_the_same_number_the_app_returns():
    """工具里那份 2 与 ``lifecycle`` 里的必须是同一个数。

    它刻意是抄的一份（smoke 不 import 被测的包，否则"源码好而包坏"就漏出去了），
    因此需要一条测试替代 import 关系。
    """
    assert smoke.EXIT_ALREADY_RUNNING == EXIT_ALREADY_RUNNING


def test_already_running_says_what_to_do_instead_of_printing_a_number(tmp_path: Path):
    """退出码 2 是最常见的一种失败，而它的字面意思最难猜。

    也不该再去找 STARTUP_ERROR.txt：那不是一次启动失败，是它按设计让位给了已经在跑的
    那一个，因此那个文件永远不存在——提"未找到 STARTUP_ERROR.txt"只是把人往错的方向带。
    """
    try:
        smoke._wait_for_runtime(tmp_path / "data", _Exited(EXIT_ALREADY_RUNNING))
    except RuntimeError as exc:
        message = str(exc)
    else:  # pragma: no cover - 上面必抛
        raise AssertionError("已有实例在跑时应当立刻报错")
    assert "已有一个实例在跑" in message
    assert "互斥体" in message, "要说清换端口绕不开它"
    assert "STARTUP_ERROR" not in message


def test_a_port_flag_is_not_mistaken_for_the_executable_path(monkeypatch):
    """`--port 6102` 里那个数字曾经会被当成产物路径。

    原来的解析是"不以 -- 开头的就是位置参数"，于是 `--port 6102` 会让工具去找一个名叫
    `6102` 的可执行文件——报错是"找不到产物：6102"，而那句话不会让任何人想到解析。
    """
    seen: dict[str, object] = {}
    monkeypatch.setattr(
        smoke, "run", lambda target, *, keep, port: seen.update(target=target, keep=keep, port=port)
    )
    smoke.main(["--port", "6102", "--keep"])
    assert seen["port"] == 6102
    assert seen["keep"] is True
    assert Path(seen["target"]).name == "OmniSight.exe"
    smoke.main(["--port=6103", "dist/Other.exe"])
    assert seen["port"] == 6103
    assert Path(seen["target"]).name == "Other.exe"


def test_an_existing_config_is_handed_back_so_it_can_be_restored(tmp_path: Path):
    """产物同级那份 config.json 可能不是我们的（有人手工跑过 `--keep`）。

    而 ``_cleanup`` 会无条件删掉它——因此写之前必须把原文交回调用方，由它在最后放回去。
    少了这一步，跑一次冒烟就吃掉别人的配置，且没有任何提示。
    """
    keeper = tmp_path / "config.json"
    keeper.write_text('{"server": {"port": 6100}}', encoding="utf-8")
    previous = smoke._write_port_config(tmp_path, smoke.SMOKE_PORT)
    assert previous == b'{"server": {"port": 6100}}'
    assert json.loads(keeper.read_text(encoding="utf-8"))["server"]["port"] == smoke.SMOKE_PORT


def test_the_written_config_is_something_the_app_will_accept(tmp_path: Path):
    """写出来的必须是一份**能过校验**的配置：坏配置会让产物在启动时就退出，而那个失败
    看起来和"打包坏了"一模一样。"""
    from omnisight.core import config as config_module

    assert smoke._write_port_config(tmp_path, 6102) is None
    loaded, _ = config_module.load(tmp_path / "config.json")
    assert loaded.server.port == 6102
    assert loaded.server.host in config_module.LOOPBACK_HOSTS
