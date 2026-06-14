from __future__ import annotations

import pytest
from pydantic import ValidationError

from astrbot_plugin_setu.src.infrastructure.config import heal_astrbot_plugin_config
from astrbot_plugin_setu.src.shared.config import SetuPluginConfig, should_auto_revoke


def test_provider_config_accepts_empty_aspect_ratio(sample_config_dict) -> None:
    config = SetuPluginConfig(**sample_config_dict)

    assert config.aspect_ratio == ""
    assert config.atri_aspect_ratio == ""


def test_auto_revoke_scope_defaults_to_none() -> None:
    config = SetuPluginConfig()

    assert config.auto_revoke_scope == "none"
    assert should_auto_revoke(config.auto_revoke_scope, is_r18=False) is False
    assert should_auto_revoke(config.auto_revoke_scope, is_r18=True) is False


def test_auto_revoke_scope_validation(sample_config_dict) -> None:
    config_dict = sample_config_dict.copy()
    config_dict["delivery"] = {
        **sample_config_dict["delivery"],
        "auto_revoke_scope": "all",
    }

    config = SetuPluginConfig(**config_dict)

    assert config.auto_revoke_scope == "all"
    assert should_auto_revoke("sfw", is_r18=False) is True
    assert should_auto_revoke("sfw", is_r18=True) is False
    assert should_auto_revoke("r18", is_r18=False) is False
    assert should_auto_revoke("r18", is_r18=True) is True
    assert should_auto_revoke("all", is_r18=False) is True
    assert should_auto_revoke("all", is_r18=True) is True

    invalid = sample_config_dict.copy()
    invalid["delivery"] = {
        **sample_config_dict["delivery"],
        "auto_revoke_scope": "bad",
    }
    with pytest.raises(ValidationError):
        SetuPluginConfig(**invalid)


def test_message_send_failed_enabled_default_false() -> None:
    config = SetuPluginConfig()
    assert config.msg_send_failed_enabled is False
    assert config.resolve_message("send_failed") is None


def test_resolve_message_supports_placeholders(sample_config_dict) -> None:
    config_dict = sample_config_dict.copy()
    config_dict["messages"] = {
        **sample_config_dict["messages"],
        "max_count_exceeded": {
            "enabled": True,
            "text": "一次最多只能获取{max_count}张哦~",
        },
    }
    config = SetuPluginConfig(**config_dict)

    text = config.resolve_message("max_count_exceeded", max_count=7)

    assert text == "一次最多只能获取7张哦~"


def test_config_healer_migrates_legacy_auto_revoke_scope() -> None:
    schema = {
        "delivery": {
            "type": "object",
            "items": {
                "auto_revoke_scope": {
                    "type": "string",
                    "default": "none",
                    "options": ["none", "sfw", "r18", "all"],
                }
            },
        }
    }
    healed, changes = heal_astrbot_plugin_config(
        {"delivery": {"auto_revoke_r18": True}}, schema
    )

    assert healed["delivery"] == {"auto_revoke_scope": "r18"}
    assert changes

    healed, _ = heal_astrbot_plugin_config(
        {"delivery": {"auto_revoke_r18": False}}, schema
    )
    assert healed["delivery"] == {"auto_revoke_scope": "none"}


def test_config_healer_keeps_new_auto_revoke_scope_when_legacy_exists() -> None:
    schema = {
        "delivery": {
            "type": "object",
            "items": {
                "auto_revoke_scope": {
                    "type": "string",
                    "default": "none",
                    "options": ["none", "sfw", "r18", "all"],
                }
            },
        }
    }
    healed, changes = heal_astrbot_plugin_config(
        {"delivery": {"auto_revoke_r18": True, "auto_revoke_scope": "all"}},
        schema,
    )

    assert healed["delivery"] == {"auto_revoke_scope": "all"}
    assert changes


def test_config_healer_migrates_legacy_session_template_revoke_scope() -> None:
    healed, changes = heal_astrbot_plugin_config(
        {"session_configs": [{"session_id": "g1", "auto_revoke_r18": "true"}]},
        {},
    )

    assert healed["session_configs"][0] == {
        "session_id": "g1",
        "auto_revoke_scope": "r18",
    }
    assert changes


def test_resolve_message_respects_enabled_toggle(sample_config_dict) -> None:
    config_dict = sample_config_dict.copy()
    config_dict["messages"] = {
        **sample_config_dict["messages"],
        "fetch_failed": {"enabled": False, "text": "X"},
    }
    config = SetuPluginConfig(**config_dict)

    assert config.resolve_message("fetch_failed") is None


def test_resolve_message_supports_dotted_builtin_error_keys(
    sample_config_dict,
) -> None:
    config_dict = sample_config_dict.copy()
    config_dict["messages"] = {
        **sample_config_dict["messages"],
        "error_invalid_request": {"enabled": True, "text": "请求参数无效"},
    }
    config = SetuPluginConfig(**config_dict)

    assert config.resolve_message("error.invalid_request") == "请求参数无效"


def test_message_template_override_takes_precedence(sample_config_dict) -> None:
    config_dict = sample_config_dict.copy()
    config_dict["messages"] = {
        **sample_config_dict["messages"],
        "message_overrides": [
            {
                "__template_key": "message",
                "message_key": "max_count_exceeded",
                "enabled": True,
                "text": "最多 {max_count} 张",
            }
        ],
    }
    config = SetuPluginConfig(**config_dict)

    assert config.resolve_message("max_count_exceeded", max_count=3) == "最多 3 张"


def test_provider_template_override_takes_precedence(sample_config_dict) -> None:
    config_dict = sample_config_dict.copy()
    config_dict["api"] = {
        **sample_config_dict["api"],
        "provider_overrides": [
            {
                "__template_key": "lolicon",
                "image_size": "regular",
                "proxy": "pixiv.example.test",
                "aspect_ratio": "vertical",
                "uid": [123],
                "keyword": "blue",
                "exclude_ai": False,
            }
        ],
    }
    config = SetuPluginConfig(**config_dict)

    assert config.image_size == "regular"
    assert config.proxy == "pixiv.example.test"
    assert config.aspect_ratio == "vertical"
    assert config.uid == [123]
    assert config.keyword == "blue"
    assert config.exclude_ai is False


def test_delivery_napcat_transport_defaults(sample_config_dict) -> None:
    config = SetuPluginConfig(**sample_config_dict)

    assert config.napcat_local_file_mode == "disabled"
    assert config.napcat_local_file_allowed_roots == []
    assert config.napcat_stream_chunk_kb == 64


def test_delivery_platform_transport_template_takes_precedence(
    sample_config_dict,
) -> None:
    config_dict = sample_config_dict.copy()
    config_dict["delivery"] = {
        **sample_config_dict["delivery"],
        "platform_transports": [
            {
                "__template_key": "napcat",
                "stream_mode": "always",
                "stream_chunk_kb": 512,
                "local_file_mode": "fallback",
                "local_file_allowed_roots": ["/AstrBot/data"],
            }
        ],
        "napcat_stream_mode": "disabled",
        "napcat_stream_chunk_kb": 64,
        "napcat_local_file_mode": "disabled",
        "napcat_local_file_allowed_roots": [],
    }
    config = SetuPluginConfig(**config_dict)

    assert config.napcat_stream_mode == "always"
    assert config.napcat_stream_chunk_kb == 512
    assert config.napcat_local_file_mode == "fallback"
    assert config.napcat_local_file_allowed_roots == ["/AstrBot/data"]


def test_delivery_legacy_napcat_fields_remain_supported(sample_config_dict) -> None:
    config_dict = sample_config_dict.copy()
    config_dict["delivery"] = {
        **sample_config_dict["delivery"],
        "napcat_stream_mode": "disabled",
        "napcat_stream_chunk_kb": 256,
        "napcat_local_file_mode": "always",
        "napcat_local_file_allowed_roots": ["/legacy/shared"],
    }
    config = SetuPluginConfig(**config_dict)

    assert config.napcat_stream_mode == "disabled"
    assert config.napcat_stream_chunk_kb == 256
    assert config.napcat_local_file_mode == "always"
    assert config.napcat_local_file_allowed_roots == ["/legacy/shared"]


def test_sexnyan_provider_template_override(sample_config_dict) -> None:
    config_dict = sample_config_dict.copy()
    config_dict["api"] = {
        **sample_config_dict["api"],
        "provider_overrides": [
            {
                "__template_key": "sexnyan",
                "proxy": "pixiv-proxy.example.com",
                "uid": [1001, 1002],
                "keyword": "blue",
            }
        ],
    }
    config = SetuPluginConfig(**config_dict)

    assert config.sexnyan_proxy == "pixiv-proxy.example.com"
    assert config.sexnyan_uid == [1001, 1002]
    assert config.sexnyan_keyword == "blue"


def test_exclude_ai_uses_atri_override_when_api_type_is_atri(
    sample_config_dict,
) -> None:
    config_dict = sample_config_dict.copy()
    config_dict["setu_general"] = {
        **sample_config_dict["setu_general"],
        "api_type": "atri",
    }
    config_dict["api"] = {
        **sample_config_dict["api"],
        "provider_overrides": [
            {
                "__template_key": "lolicon",
                "image_size": "original",
                "proxy": "",
                "aspect_ratio": "",
                "uid": [],
                "keyword": "",
                "exclude_ai": True,
            },
            {
                "__template_key": "atri",
                "image_size": "original",
                "proxy": "",
                "aspect_ratio": "",
                "uid": [],
                "keyword": "",
                "exclude_ai": False,
            },
        ],
    }
    config = SetuPluginConfig(**config_dict)

    assert config.exclude_ai is False


def test_tag_alias_templates_override_text_default(sample_config_dict) -> None:
    config_dict = sample_config_dict.copy()
    config_dict["setu_general"] = {
        **sample_config_dict["setu_general"],
        "tag_alias_templates": [
            {
                "__template_key": "alias",
                "canonical": "少女",
                "aliases": ["girl", "girls"],
            }
        ],
    }
    config = SetuPluginConfig(**config_dict)

    assert config.tag_alias == "少女=girl,girls"


def test_legacy_auto_handle_send_failure_is_ignored(sample_config_dict) -> None:
    config_dict = sample_config_dict.copy()
    config_dict["delivery"] = {
        **sample_config_dict["delivery"],
        "auto_handle_send_failure": False,
    }

    config = SetuPluginConfig(**config_dict)

    assert not hasattr(config.delivery, "auto_handle_send_failure")
