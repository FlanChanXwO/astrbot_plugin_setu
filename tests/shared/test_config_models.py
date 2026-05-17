from __future__ import annotations

from astrbot_plugin_setu.src.shared.config import SetuPluginConfig


def test_provider_config_accepts_empty_aspect_ratio(sample_config_dict) -> None:
    config = SetuPluginConfig(**sample_config_dict)

    assert config.api.lolicon.aspect_ratio is None
    assert config.api.atri.aspect_ratio is None


def test_message_send_failed_enabled_default_true(sample_config_dict) -> None:
    config = SetuPluginConfig(**sample_config_dict)
    assert config.msg_send_failed_enabled is True


def test_resolve_message_supports_placeholders(sample_config_dict) -> None:
    config = SetuPluginConfig(**sample_config_dict)

    text = config.resolve_message("max_count_exceeded", max_count=7)

    assert text == "一次最多只能获取7张哦~"


def test_resolve_message_respects_enabled_toggle(sample_config_dict) -> None:
    config_dict = sample_config_dict.copy()
    config_dict["messages"] = {
        **sample_config_dict["messages"],
        "fetch_failed": {"enabled": False, "text": "X"},
    }
    config = SetuPluginConfig(**config_dict)

    assert config.resolve_message("fetch_failed") is None
