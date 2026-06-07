from __future__ import annotations

from astrbot_plugin_setu.src.infrastructure.sending.platform_capabilities import (
    is_onebot_like_platform,
    supports_forward_messages,
)


def test_onebot12_is_not_treated_as_onebot11_like() -> None:
    assert is_onebot_like_platform("onebot12") is False
    assert supports_forward_messages("onebot12") is False


def test_explicit_onebot11_and_napcat_are_supported() -> None:
    assert supports_forward_messages("onebot11") is True
    assert supports_forward_messages("napcat") is True
