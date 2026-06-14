from __future__ import annotations

from astrbot_plugin_setu.src.infrastructure.providers import (
    clear_provider,
    get_provider,
    init_provider,
    init_provider_from_config,
)
from astrbot_plugin_setu.src.infrastructure.providers.atri import AtriProvider
from astrbot_plugin_setu.src.infrastructure.providers.lolicon import LoliconProvider
from astrbot_plugin_setu.src.infrastructure.providers.multi import MultiApiProvider
from astrbot_plugin_setu.src.infrastructure.providers.sexnyan import SexNyanRunProvider
from astrbot_plugin_setu.src.shared.config import SetuPluginConfig


def test_init_provider_from_config_uses_current_proxy_values(
    sample_config_dict,
) -> None:
    clear_provider()
    config_dict = sample_config_dict.copy()
    config_dict["setu_general"] = {
        **sample_config_dict["setu_general"],
        "api_type": "lolicon",
    }
    config_dict["api"] = {
        **sample_config_dict["api"],
        "provider_overrides": [
            {"__template_key": "lolicon", "proxy": "proxy.example.com"},
            {"__template_key": "atri", "proxy": "atri-proxy.example.com"},
        ],
    }
    config = SetuPluginConfig(**config_dict)

    init_provider_from_config(config)
    provider = get_provider()

    assert getattr(provider, "proxy", None) == "proxy.example.com"


def test_init_provider_from_config_applies_atri_proxy_override(
    sample_config_dict,
) -> None:
    clear_provider()
    config_dict = sample_config_dict.copy()
    config_dict["setu_general"] = {
        **sample_config_dict["setu_general"],
        "api_type": "atri",
    }
    config_dict["api"] = {
        **sample_config_dict["api"],
        "provider_overrides": [
            {"__template_key": "lolicon", "proxy": "proxy.example.com"},
            {"__template_key": "atri", "proxy": "atri-proxy.example.com"},
        ],
    }
    config = SetuPluginConfig(**config_dict)

    init_provider_from_config(config)
    provider = get_provider()

    assert isinstance(provider, AtriProvider)
    assert provider.proxy == "atri-proxy.example.com"


def test_init_provider_from_config_applies_sexnyan_override(
    sample_config_dict,
) -> None:
    clear_provider()
    config_dict = sample_config_dict.copy()
    config_dict["setu_general"] = {
        **sample_config_dict["setu_general"],
        "api_type": "sexnyan",
    }
    config_dict["api"] = {
        **sample_config_dict["api"],
        "provider_overrides": [
            {
                "__template_key": "sexnyan",
                "proxy": "sex-proxy.example.com",
                "uid": [1, 2],
                "keyword": "blue",
            }
        ],
    }
    config = SetuPluginConfig(**config_dict)

    init_provider_from_config(config)
    provider = get_provider()

    assert isinstance(provider, SexNyanRunProvider)
    assert provider.proxy == "sex-proxy.example.com"
    assert provider.uid == [1, 2]
    assert provider.keyword == "blue"


def test_init_provider_from_config_applies_sexnyan_override_in_all_mode(
    sample_config_dict,
) -> None:
    clear_provider()
    config_dict = sample_config_dict.copy()
    config_dict["setu_general"] = {
        **sample_config_dict["setu_general"],
        "api_type": "all",
    }
    config_dict["api"] = {
        **sample_config_dict["api"],
        "provider_overrides": [
            {
                "__template_key": "sexnyan",
                "proxy": "sex-proxy.example.com",
                "uid": [42],
                "keyword": "mika",
            }
        ],
    }
    config = SetuPluginConfig(**config_dict)

    init_provider_from_config(config)
    provider = get_provider()

    assert isinstance(provider, MultiApiProvider)
    sexnyan = next(
        item for item in provider.providers if isinstance(item, SexNyanRunProvider)
    )
    assert sexnyan.proxy == "sex-proxy.example.com"
    assert sexnyan.uid == [42]
    assert sexnyan.keyword == "mika"


def test_custom_provider_without_config_falls_back_to_lolicon_without_proxy() -> None:
    clear_provider()

    provider = init_provider(api_type="custom", custom_api_configs=[])

    assert isinstance(provider, LoliconProvider)
    assert provider.proxy == ""
    assert provider._apply_proxy_to_urls(
        ["https://i.pximg.net/img-original/img/2024/01/01/00/00/00/1_p0.jpg"],
        provider.proxy,
        "LoliconProvider",
    ) == ["https://i.pximg.net/img-original/img/2024/01/01/00/00/00/1_p0.jpg"]
