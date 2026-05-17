from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest

from astrbot_plugin_setu.src.application.ports import (
    image_provider as image_provider_module,
)
from astrbot_plugin_setu.src.application.ports.image_provider import SetuImageProvider
from astrbot_plugin_setu.src.domain.setu import SetuRequest


class DummyProvider(SetuImageProvider):
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
        count=1, tags=["cat"], r18=False, exclude_ai=True
    )
    fake_logger = MagicMock()
    monkeypatch.setattr(image_provider_module, "logger", fake_logger)

    async def fail_get(_self, url: str):
        raise httpx.ConnectError("boom", request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", fail_get)

    payload = await provider.fetch_and_download(request)

    assert payload.items == ()
    warning_messages = [call.args[0] for call in fake_logger.warning.call_args_list]
    error_messages = [call.args[0] for call in fake_logger.error.call_args_list]
    assert any("[provider] download failed:" in message for message in warning_messages)
    assert any(
        "[provider] all downloads failed:" in message for message in error_messages
    )
