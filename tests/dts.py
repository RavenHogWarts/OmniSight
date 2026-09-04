"""``.d.ts`` 里的 interface 声明 -> Python 字典，供接口契约测试比对真实响应。

**为什么要自己解析而不是引一个 TS 解析器**：需要的语法只有一种形态，而
``frontend/src/types/api.d.ts`` 刻意按那一种写（嵌套对象
一律具名 interface，不用内联字面量）。为这点东西加一条 Node 侧依赖不划算，而且
契约测试必须在没装 Node 的机器上也能跑——它查的是后端，不是前端。

解析器认得的东西恰好是那份声明用到的：``export interface A extends B { x: T; y?: T }``、
数组 ``T[]`` / ``T[][]``、``Record<string, T>``、联合 ``T | null``。别的都当"不认识"
处理（跳过递归），因此写出解析器读不懂的类型不会让测试假绿——只会少查一层，
而 :func:`unchecked_types` 会把这种情况报出来。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_INTERFACE = re.compile(
    r"^export\s+interface\s+(?P<name>\w+)(?:\s+extends\s+(?P<base>\w+))?\s*\{(?P<body>[^}]*)\}",
    re.MULTILINE,
)
_FIELD = re.compile(r"^\s*(?P<name>\w+)(?P<optional>\?)?\s*:\s*(?P<type>[^;]+);", re.MULTILINE)
_ALIAS = re.compile(r"^export\s+type\s+(?P<name>\w+)\s*=", re.MULTILINE)

#: 解析器认得的原始类型 -> 允许的 Python 类型。JSON 只有一种数字，因此 int 与 float 同列。
PRIMITIVES: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "number": (int, float),
    "boolean": (bool,),
}


@dataclass(frozen=True, slots=True)
class Field:
    name: str
    type: str
    optional: bool


@dataclass(frozen=True, slots=True)
class Interface:
    name: str
    base: str | None
    fields: tuple[Field, ...]


@dataclass(frozen=True, slots=True)
class Declarations:
    interfaces: dict[str, Interface] = field(default_factory=dict)
    #: ``export type X = ...`` 的名字。它们存在即可，内容不参与比对。
    aliases: frozenset[str] = frozenset()

    def fields_of(self, name: str) -> dict[str, Field]:
        """含 ``extends`` 继承来的字段。"""
        interface = self.interfaces[name]
        merged: dict[str, Field] = {}
        if interface.base:
            merged.update(self.fields_of(interface.base))
        for item in interface.fields:
            merged[item.name] = item
        return merged


def parse(path: Path) -> Declarations:
    text = path.read_text(encoding="utf-8")
    # 注释里有示例与 §引用，先剔掉，否则 `// x: string;` 会被当成字段。
    text = re.sub(r"^\s*//.*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    interfaces: dict[str, Interface] = {}
    for match in _INTERFACE.finditer(text):
        fields = tuple(
            Field(item.group("name"), item.group("type").strip(), bool(item.group("optional")))
            for item in _FIELD.finditer(match.group("body"))
        )
        name = match.group("name")
        interfaces[name] = Interface(name, match.group("base"), fields)
    aliases = frozenset(match.group("name") for match in _ALIAS.finditer(text))
    return Declarations(interfaces=interfaces, aliases=aliases)


def _split_union(type_str: str) -> list[str]:
    """顶层 ``|`` 拆分。尖括号与方括号里的 ``|`` 不算（``Record<string, A | B>``）。"""
    parts: list[str] = []
    depth = 0
    current = ""
    for char in type_str:
        if char in "<[(":
            depth += 1
        elif char in ">])":
            depth -= 1
        if char == "|" and depth == 0:
            parts.append(current.strip())
            current = ""
        else:
            current += char
    parts.append(current.strip())
    return [part for part in parts if part]


def _unwrap(type_str: str) -> str:
    type_str = type_str.strip()
    while type_str.startswith("(") and type_str.endswith(")"):
        type_str = type_str[1:-1].strip()
    return type_str


def mismatches(
    declarations: Declarations, type_str: str, value: object, path: str
) -> list[str]:
    """按声明的类型核对一个值，返回人类可读的不一致说明（空表示一致）。

    认不出的类型**跳过**而不是报错：解析器只认那一小套语法，把"没看懂"当成失败会
    让契约测试变成解析器的测试。真正的漏检由 :func:`unchecked_types` 报出来。
    """
    type_str = _unwrap(type_str)
    parts = _split_union(type_str)
    if len(parts) > 1:
        if value is None:
            return [] if "null" in parts else [f"{path}：后端给了 null，声明是 {type_str}"]
        concrete = [part for part in parts if part not in {"null", "undefined"}]
        if len(concrete) != 1:
            return []  # 多个非空分支，无法判定用的是哪一个
        return mismatches(declarations, concrete[0], value, path)

    if type_str.endswith("[]"):
        if not isinstance(value, list):
            return [f"{path}：声明是数组 {type_str}，后端给了 {type(value).__name__}"]
        element = type_str[:-2]
        problems: list[str] = []
        for index, item in enumerate(value):
            problems += mismatches(declarations, element, item, f"{path}[{index}]")
        return problems

    record = re.fullmatch(r"Record<\s*string\s*,\s*(?P<value>.+)>", type_str)
    if record:
        if not isinstance(value, dict):
            return [f"{path}：声明是 {type_str}，后端给了 {type(value).__name__}"]
        problems = []
        for key, item in value.items():
            problems += mismatches(declarations, record.group("value"), item, f"{path}.{key}")
        return problems

    if type_str in PRIMITIVES:
        allowed = PRIMITIVES[type_str]
        # bool 是 int 的子类：不这么挡，`number` 会接受 true。
        if isinstance(value, bool) != (type_str == "boolean"):
            return [f"{path}：声明是 {type_str}，后端给了 {type(value).__name__}"]
        if not isinstance(value, allowed):
            return [f"{path}：声明是 {type_str}，后端给了 {type(value).__name__}"]
        return []

    if type_str in declarations.interfaces:
        if not isinstance(value, dict):
            return [f"{path}：声明是 {type_str}，后端给了 {type(value).__name__}"]
        fields = declarations.fields_of(type_str)
        problems = []
        for key in value:
            if key not in fields:
                problems.append(
                    f"{path}.{key}：后端有这个字段，{type_str} 没有声明它"
                )
        for name, item in fields.items():
            if name not in value:
                if not item.optional:
                    problems.append(
                        f"{path}.{name}：{type_str} 声明了必填字段，后端没给"
                    )
                continue
            problems += mismatches(declarations, item.type, value[name], f"{path}.{name}")
        return problems

    return []  # 类型别名、字面量联合、认不出的写法


def unchecked_types(declarations: Declarations, type_str: str) -> set[str]:
    """这个类型里**没被 :func:`mismatches` 覆盖**的名字。探针测试用它。"""
    type_str = _unwrap(type_str)
    parts = _split_union(type_str)
    if len(parts) > 1:
        concrete = [part for part in parts if part not in {"null", "undefined"}]
        if len(concrete) != 1:
            return {type_str}
        return unchecked_types(declarations, concrete[0])
    if type_str.endswith("[]"):
        return unchecked_types(declarations, type_str[:-2])
    record = re.fullmatch(r"Record<\s*string\s*,\s*(?P<value>.+)>", type_str)
    if record:
        return unchecked_types(declarations, record.group("value"))
    if type_str in PRIMITIVES or type_str in declarations.aliases:
        return set()
    if type_str in declarations.interfaces:
        found: set[str] = set()
        for item in declarations.fields_of(type_str).values():
            found |= unchecked_types(declarations, item.type)
        return found
    return {type_str}
