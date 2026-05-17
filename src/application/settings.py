"""Read-only settings facade for application code.

Infrastructure owns the full AstrBot/Pydantic config object. Application code reads
small settings snapshots so it does not reach into the full runtime config tree.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..shared.config import SetuPluginConfig


@dataclass(frozen=True)
class SetuSettings:
    """Settings needed by Setu use cases."""

    max_count: int
    content_mode: str
    exclude_ai: bool
    fetch_timeout_seconds: float = 60.0


@dataclass(frozen=True)
class DeliverySettings:
    """Settings needed by adapter-level delivery."""

    send_mode: str
    html_card_strategy: str
    auto_revoke_r18: bool
    auto_revoke_delay: int
    r18_docx_mode: bool
    html_card_padding: int
    html_card_gap: int
    napcat_stream_mode: str


@dataclass(frozen=True)
class FortuneSettings:
    """Settings needed by fortune use cases."""

    enabled: bool
    content_mode: str
    tags: str
    allow_user_refresh: bool
    auto_refresh: bool


_config: SetuPluginConfig | None = None


def set_application_config(config: SetuPluginConfig) -> None:
    """Set the config snapshot used by application settings getters."""
    global _config
    _config = config


def clear_application_config() -> None:
    """Clear application config for tests and plugin shutdown."""
    global _config
    _config = None


def get_setu_settings() -> SetuSettings:
    """Return Setu settings from the current config snapshot."""
    if _config is None:
        return SetuSettings(
            max_count=10,
            content_mode="sfw",
            exclude_ai=True,
        )
    return SetuSettings(
        max_count=_config.max_count,
        content_mode=_config.content_mode,
        exclude_ai=_config.exclude_ai,
    )


def get_delivery_settings() -> DeliverySettings:
    """Return delivery settings from the current config snapshot."""
    if _config is None:
        return DeliverySettings(
            send_mode="image",
            html_card_strategy="never",
            auto_revoke_r18=False,
            auto_revoke_delay=30,
            r18_docx_mode=False,
            html_card_padding=6,
            html_card_gap=6,
            napcat_stream_mode="fallback",
        )
    return DeliverySettings(
        send_mode=_config.send_mode,
        html_card_strategy=_config.html_card_strategy,
        auto_revoke_r18=_config.auto_revoke_r18,
        auto_revoke_delay=_config.auto_revoke_delay,
        r18_docx_mode=_config.r18_docx_mode,
        html_card_padding=_config.html_card_padding,
        html_card_gap=_config.html_card_gap,
        napcat_stream_mode=_config.napcat_stream_mode,
    )


def get_fortune_settings() -> FortuneSettings:
    """Return fortune settings from the current config snapshot."""
    if _config is None:
        return FortuneSettings(
            enabled=True,
            content_mode="sfw",
            tags="",
            allow_user_refresh=False,
            auto_refresh=True,
        )
    return FortuneSettings(
        enabled=_config.fortune.enabled,
        content_mode=_config.fortune.content_mode.value,
        tags=_config.fortune.tags,
        allow_user_refresh=_config.fortune.allow_user_refresh,
        auto_refresh=_config.fortune.auto_refresh,
    )
