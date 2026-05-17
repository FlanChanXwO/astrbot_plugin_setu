"""Access-control domain value objects."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AccessPolicy:
    """Value object for access-control policy."""

    user_id: str | None
    group_id: str | None
    user_mode: str
    group_mode: str

    @classmethod
    def for_user(cls, user_id: str, user_mode: str = "none") -> AccessPolicy:
        """Create policy for user-only access control."""
        return cls(user_id, None, user_mode, "none")

    @classmethod
    def for_group(cls, group_id: str, group_mode: str = "none") -> AccessPolicy:
        """Create policy for group-only access control."""
        return cls(None, group_id, "none", group_mode)

    @classmethod
    def for_session(
        cls,
        user_id: str | None,
        group_id: str | None,
        user_mode: str = "none",
        group_mode: str = "none",
    ) -> AccessPolicy:
        """Create policy for full session access control."""
        return cls(user_id, group_id, user_mode, group_mode)
