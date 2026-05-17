"""Application port for session configuration persistence."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..session_config.dto import SessionConfigRecord


class SessionConfigRepository(ABC):
    """Repository interface for session-scoped config overrides."""

    @abstractmethod
    async def list_sessions(self) -> list[SessionConfigRecord]:
        """List all stored session records."""
        ...

    @abstractmethod
    async def get_session(self, session_id: str) -> SessionConfigRecord | None:
        """Get a session record by ID."""
        ...

    @abstractmethod
    async def upsert_session(self, record: SessionConfigRecord) -> SessionConfigRecord:
        """Create or replace a session record."""
        ...

    @abstractmethod
    async def delete_session(self, session_id: str) -> bool:
        """Delete a session record."""
        ...
