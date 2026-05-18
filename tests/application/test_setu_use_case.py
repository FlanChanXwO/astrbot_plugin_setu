from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot_plugin_setu.src.application.setu.dto import ImagePayload
from astrbot_plugin_setu.src.application.setu.get_images import GetSetuImagesUseCase


@pytest.mark.asyncio
async def test_execute_returns_empty_payload_without_hardcoded_notice() -> None:
    provider = MagicMock()
    provider.fetch_and_download = AsyncMock(
        return_value=ImagePayload(
            urls=(),
            raw_bytes=(),
            file_paths=(),
            items=(),
            r18=False,
            tags=(),
        )
    )

    use_case = GetSetuImagesUseCase(provider)
    result = await use_case.execute(1, ["少女"], False)

    assert result.payload is None
    assert result.notice is None


@pytest.mark.asyncio
async def test_execute_returns_payload_when_non_empty() -> None:
    payload = ImagePayload(
        urls=("https://example.com/1.jpg",),
        raw_bytes=(),
        file_paths=(),
        items=(),
        r18=False,
        tags=("少女",),
    )
    provider = MagicMock()
    provider.fetch_and_download = AsyncMock(return_value=payload)

    use_case = GetSetuImagesUseCase(provider)
    result = await use_case.execute(1, ["少女"], False)

    assert result.payload == payload
    assert result.notice is None
