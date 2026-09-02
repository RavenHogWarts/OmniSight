"""生成托盘与打包用的图标资源。

刻意用脚本生成而不是提交一张手工 PNG：图标是纯几何形状，脚本比二进制文件更容易
审查与改动，而 Pillow 本来就是运行时依赖。运行 ``python tools/make_icon.py``
后把产物提交进仓库——打包时不再依赖本脚本。
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
ACCENT = (47, 141, 251, 255)
WHITE = (255, 255, 255, 255)
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)


def render(size: int) -> Image.Image:
    """一枚"眼睛"轮廓：外圈品牌蓝、内圈白，寓意"全览"。"""
    scale = 8
    canvas = Image.new("RGBA", (size * scale, size * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    edge = size * scale
    inset = edge * 0.06
    draw.ellipse((inset, inset, edge - inset, edge - inset), fill=ACCENT)
    hole = edge * 0.34
    draw.ellipse((hole, hole, edge - hole, edge - hole), fill=WHITE)
    return canvas.resize((size, size), Image.LANCZOS)


def main() -> int:
    ASSETS.mkdir(parents=True, exist_ok=True)
    png = ASSETS / "omnisight.png"
    render(256).save(png)
    ico = ASSETS / "omnisight.ico"
    render(256).save(ico, sizes=[(s, s) for s in ICO_SIZES])
    print(f"已生成 {png.relative_to(ROOT)} 与 {ico.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    # 见 tools/_console.py：runner 上 stdout 是管道，按 locale 挑到 cp1252，
    # 一行中文输出就能让进程死在 UnicodeEncodeError 上。
    from _console import use_utf8_output

    use_utf8_output()
    sys.exit(main())
