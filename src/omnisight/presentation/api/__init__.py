"""API 路由包。

M1 只有一个下划线前缀的临时验证端点；05 文档定义的正式端点集合在 M2 落地，
届时这里会按面板拆成 ``usage.py`` / ``keyboard.py`` / ``apps.py`` / ``insights.py``
等模块，且一律经服务层取数——表现层里不许出现 SQL（02 文档 §1）。
"""

from . import debug

__all__ = ["debug"]
