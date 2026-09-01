"""API 路由包。按面板拆分，且**一律经服务层取数**——表现层里不许出现 SQL（02 文档 §1）。

每个模块只做三件事：校验参数（交给 :mod:`..validators`）、调一次服务、把结果套上公共
外壳。任何"顺手在这里算一下"的冲动都属于服务层。
"""

from __future__ import annotations

from typing import Any

from ..validators import parse_period


def resolved_period(context: Any, args):
    """URL 参数 → 展开好的 :class:`~omnisight.services.period.Period`。

    两步走：表现层校验语法，服务层做语义展开（``total`` 要知道哪天有数据）。
    """
    return context.services.context.resolve_period(parse_period(args))


def envelope(context: Any, period=None, *, warnings: list | None = None) -> dict[str, Any]:
    return context.services.context.envelope(period, warnings=warnings)


__all__ = ["envelope", "resolved_period"]
