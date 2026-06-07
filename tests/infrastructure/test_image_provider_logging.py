from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from astrbot_plugin_setu.src.infrastructure.providers import (
    base as provider_base_module,
)
from astrbot_plugin_setu.src.infrastructure.providers.base import (
    DownloadingSetuImageProvider,
)
from astrbot_plugin_setu.src.domain.setu import SetuRequest


class DummyProvider(DownloadingSetuImageProvider):
    async def fetch_image_urls(
        self,
        num: int,
        tags: list[str],
        r18: bool,
        exclude_ai: bool = True,
    ) -> list[str]:
        return ["https://example.com/a.jpg"]


@pytest.mark.asyncio
async def test_fetch_and_download_logs_when_all_downloads_fail(monkeypatch) -> None:
    provider = DummyProvider()
    request = SetuRequest.from_user_input(
        count=1, tags=["cat"], r18=False, exclude_ai=True, max_replenish_rounds=2
    )
    fake_logger = MagicMock()
    monkeypatch.setattr(provider_base_module, "logger", fake_logger)

    async def fail_get(_self, url: str):
        raise httpx.ConnectError("boom", request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", fail_get)

    payload = await provider.fetch_and_download(request)

    assert payload.items == ()
    warning_messages = [call.args[0] for call in fake_logger.warning.call_args_list]
    error_messages = [call.args[0] for call in fake_logger.error.call_args_list]
    assert any(
        "[provider] transient download failed, will retry:" in message
        for message in warning_messages
    )
    assert any("[provider] download failed:" in message for message in warning_messages)
    assert any(
        "[provider] all downloads failed:" in message for message in error_messages
    )


@pytest.mark.asyncio
async def test_fetch_and_download_retries_transient_download_failure(
    monkeypatch,
) -> None:
    provider = DummyProvider()
    request = SetuRequest.from_user_input(
        count=1, tags=["cat"], r18=False, exclude_ai=True, max_replenish_rounds=2
    )
    calls = 0

    async def flaky_get(_self, url: str):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ConnectError("temporary", request=httpx.Request("GET", url))
        return httpx.Response(
            200,
            content=b"image-data",
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", flaky_get)

    payload = await provider.fetch_and_download(request)

    assert payload.items == (b"image-data",)
    assert calls == 2


@pytest.mark.asyncio
async def test_download_returns_bytes_without_writing_when_cache_disabled(
    monkeypatch,
) -> None:
    provider = DummyProvider()
    fake_cache = MagicMock()
    fake_cache.enabled = False
    fake_cache.get = AsyncMock()
    fake_cache.reserve = AsyncMock()
    fake_cache.commit = AsyncMock()
    fake_cache.discard = AsyncMock()
    monkeypatch.setattr(provider_base_module, "get_send_cache", lambda: fake_cache)

    class FakeResponse:
        def __init__(self) -> None:
            self.headers: dict[str, str] = {}

        def raise_for_status(self) -> None:
            return None

        async def aiter_bytes(self):
            yield b"image-"
            yield b"data"

    class FakeStream:
        async def __aenter__(self) -> FakeResponse:
            return FakeResponse()

        async def __aexit__(self, *args) -> None:
            return None

    class FakeClient:
        def stream(self, method: str, url: str) -> FakeStream:
            assert method == "GET"
            assert url == "https://example.com/a.jpg"
            return FakeStream()

    item = await provider._download_one_attempt(
        FakeClient(), "https://example.com/a.jpg", attempt=1, max_attempts=1
    )

    assert item == b"image-data"
    fake_cache.get.assert_not_awaited()
    fake_cache.reserve.assert_not_awaited()
    fake_cache.commit.assert_not_awaited()
    fake_cache.discard.assert_not_awaited()
