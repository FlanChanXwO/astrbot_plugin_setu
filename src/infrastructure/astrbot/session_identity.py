"""Helpers for mapping AstrBot events to session config identities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class SessionIdentity:
    """Normalized AstrBot session identity."""

    session_id: str
    session_type: str
    display_name: str


def get_event_session_identity(event: Any) -> SessionIdentity:
    """Return the session identity used by per-session config."""
    session_id = _call_or_attr(event, "unified_msg_origin")
    if not session_id:
        session_id = _call_or_attr(event, "get_session_id")
    if not session_id:
        raise ValueError("无法获取当前会话 ID")

    group_id = _call_or_attr(event, "get_group_id")
    sender_id = _call_or_attr(event, "get_sender_id")
    session_type = "group" if group_id else "private"
    display_name = str(group_id or sender_id or session_id)
    return SessionIdentity(
        session_id=str(session_id),
        session_type=session_type,
        display_name=display_name,
    )


def _call_or_attr(obj: Any, name: str) -> Any:
    value = getattr(obj, name, None)
    if callable(value):
        return value()
    return value
