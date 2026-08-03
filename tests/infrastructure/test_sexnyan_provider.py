from __future__ import annotations

from typing import Any

import httpx
import pytest
from astrbot_plugin_setu.src.infrastructure.providers.sexnyan import SexNyanRunProvider


@pytest.mark.asyncio
async def test_sexnyan_provider_uses_supported_filter_params(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_get(
        self, url: str, params: list[tuple[str, str | int]]
    ) -> httpx.Response:
        captured["url"] = url
        captured["params"] = params
        request = httpx.Request("GET", url, params=params)
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "url": (
                            "https://i.pximg.net/img-original/img/2026/01/01/"
                            "00/00/00/1_p0.jpg"
                        )
                    }
                ]
            },
            request=request,
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    provider = SexNyanRunProvider(
        proxy="pixiv-proxy.example.com",
        uid=[1001, 1002],
        keyword="blue",
    )

    urls = await provider.fetch_image_urls(
        num=2,
        tags=["tag-a", "tag-b"],
        r18=True,
    )

    assert captured["url"] == SexNyanRunProvider.API_URL
    assert ("r18", "true") in captured["params"]
    assert ("num", 2) in captured["params"]
    assert ("author_uuid", 1001) in captured["params"]
    assert ("author_uuid", 1002) in captured["params"]
    assert ("keyword", "blue") in captured["params"]
    assert ("tag", "tag-a") in captured["params"]
    assert ("tag", "tag-b") in captured["params"]
    assert urls == [
        "https://pixiv-proxy.example.com/img-original/img/2026/01/01/00/00/00/1_p0.jpg"
    ]
