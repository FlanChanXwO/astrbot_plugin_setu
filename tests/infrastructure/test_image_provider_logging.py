from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from astrbot_plugin_setu.src.domain.setu import SetuRequest
from astrbot_plugin_setu.src.infrastructure.providers import (
    base as provider_base_module,
)
from astrbot_plugin_setu.src.infrastructure.providers.base import (
    DownloadingSetuImageProvider,
    select_replenish_urls,
)


class DummyProvider(DownloadingSetuImageProvider):
    async def fetch_image_urls(
        self,
        num: int,
        tags: list[str],
        r18: bool,
        exclude_ai: bool = True,
    ) -> list[str]:
        return ["https://example.com/a.jpg"]


def test_select_replenish_urls_prefers_unreported_candidates() -> None:
    selected, exhausted = select_replenish_urls(
        [
            "https://example.com/a.jpg",
            "https://example.com/b.jpg",
        ],
        1,
        reported_urls={"https://example.com/a.jpg"},
        completed_urls=set(),
        download_attempts={"https://example.com/a.jpg": 1},
        max_rounds=3,
    )

    assert selected == ["https://example.com/b.jpg"]
    assert exhausted == 0


def test_select_replenish_urls_uses_retry_candidates_when_no_new_url_exists() -> None:
    selected, exhausted = select_replenish_urls(
        ["https://example.com/a.jpg"],
        1,
        reported_urls={"https://example.com/a.jpg"},
        completed_urls=set(),
        download_attempts={"https://example.com/a.jpg": 1},
        max_rounds=3,
    )

    assert selected == ["https://example.com/a.jpg"]
    assert exhausted == 0


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


@pytest.mark.asyncio
async def test_fetch_and_download_keeps_requested_count_when_provider_overreturns(
    monkeypatch,
) -> None:
    """上游返回多于请求数量的 URL 时，只交付用户请求数量的图片。"""

    class OverreturningProvider(DummyProvider):
        async def fetch_image_urls(
            self,
            num: int,
            tags: list[str],
            r18: bool,
            exclude_ai: bool = True,
        ) -> list[str]:
            assert num == 1
            return [
                "https://example.com/a.jpg",
                "https://example.com/b.jpg",
            ]

    provider = OverreturningProvider()
    request = SetuRequest.from_user_input(
        count=1, tags=["cat"], r18=False, exclude_ai=True, max_replenish_rounds=1
    )

    async def fake_get(_self, url: str) -> httpx.Response:
        return httpx.Response(
            200,
            content=url.rsplit("/", 1)[-1].encode(),
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    payload = await provider.fetch_and_download(request)

    assert payload.urls == ("https://example.com/a.jpg",)
    assert payload.items == (b"a.jpg",)


@pytest.mark.asyncio
async def test_fetch_and_download_skips_reported_url_before_capping_candidates(
    monkeypatch,
) -> None:
    """候选裁剪不能让前序失败 URL 挤掉后续可用的新 URL。"""

    class RetryThenFreshProvider(DummyProvider):
        def __init__(self) -> None:
            self.calls = 0

        async def fetch_image_urls(
            self,
            num: int,
            tags: list[str],
            r18: bool,
            exclude_ai: bool = True,
        ) -> list[str]:
            assert num == 1
            self.calls += 1
            if self.calls == 1:
                return ["https://example.com/a.jpg"]
            return [
                "https://example.com/a.jpg",
                "https://example.com/b.jpg",
            ]

    provider = RetryThenFreshProvider()
    request = SetuRequest.from_user_input(
        count=1, tags=["cat"], r18=False, exclude_ai=True, max_replenish_rounds=2
    )

    async def fake_get(_self, url: str) -> httpx.Response:
        request = httpx.Request("GET", url)
        if url.endswith("/a.jpg"):
            raise httpx.ConnectError("a is unavailable", request=request)
        return httpx.Response(200, content=b"b.jpg", request=request)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    payload = await provider.fetch_and_download(request)

    assert payload.urls == ("https://example.com/a.jpg", "https://example.com/b.jpg")
    assert payload.items == (b"b.jpg",)
