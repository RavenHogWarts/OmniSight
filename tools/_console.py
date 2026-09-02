"""让工具的输出不因为控制台编码而失败（10 文档 §11.2）。

**这不是洁癖，是一次真实的发版失败。** GitHub 的 Windows runner 把子进程的 stdout 接成
管道，Python 于是不走控制台的 Unicode 接口，而是按 locale 挑编码——实测是 **cp1252**。
于是 ``print("tag v0.1.0-alpha.1 与代码里的版本一致")`` 抛 ``UnicodeEncodeError``，
退出码 1，流水线红在**报喜的那一行**上：核对通过了，脚本却死在打印结果的时候。

本机的中文控制台（cp936）装得下这些字，所以这件事在开发机上永远看不见；英文 Windows
上把任何一个工具的输出重定向到文件，同样会中。``tools/`` 里**每个入口**都在 ``__main__``
里调一次 :func:`use_utf8_output`，理由是这道保证不该寄存在某份 YAML 的环境变量里
——那种保证会在下一个人加一步的时候消失（发版流水线里另外还设了
``PYTHONIOENCODING: utf-8`` 作为第二道，两道互不依赖）。

放在 ``__main__`` 里而不是模块顶层：被测试或别的工具 import 时不该顺手改掉调用方的
标准输出。
"""

from __future__ import annotations

import sys


def use_utf8_output() -> None:
    """把 ``stdout`` / ``stderr`` 重设为 UTF-8，编不出的字符退化成替代符而不是抛异常。

    拿不到 ``reconfigure``（被换成了别的对象）或者它拒绝重设时**静默跳过**：这个函数
    的全部意义是让输出别把进程弄死，它自己更不该成为新的失败点。
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError, AttributeError):  # 已 detach、或不是真的文本流
            continue
