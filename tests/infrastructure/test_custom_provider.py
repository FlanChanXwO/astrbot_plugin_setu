from __future__ import annotations

import pytest

from astrbot_plugin_setu.src.infrastructure.providers.custom import CustomApiProvider


async def _raise_value_error(*args, **kwargs):
    raise ValueError("blocked url")


@pytest.mark.asyncio
async def test_custom_provider_returns_empty_list_when_url_validation_fails(
    monkeypatch,
) -> None:
    provider = CustomApiProvider({"url": "http://127.0.0.1/image"})
    monkeypatch.setattr(provider, "_build_url", _raise_value_error)

    urls = await provider.fetch_image_urls(num=1, tags=[], r18=False)

    assert urls == []
