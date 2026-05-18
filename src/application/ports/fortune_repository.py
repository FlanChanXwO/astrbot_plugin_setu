"""Application port for fortune persistence."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ...domain.fortune.entities import FortuneGenerationRequest, FortuneRecord


class FortuneRepository(ABC):
    """Repository interface for fortune data."""

    @abstractmethod
    async def get_today_fortune(
        self, request: FortuneGenerationRequest
    ) -> FortuneRecord | None:
        """Get fortune for today."""
        ...

    @abstractmethod
    async def save_fortune(self, record: FortuneRecord) -> bool:
        """Save or update fortune record."""
        ...

    @abstractmethod
    async def delete_fortune(self, user_id: str, date_str: str) -> bool:
        """Delete a fortune record."""
        ...

    @abstractmethod
    async def delete_group_fortunes(self, group_id: str, date_str: str) -> int:
        """Delete all fortune records for a group on a date."""
        ...

    @abstractmethod
    async def delete_all_fortunes(self, date_str: str) -> int:
        """Delete all fortune records for a date."""
        ...

    @abstractmethod
    async def get_active_users(self, days: int = 3) -> list[str]:
        """Get active user IDs."""
        ...

    @abstractmethod
    async def get_active_fortune_requests(
        self, days: int = 3, date_str: str | None = None
    ) -> list[FortuneGenerationRequest]:
        """Get generation requests for users active within N days."""
        ...

    @abstractmethod
    async def get_cached_image_path(self, user_id: str, date_str: str) -> Any | None:
        """Get cached image path."""
        ...

    @abstractmethod
    async def save_cached_image(
        self, user_id: str, date_str: str, image_data: bytes, img_url: str | None
    ) -> Any:
        """Save cached image data."""
        ...

    @abstractmethod
    async def delete_cached_image(self, user_id: str, date_str: str) -> bool:
        """Delete cached image."""
        ...

    @abstractmethod
    async def cleanup_expired_cache(self, date_str: str) -> int:
        """Clean expired cache files."""
        ...
