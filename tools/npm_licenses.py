"""采集随产物分发的 npm 包许可（15 文档 §3.5）。

**这是分发义务，不是可选项。** `static/dist` 里打进了 react / react-dom /
lucide-react 的代码，它们都是 MIT——MIT 要求副本保留版权与许可声明。产物提交进版本库
并随 wheel、EXE 一起分发，所以那份声明必须跟着走。

**为什么是"快照 + 提交"而不是"生成清单时现采"**：`tools/licenses.py` 在发布流水线上
跑，那里只 `pip install`，**没有 node_modules**（15 文档 §3.2）。所以这里把结果写成
`frontend/npm-licenses.json` 提交进版本库，`licenses.py` 读那份快照。同一条路子与
前端产物本身一致：需要 Node 的东西一律"生成 + 提交 + 有漂移检查"。

范围是 `package.json` 的 `dependencies` **传递闭包**——不是 devDependencies：
后者（vite、typescript、playwright-core、lucide-static）不进产物。传递闭包很重要：
react 现在没有依赖，但哪天 lucide-react 拉进一个包，义务也跟着来。

用法::

    python tools/npm_licenses.py            # 重新采集
    python tools/npm_licenses.py --check    # 只比对，有漂移就非零退出
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_JSON = ROOT / "package.json"
NODE_MODULES = ROOT / "node_modules"
SNAPSHOT = ROOT / "frontend" / "npm-licenses.json"

#: 许可正文的文件名。npm 包的约定比 wheel 统一得多，但大小写与后缀都有变体。
LICENSE_NAMES = ("LICENSE", "LICENSE.md", "LICENSE.txt", "LICENCE", "COPYING", "license")

#: 红线：与 `tools/licenses.py` 同一条——强著佐权和单文件静态分发不相容。
FORBIDDEN = ("GPL-2.0", "GPL-3.0", "AGPL", "SSPL")


class MissingModules(RuntimeError):
    """没有 node_modules（没跑过 `pnpm install`）。"""


def direct_dependencies() -> dict[str, str]:
    payload = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    return dict(payload.get("dependencies", {}))


def _package_dir(name: str, parent: Path | None = None) -> Path | None:
    """按 Node 的解析顺序找包目录，找不到给 None。

    **pnpm 的布局不是扁平的**：只有直接依赖会出现在 `node_modules/<name>`，传递依赖
    在 `node_modules/.pnpm/<name>@<version>/node_modules/<name>` 下。写死第一种的话
    react-dom 的 `scheduler` 就找不到——而那正是义务清单里不能漏的东西。
    """
    candidates: list[Path] = []
    if parent is not None:
        candidates.append(parent / 'node_modules' / name)
    candidates.append(NODE_MODULES / name)
    for candidate in candidates:
        if (candidate / 'package.json').is_file():
            return candidate.resolve()
    # .pnpm 里的目录名把 `/` 写成 `+`（`@scope/pkg` -> `@scope+pkg@1.2.3`）。
    flattened = name.replace('/', '+')
    for store in sorted((NODE_MODULES / '.pnpm').glob(f'{flattened}@*')):
        candidate = store / 'node_modules' / name
        if (candidate / 'package.json').is_file():
            return candidate.resolve()
    return None


def _license_text(directory: Path) -> tuple[str, str]:
    """``(文件名, 正文)``。找不到时给 ``("", "")``，由调用方决定怎么报。"""
    for name in LICENSE_NAMES:
        path = directory / name
        if path.is_file():
            return name, path.read_text(encoding="utf-8", errors="replace").strip()
    return "", ""


def _normalize_license(value: object) -> str:
    """`license` 字段有三种写法：字符串、``{type, url}``、以及老包的 `licenses` 数组。"""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return str(value.get("type") or "")
    if isinstance(value, list):
        return " OR ".join(_normalize_license(item) for item in value if item)
    return ""


def collect() -> list[dict[str, str]]:
    """`dependencies` 的传递闭包，每项带许可标识与正文。按包名排序。"""
    if not NODE_MODULES.is_dir():
        raise MissingModules("没有 node_modules——跑 `pnpm install`")
    pending = list(direct_dependencies())
    # 传递依赖要从**引入它的那个包**旁边开始找（pnpm 的嵌套布局），所以记住来路。
    parents: dict[str, Path] = {}
    seen: set[str] = set()
    collected: list[dict[str, str]] = []
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        directory = _package_dir(name, parents.get(name))
        if directory is None:
            raise MissingModules(f"{name} 不在 node_modules 里——跑 `pnpm install`")
        payload = json.loads((directory / "package.json").read_text(encoding="utf-8"))
        file_name, text = _license_text(directory)
        homepage = payload.get("homepage") or ""
        if not homepage and isinstance(payload.get("repository"), dict):
            homepage = payload["repository"].get("url", "")
        collected.append(
            {
                "name": name,
                "version": str(payload.get("version", "")),
                "license": _normalize_license(payload.get("license") or payload.get("licenses")),
                "homepage": str(homepage),
                "license_file": file_name,
                "license_text": text,
            }
        )
        for child in payload.get("dependencies", {}):
            parents.setdefault(child, directory)
            pending.append(child)
    return sorted(collected, key=lambda item: item["name"])


def render(packages: list[dict[str, str]]) -> str:
    """快照文件。缩进 2 空格 + 排序键，让 diff 只在真的变了时才有内容。"""
    payload = {
        "_comment": (
            "由 tools/npm_licenses.py 生成，请勿手改。这些包的代码打进了 "
            "src/omnisight/presentation/static/dist，因此随产物分发（15 文档 §3.5）。"
        ),
        "packages": packages,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n"


def load() -> list[dict[str, str]]:
    """读快照。`tools/licenses.py` 走这条——它不需要 Node。"""
    try:
        payload = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    packages = payload.get("packages")
    return packages if isinstance(packages, list) else []


def forbidden(packages: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        pkg
        for pkg in packages
        if any(bad.casefold() in pkg["license"].casefold() for bad in FORBIDDEN)
    ]


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    try:
        packages = collect()
    except MissingModules as error:
        print(f"采集失败：{error}", file=sys.stderr)
        return 1
    if bad := forbidden(packages):
        names = "、".join(f"{pkg['name']}（{pkg['license']}）" for pkg in bad)
        print(f"依赖里出现不相容的许可：{names}", file=sys.stderr)
        return 1
    if missing := [pkg["name"] for pkg in packages if not pkg["license_text"]]:
        print(f"提醒：{len(missing)} 个包没随附许可正文（{'、'.join(missing)}）")
    rendered = render(packages)
    current = SNAPSHOT.read_text(encoding="utf-8") if SNAPSHOT.is_file() else None
    if "--check" in argv:
        if current == rendered:
            print(f"npm 许可快照与 node_modules 一致（{len(packages)} 个包）")
            return 0
        print(
            f"{SNAPSHOT.relative_to(ROOT)} 已过期，跑 `python tools/npm_licenses.py`",
            file=sys.stderr,
        )
        return 1
    if current == rendered:
        print(f"npm 许可快照无变化（{len(packages)} 个包）")
        return 0
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_text(rendered, encoding="utf-8")
    for pkg in packages:
        print(f"  {pkg['name']} {pkg['version']} — {pkg['license'] or '未声明'}")
    print(f"已生成 {SNAPSHOT.relative_to(ROOT)}（{len(packages)} 个包）")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _console import use_utf8_output

    use_utf8_output()
    sys.exit(main())
