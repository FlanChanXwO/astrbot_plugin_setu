"""Sending layer — image sending strategies and implementations."""

from __future__ import annotations

from .dto import SendOptions
from .doujinshi_sender import build_doujinshi_file_chain, get_doujinshi_file_name
from .image_sender import ImageSender
from .revoke_scheduler import (
    get_revoke_scheduler,
    init_revoke_scheduler,
    schedule_revoke,
    stop_revoke_scheduler,
)
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
    "schedule_revoke",
    "get_revoke_scheduler",
    "init_revoke_scheduler",
    "stop_revoke_scheduler",
    "resolve_send_mode",
    "build_doujinshi_file_chain",
    "get_doujinshi_file_name",
    # Filter chain (new)
    "send_with_filter_chain",
    "SendResult",
    "SendFilter",
    "direct_send_filter",
    "forward_send_filter",
    "html_card_filter",
]
