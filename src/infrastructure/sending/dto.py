"""Infrastructure DTOs for sending strategies."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Iterable


@dataclass(frozen=True)
class SendOptions:
    """Value object for send strategy options."""

    send_mode: str
    use_html_card: bool
    auto_revoke: bool
    revoke_delay: int
    r18_docx_mode: bool
    auto_revoke_scope: str = "none"
    html_padding: int = 6
    html_gap: int = 6
    html_card_strategy: str = "fallback"
    napcat_stream_mode: str = "fallback"
    napcat_stream_chunk_kb: int = 64
    napcat_local_file_mode: str = "disabled"
    napcat_local_file_allowed_roots: tuple[str, ...] = ()
    compress_enabled: bool = False
    compress_max_mb: int = 4


@dataclass(frozen=True)
class SendAttemptResult:
    """单次发送尝试的结果，区分确认失败和平台确认超时。"""

    accepted: bool
    pending: bool = False
    reason: str = ""
    message_ids: tuple[str, ...] = ()

    @classmethod
    def success(cls, message_ids: Iterable[str] = ()) -> "SendAttemptResult":
        """发送链路已确认成功。"""
        return cls(accepted=True, message_ids=tuple(str(item) for item in message_ids))

    @classmethod
    def pending_delivery(
        cls, reason: str, message_ids: Iterable[str] = ()
    ) -> "SendAttemptResult":
        """平台侧可能已接收，但本地未拿到最终确认。"""
        return cls(
            accepted=True,
            pending=True,
            reason=reason,
            message_ids=tuple(str(item) for item in message_ids),
        )

    @classmethod
    def failed(cls, reason: str = "") -> "SendAttemptResult":
        """发送链路已确认失败，可以进入后续 fallback。"""
        return cls(accepted=False, reason=reason)
