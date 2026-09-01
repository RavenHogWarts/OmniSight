"""仓储层：唯一允许出现 SQL 的地方（02 文档 §1）。

服务层调仓储，表现层调服务层。表现层里不许有一个 SQL 字符串——现状 TimeLens 的
``web_app.py`` 有 710 行且混杂图标提取、分类规则与时间格式化，这是本次要拆掉的最大
一团。M1 只落地"够验证闭环"的查询，完整集合在 M2。
"""

from .apps import AppRegistry
from .keys import KeyRepository
from .usage import UsageRepository

__all__ = ["AppRegistry", "KeyRepository", "UsageRepository"]
