"""PyInstaller 打包入口。

``src/omnisight/__main__.py`` 服务的是 ``python -m omnisight``，它用相对导入
（``from .app import run``）。PyInstaller 把入口脚本当**顶层脚本**执行，此时不存在
父包，相对导入会直接抛 ``ImportError``——而 ``--noconsole`` 下这个错误没有任何
出口，用户只看到"双击了没反应"。

因此打包用这个独立的启动器：绝对导入、不依赖包上下文。两个入口共用
``omnisight.app.run``，不会各自漂移。
"""

from __future__ import annotations

import multiprocessing
import sys

from omnisight.app import run

if __name__ == "__main__":
    # 打包后若将来用到多进程，没有这一行会让子进程重新执行整个启动流程。
    multiprocessing.freeze_support()
    sys.exit(run(sys.argv[1:]))
