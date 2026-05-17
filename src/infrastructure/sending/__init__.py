"""Sending layer — image sending strategies and implementations."""

from __future__ import annotations

from .dto import SendOptions
from .image_sender import ImageSender
from .send_filters import (
    SendFilter,
    SendResult,
    direct_send_filter,
    forward_send_filter,
    html_card_filter,
    send_with_filter_chain,
)
from .send_strategies import (
    DirectSendStrategy,
    ForwardSendStrategy,
    HtmlCardFallbackStrategy,
    resolve_send_mode,
)

__all__ = [
    "ImageSender",
    "DirectSendStrategy",
    "ForwardSendStrategy",
    "HtmlCardFallbackStrategy",
    "SendOptions",
    "resolve_send_mode",
    # Filter chain (new)
    "send_with_filter_chain",
    "SendResult",
    "SendFilter",
    "direct_send_filter",
    "forward_send_filter",
    "html_card_filter",
]
