from __future__ import annotations

from astrbot_plugin_setu.src.shared.config import SetuPluginConfig


def test_provider_config_accepts_empty_aspect_ratio(sample_config_dict) -> None:
    config = SetuPluginConfig(**sample_config_dict)

    assert config.aspect_ratio == ""
    assert config.atri_aspect_ratio == ""


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


def test_resolve_message_supports_dotted_builtin_error_keys(
    sample_config_dict,
) -> None:
    config = SetuPluginConfig(**sample_config_dict)

    assert config.resolve_message("error.invalid_request") == "请求参数无效"
    assert config.resolve_message("error.internal_server") == "服务器内部错误"


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
