"""仓储层：唯一允许出现 SQL 的地方（02 文档 §1）。

服务层拿仓储返回的字典或数据类拼装响应，绝不自己拼 SQL——现状 TimeLens 的
``web_app.py`` 里 710 行里混着建表、取数、格式化与时间戳解析，而这正是本项目要避免的
那一类。
"""

from .apps import AppDirectory, AppMeta, AppRegistry
from .insights import InsightsRepository
from .keys import KeyRepository
from .usage import UsageRepository

__all__ = [
    "AppDirectory",
    "AppMeta",
    "AppRegistry",
    "InsightsRepository",
    "KeyRepository",
    "UsageRepository",
]
