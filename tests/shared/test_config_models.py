from __future__ import annotations

from astrbot_plugin_setu.src.shared.config import SetuPluginConfig


def test_provider_config_accepts_empty_aspect_ratio(sample_config_dict) -> None:
    config = SetuPluginConfig(**sample_config_dict)

    assert config.api.lolicon.aspect_ratio is None
    assert config.api.atri.aspect_ratio is None
