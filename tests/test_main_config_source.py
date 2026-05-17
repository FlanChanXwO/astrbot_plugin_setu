from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot_plugin_setu.main import SetuPlugin


@pytest.mark.asyncio
async def test_initialize_uses_plugin_config_not_context_config(
    monkeypatch, sample_config_dict
) -> None:
    context = MagicMock()
    context.get_config.return_value = {"api": {"lolicon": {"proxy": "wrong.example.com"}}}
    config = MagicMock()
    config.items.return_value = sample_config_dict.items()

    plugin = SetuPlugin(context, config)
    plugin.name = "astrbot_plugin_setu"

    captured: dict[str, object] = {}

    def fake_init_config(raw_config):
        captured["raw_config"] = raw_config
        return MagicMock(
            api_type="lolicon",
            custom_api_configs=[],
            multi_api_strategy="round_robin",
            proxy=raw_config["api"]["lolicon"]["proxy"],
            image_size="original",
            aspect_ratio="",
            uid=[],
            keyword="",
            atri_proxy=raw_config["api"]["atri"]["proxy"],
            atri_image_size="original",
            atri_aspect_ratio="",
            atri_uid=[],
            atri_keyword="",
            cache_enabled=True,
            cache_ttl_hours=2,
            cache_max_items=200,
            cache_cleanup_on_start=True,
        )

    monkeypatch.setattr("astrbot_plugin_setu.main.init_config", fake_init_config)
    monkeypatch.setattr("astrbot_plugin_setu.main.set_plugin_context", lambda _ctx: None)
    monkeypatch.setattr("astrbot_plugin_setu.main.StarTools.get_data_dir", lambda _name: "/tmp")
    monkeypatch.setattr("astrbot_plugin_setu.main.init_provider_from_config", lambda _cfg: None)
    monkeypatch.setattr("astrbot_plugin_setu.main.init_access_control_repo", AsyncMock())
    monkeypatch.setattr("astrbot_plugin_setu.main.init_fortune_repo", AsyncMock())
    monkeypatch.setattr("astrbot_plugin_setu.main.init_session_config_repo", AsyncMock())
    monkeypatch.setattr("astrbot_plugin_setu.main.init_send_cache", AsyncMock())
    monkeypatch.setattr("astrbot_plugin_setu.main.register_setu_llm_tools", lambda: None)
    monkeypatch.setattr("astrbot_plugin_setu.main.register_fortune_llm_tools", lambda: None)
    monkeypatch.setattr("astrbot_plugin_setu.main.register_session_config_llm_tools", lambda: None)

    await plugin.initialize()

    assert captured["raw_config"]["api"]["lolicon"]["proxy"] == sample_config_dict["api"]["lolicon"]["proxy"]
