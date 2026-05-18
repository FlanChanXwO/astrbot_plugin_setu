"""Use case for fetching Setu images."""

from __future__ import annotations

import asyncio

from ...domain.setu import SetuRequest
from ..ports import ImageProvider
from ..settings import get_setu_settings
from .dto import SetuImagesResult


class GetSetuImagesUseCase:
    """Fetch Setu image data without knowing how a chat platform will send it."""

    def __init__(self, image_provider: ImageProvider) -> None:
        self._provider = image_provider

    async def execute(self, count: int, tags: list[str], r18: bool) -> SetuImagesResult:
        """Fetch image files according to current settings."""
        settings = get_setu_settings()
        request = SetuRequest.from_user_input(
            count=count,
            tags=tags,
            r18=r18,
            exclude_ai=settings.exclude_ai,
        )

        payload = await asyncio.wait_for(
            self._provider.fetch_and_download(request),
            timeout=settings.fetch_timeout_seconds,
        )

        if payload.is_empty:
            return SetuImagesResult(payload=None)
        return SetuImagesResult(payload=payload)
