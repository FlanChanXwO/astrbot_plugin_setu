from __future__ import annotations

from astrbot_plugin_setu.src.infrastructure.providers import (
    clear_provider,
    get_provider,
    init_provider_from_config,
)
from astrbot_plugin_setu.src.shared.config import SetuPluginConfig


def test_init_provider_from_config_uses_current_proxy_values(sample_config_dict) -> None:
    clear_provider()
    config_dict = sample_config_dict.copy()
    config_dict["setu_general"] = {**sample_config_dict["setu_general"], "api_type": "lolicon"}
    config_dict["api"] = {
        **sample_config_dict["api"],
        "lolicon": {**sample_config_dict["api"]["lolicon"], "proxy": "proxy.example.com"},
        "atri": {**sample_config_dict["api"]["atri"], "proxy": "atri-proxy.example.com"},
    }
    config = SetuPluginConfig(**config_dict)

    init_provider_from_config(config)
    provider = get_provider()

    assert getattr(provider, "proxy", None) == "proxy.example.com"
