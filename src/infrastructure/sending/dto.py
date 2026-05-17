"""Infrastructure DTOs for sending strategies."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SendOptions:
    """Value object for send strategy options."""

    send_mode: str
    use_html_card: bool
    auto_revoke: bool
    revoke_delay: int
    r18_docx_mode: bool
    html_padding: int = 6
    html_gap: int = 6
    html_card_strategy: str = "fallback"
    napcat_stream_mode: str = "fallback"
