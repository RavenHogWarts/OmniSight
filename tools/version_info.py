"""生成 Windows 版本资源（10 文档 §2.2 的"图标、版本信息"那一项）。

**为什么这件事必须做**：未签名的 EXE 已经要让用户点一次"仍要运行"（§2.3），
如果属性页里连"文件说明""产品名称"都是空的，SmartScreen 的警告框会显示
``OmniSight.exe`` 而不是产品名——一个记录按键的程序，在信任成本最高的那一屏上
显示得像来路不明的东西，是可以避免的自伤。杀软的启发式打分同样吃这些字段。

产物是一个 ``VSVersionInfo(...)`` 的 Python 字面量文件，交给
``pyinstaller --version-file=``。语言用 zh-CN（0x0804）：字符串本身是中文，
声明成 en-US 会让某些取值按语言回退时显示乱码。

版本号从 :data:`omnisight.__version__` 来，且**只有一处真源**。PEP 440 的
``0.1.0-alpha.1`` 这类形式无法直接塞进 Windows 要的四元组（那里只接受整数），
因此 :func:`file_version` 做一次解析：数字段取前三段补零，``dev`` / ``alpha``
等预发布标记不进四元组，但**保留在字符串字段里**——属性页上必须能看出这是
一个预发布版本。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from omnisight import APP_NAME, __version__  # noqa: E402

COMPANY = "RavenHogwarts"
DESCRIPTION = "本地应用使用时长与键盘统计工具"
COPYRIGHT = "Copyright (c) RavenHogwarts. MIT License."
#: zh-CN + Unicode 代码页。StringTable 的键是 "语言ID(4位十六进制)代码页(4位)"。
LANG_CODEPAGE = "080404B0"
LANG_ID = 2052  # 0x0804
CODEPAGE = 1200  # Unicode


def file_version(version: str = __version__) -> tuple[int, int, int, int]:
    """PEP 440 版本 → Windows 的四元整数组。

    ``0.1.0-alpha.1`` → ``(0, 1, 0, 0)``；``1.2`` → ``(1, 2, 0, 0)``；
    ``1.2.3.4`` → ``(1, 2, 3, 4)``。非数字段（``dev0`` / ``-alpha.1`` / ``+local``）
    一律丢弃——四元组里放不下，而放个 0 比放个错的数字诚实。
    """
    release = re.split(r"[^0-9.]", version, maxsplit=1)[0]
    parts = [int(piece) for piece in release.strip(".").split(".") if piece.isdigit()]
    quad = ([*parts, 0, 0, 0, 0])[:4]
    return (quad[0], quad[1], quad[2], quad[3])


#: PEP 440 允许的全部预发布拼写与分隔符（``0.1.0a1`` / ``0.1.0-alpha.1`` /
#: ``0.1.0.rc.2`` / ``1.0.dev0`` 都要能认出来）。只在 ``packaging`` 不可用时兜底。
_PRERELEASE = re.compile(
    r"(?:^|[-_.])(?:dev|alpha|beta|pre|preview|a|b|c|rc)[-_.]?\d*", re.IGNORECASE
)


def is_prerelease(version: str = __version__) -> bool:
    """是否预发布版本。

    优先用 ``packaging``（它就是 PEP 440 的参考实现），不可用时退回正则。
    **不能只认 ``dev``**：M6 起版本串是 ``0.1.0-alpha.1``，而漏判的后果是属性页
    把一个 alpha 显示成正式产品——正好是这份文件想避免的那类不诚实。
    """
    try:
        from packaging.version import InvalidVersion, Version
    except ImportError:  # pragma: no cover - 开发环境必有 packaging（pyinstaller 依赖）
        return bool(_PRERELEASE.search(version))
    try:
        parsed = Version(version)
    except InvalidVersion:  # pragma: no cover - 版本串写坏了，按预发布处理更保守
        return True
    return parsed.is_prerelease or parsed.is_devrelease


def render(version: str = __version__) -> str:
    quad = file_version(version)
    prerelease = is_prerelease(version)
    product = f"{APP_NAME}{'（预发布）' if prerelease else ''}"
    return f'''# 由 tools/version_info.py 生成，请勿手改。
# 版本号的真源是 src/omnisight/__init__.py 的 __version__。
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={quad},
    prodvers={quad},
    mask=0x3f,
    # 0x2 = VS_FF_PRERELEASE。标志位是给工具看的（属性页上并不显示它），所以
    # 预发布这件事**同时**写进 ProductName 字符串——用户看得到的那一半更重要。
    flags={"0x2" if prerelease else "0x0"},
    OS=0x40004,      # VOS_NT_WINDOWS32
    fileType=0x1,    # VFT_APP
    subtype=0x0,
    date=(0, 0),
  ),
  kids=[
    StringFileInfo([
      StringTable(
        {LANG_CODEPAGE!r},
        [
          StringStruct('CompanyName', {COMPANY!r}),
          StringStruct('FileDescription', {DESCRIPTION!r}),
          StringStruct('FileVersion', {version!r}),
          StringStruct('InternalName', {APP_NAME!r}),
          StringStruct('OriginalFilename', {f"{APP_NAME}.exe"!r}),
          StringStruct('ProductName', {product!r}),
          StringStruct('ProductVersion', {version!r}),
          StringStruct('LegalCopyright', {COPYRIGHT!r}),
        ],
      )
    ]),
    VarFileInfo([VarStruct('Translation', [{LANG_ID}, {CODEPAGE}])]),
  ],
)
'''


def write(target: Path, version: str = __version__) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render(version), encoding="utf-8")
    return target


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    positional = [arg for arg in argv if not arg.startswith("--")]
    target = Path(positional[0]) if positional else ROOT / "build" / "version_info.txt"
    path = write(target)
    print(f"已生成 {path}（版本 {__version__} → {file_version()}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
