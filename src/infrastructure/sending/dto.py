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


@dataclass(frozen=True)
class SendAttemptResult:
    """单次发送尝试的结果，区分确认失败和平台确认超时。"""

    accepted: bool
    pending: bool = False
    reason: str = ""

    @classmethod
    def success(cls) -> "SendAttemptResult":
        """发送链路已确认成功。"""
        return cls(accepted=True)

    @classmethod
    def pending_delivery(cls, reason: str) -> "SendAttemptResult":
        """平台侧可能已接收，但本地未拿到最终确认。"""
        return cls(accepted=True, pending=True, reason=reason)

    @classmethod
    def failed(cls, reason: str = "") -> "SendAttemptResult":
        """发送链路已确认失败，可以进入后续 fallback。"""
        return cls(accepted=False, reason=reason)
