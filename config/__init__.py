"""Setu 插件配置解析和兼容性辅助模块。

提供配置读取、标签解析、以及新旧配置格式的兼容性支持。
"""

from __future__ import annotations

from astrbot.core import AstrBotConfig

from .api import ApiConfigMixin
from .base import ConfigBase
from .delivery import DeliveryConfigMixin
from .helpers import parse_count
from .html_card import HtmlCardConfigMixin
from .messages import MessagesConfigMixin
from .safety import SafetyConfigMixin


class SetuConfig(
    ConfigBase,
    ApiConfigMixin,
    DeliveryConfigMixin,
    HtmlCardConfigMixin,
    SafetyConfigMixin,
    MessagesConfigMixin,
):
    """Setu 插件配置包装类。

    支持嵌套配置和旧版配置的兼容性处理，提供类型安全的配置访问方法。

    通过多重继承组合各个功能模块的配置：
    - ApiConfigMixin: API 相关配置
    - DeliveryConfigMixin: 发送相关配置
    - HtmlCardConfigMixin: HTML 卡片配置
    - SafetyConfigMixin: 安全和缓存配置
    - MessagesConfigMixin: 消息配置
    """

    def __init__(self, config: AstrBotConfig):
        """初始化配置包装器。

        参数:
            config: AstrBot 配置对象
        """
        super().__init__(config)


__all__ = ["SetuConfig", "parse_count"]
