"""图片提供商实现，使用策略模式。"""

from __future__ import annotations

from typing import Any

from astrbot.api import logger

from .base import SetuImageProvider
from .custom import CustomApiProvider
from .lolicon import LoliconProvider
from .multi import MultiApiProvider
from .sexnyan import SexNyanRunProvider

# 提供商注册表
PROVIDERS: dict[str, type[SetuImageProvider]] = {
    "lolicon": LoliconProvider,
    "sexnyan": SexNyanRunProvider,
}

# 多API策略下的内置提供商列表
BUILTIN_PROVIDERS = ["lolicon", "sexnyan"]


def get_provider(
    api_type: str,
    custom_config: dict[str, Any] | None = None,
    parser_config: dict[str, Any] | None = None,
    custom_api_configs: list[dict[str, Any]] | None = None,
    multi_api_strategy: str = "round_robin",
    lolicon_config: dict[str, Any] | None = None,
) -> SetuImageProvider | MultiApiProvider:
    """根据类型名称获取提供商实例。

    参数:
        api_type: 提供商类型（'lolicon'、'sexnyan'、'custom' 或 'all'）。
        custom_config: 自定义 API 配置（当 api_type 为 custom 时使用）。
        parser_config: API 响应解析配置（当 api_type 为 custom 时使用）。
        custom_api_configs: 自定义 API 配置列表（template_list 格式）。
        multi_api_strategy: 多 API 策略（'round_robin'、'random'、'failover'）。
        lolicon_config: Lolicon 专属配置参数。

    返回:
        提供商实例（如果类型未知则默认返回 lolicon）。
    """
    if api_type == "all":
        # 创建多API提供商（内置API）
        providers = []
        for name in BUILTIN_PROVIDERS:
            if name == "lolicon" and lolicon_config:
                provider = LoliconProvider(**lolicon_config)
            else:
                provider = PROVIDERS[name]()
            providers.append(provider)
        return MultiApiProvider(providers, strategy=multi_api_strategy)

    if api_type == "custom":
        # 优先使用新的 template_list 配置格式
        if (
            custom_api_configs
            and isinstance(custom_api_configs, list)
            and len(custom_api_configs) > 0
        ):
            if len(custom_api_configs) == 1:
                # 只有一个配置，直接使用
                cfg = custom_api_configs[0]
                api_config = {
                    "url": cfg.get("url", ""),
                    "method": cfg.get("method", "GET"),
                    "timeout": cfg.get("timeout", 30),
                }
                parser_cfg = {
                    "type": cfg.get("parser_type", "auto"),
                    "json_path": cfg.get("json_path", ""),
                }
                return CustomApiProvider(api_config, parser_cfg)
            else:
                # 多个配置，创建多API提供商
                providers = []
                for cfg in custom_api_configs:
                    api_config = {
                        "url": cfg.get("url", ""),
                        "method": cfg.get("method", "GET"),
                        "timeout": cfg.get("timeout", 30),
                    }
                    parser_cfg = {
                        "type": cfg.get("parser_type", "auto"),
                        "json_path": cfg.get("json_path", ""),
                    }
                    providers.append(CustomApiProvider(api_config, parser_cfg))
                return MultiApiProvider(providers, strategy=multi_api_strategy)

        # 兼容旧的配置格式
        if custom_config:
            return CustomApiProvider(custom_config, parser_config or {})

        logger.warning("api_type 为 custom 但未提供配置，回退到 lolicon")
        if lolicon_config:
            return LoliconProvider(**lolicon_config)
        return LoliconProvider()

    provider_cls = PROVIDERS.get(api_type)
    if provider_cls is None:
        logger.warning("未知的 api_type '%s'，回退到 lolicon", api_type)
        provider_cls = LoliconProvider

    # 创建实例
    if api_type == "lolicon" and lolicon_config:
        return provider_cls(**lolicon_config)
    return provider_cls()


__all__ = [
    "SetuImageProvider",
    "MultiApiProvider",
    "LoliconProvider",
    "SexNyanRunProvider",
    "CustomApiProvider",
    "get_provider",
]
