"""PyInstaller 打包（10 文档 §2.1）。

**这是允许出现 ``sys.platform`` 判断的少数地方之一**：它是构建脚本而非运行时代码，
不受 02 文档 §1 那条约束管辖。约束的目标是防止业务逻辑里散落平台分支，而打包
本身就是平台特定的操作。

结构刻意是"通用参数 + 平台补丁"，不是三份独立脚本——三份脚本会各自漂移，
而真正的差异只有下面这几行。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
BUILD = ROOT / "build"

#: PyInstaller 的历史包袱：``--add-data`` 的分隔符在 Windows 上是 ``;``，其余是 ``:``。
#: 硬编码任一形式都会让另一个平台构建失败，且报错信息毫无指向性。
SEP = ";" if sys.platform == "win32" else ":"

PKG = "src/omnisight"

COMMON = [
    # 入口是根目录的 main.py，不是包内的 __main__.py：后者用相对导入，
    # 而 PyInstaller 以顶层脚本方式执行入口，没有父包可用。见 main.py 的说明。
    "main.py",
    "--name=OmniSight",
    "--noconsole",
    "--noconfirm",
    f"--paths={ROOT / 'src'}",
    f"--add-data={PKG}/presentation/templates{SEP}omnisight/presentation/templates",
    f"--add-data={PKG}/presentation/static{SEP}omnisight/presentation/static",
    f"--add-data=assets/omnisight.png{SEP}omnisight/presentation/static/assets",
    "--exclude-module=tkinter",
    "--exclude-module=unittest",
    "--exclude-module=pytest",
]

PLATFORM: dict[str, list[str]] = {
    "win32": [
        "--onefile",
        "--icon=assets/omnisight.ico",
        # tzdata 必须显式收集，否则 ZoneInfo 在打包后找不到时区库。
        "--collect-data=tzdata",
    ],
    "darwin": [
        # 不用 --onefile：TCC（隐私权限）记录绑定 bundle id + 签名，而 onefile 每次
        # 运行都解压到新的临时目录，会让"输入监控"授权行为变得不可预期（M9 生效）。
        "--windowed",
        "--icon=assets/omnisight.icns",
        "--osx-bundle-identifier=com.ravenhogwarts.omnisight",
    ],
    "linux": ["--onefile"],
}


def build(*, clean: bool = True, exclude_pynput: bool = False) -> int:
    if clean:
        _clean_dist()
        shutil.rmtree(BUILD, ignore_errors=True)

    args = [*COMMON, *PLATFORM.get(sys.platform, ["--onefile"])]
    if exclude_pynput:
        # 精简变体：不含低级键盘钩子模块，代价是专用后端失败时无法降级
        # （10 文档 §1.1 的取舍）。
        args.append("--exclude-module=pynput")

    print("PyInstaller 参数：")
    for arg in args:
        print(f"  {arg}")
    completed = subprocess.run(
        [sys.executable, "-m", "PyInstaller", *args], cwd=ROOT, check=False
    )
    if completed.returncode != 0:
        return completed.returncode
    _write_portable_marker()
    return 0


def _clean_dist() -> None:
    """清 ``dist/`` 但**保留 ``dist/data/``**。

    这是踩过的坑。``dist/portable.marker`` 一旦存在（冒烟测试会创建它），手动双击
    ``dist/OmniSight.exe`` 就以便携模式运行，数据落在 ``dist/data/``——而旧版这里
    一句 ``rmtree(DIST)`` 会把它连库一起删掉，且毫无提示。症状是"我明明跑了一下午，
    统计全没了"，而真正的原因在打包脚本里。

    与 M2 的 ``.bench/`` 是同一类问题（基准库原本落在 ``build/``，被下一次打包删掉），
    所以处理方式也一样：**构建产物目录里的用户数据一律不碰。**
    """
    if not DIST.exists():
        return
    data_dir = DIST / "data"
    for path in DIST.iterdir():
        if path == data_dir:
            print(f"保留 {path}（便携模式的数据目录，打包不碰它）")
            continue
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)


def _write_portable_marker() -> None:
    """便携版与安装版是同一个二进制，区别只有这个标记文件（10 文档 §2.2）。"""
    marker = DIST / "portable.marker"
    if DIST.exists():
        marker.write_text(
            "存在此文件时，OmniSight 把数据写在同级 data/ 目录，而不是系统的用户数据目录。\n",
            encoding="utf-8",
        )
        print(f"已写入 {marker.relative_to(ROOT)}")


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    return build(clean="--no-clean" not in argv, exclude_pynput="--exclude-pynput" in argv)


if __name__ == "__main__":
    sys.exit(main())
