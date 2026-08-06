from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path

import httpx
import pytest
from PIL import Image

from astrbot_plugin_setu.src.infrastructure.doujinshi.service import (
    DoujinshiService,
)


def test_parse_gallery_returns_title_and_all_page_urls() -> None:
    payload = {
        "id": 493454,
        "title": {
            "english": "English title",
            "japanese": "日本語タイトル",
            "pretty": "Pretty title",
        },
        "pages": [
            {"url": "https://example.com/1.jpg", "width": 1280, "height": 1785},
            {"url": "https://example.com/2.jpg", "width": 1280, "height": 1785},
        ],
    }

    gallery = DoujinshiService.parse_gallery(payload)

    assert gallery.id == 493454
    assert gallery.title == "Pretty title"
    assert gallery.page_urls == (
        "https://example.com/1.jpg",
        "https://example.com/2.jpg",
    )


def test_parse_gallery_rejects_response_without_downloadable_pages() -> None:
    payload = {"id": 493454, "title": {"pretty": "Empty"}, "pages": []}

    try:
        DoujinshiService.parse_gallery(payload)
    except ValueError as exc:
        assert "页图" in str(exc)
    else:
        raise AssertionError("缺少页图的响应必须失败")


def test_create_pdf_preserves_every_downloaded_page(tmp_path: Path) -> None:
    page_one = Image.new("RGB", (24, 36), "red")
    page_two = Image.new("RGB", (36, 24), "blue")
    output_path = tmp_path / "gallery.pdf"

    DoujinshiService.create_pdf([page_one, page_two], output_path, "测试本子")

    pdf_bytes = output_path.read_bytes()
    assert pdf_bytes.startswith(b"%PDF-")
    assert len(re.findall(rb"/Type\s*/Page\b", pdf_bytes)) == 2


@pytest.mark.asyncio
async def test_fetch_random_pdf_downloads_all_api_pages_in_order(
    tmp_path: Path,
) -> None:
    first_page = _image_bytes("red")
    second_page = _image_bytes("blue")

    def responder(request: httpx.Request) -> httpx.Response:
        if request.url == httpx.URL(DoujinshiService.API_URL):
            assert request.headers["sec-fetch-dest"] == "empty"
            assert "astrbot-plugin-setu" in request.headers["user-agent"]
            return httpx.Response(
                200,
                json={
                    "id": 493454,
                    "title": {"pretty": "测试本子"},
                    "pages": [
                        {"url": "https://example.com/1.jpg"},
                        {"url": "https://example.com/2.jpg"},
                    ],
                },
            )
        if request.url == httpx.URL("https://example.com/1.jpg"):
            return httpx.Response(200, content=first_page)
        if request.url == httpx.URL("https://example.com/2.jpg"):
            return httpx.Response(200, content=second_page)
        raise AssertionError(f"未预期的请求：{request.url}")

    async with httpx.AsyncClient(transport=httpx.MockTransport(responder)) as client:
        generated = await DoujinshiService(tmp_path).fetch_random_pdf(client=client)

    assert generated.gallery.id == 493454
    assert generated.gallery.title == "测试本子"
    assert generated.path.parent == tmp_path / "doujinshi"
    pdf_bytes = generated.path.read_bytes()
    assert len(re.findall(rb"/Type\s*/Page\b", pdf_bytes)) == 2


@pytest.mark.asyncio
async def test_fetch_random_pdf_repeats_resolved_tags_in_api_request(
    tmp_path: Path,
) -> None:
    page = _image_bytes("red")

    def responder(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/doujinshi/random":
            assert request.url.params.get_list("tag") == ["碧蓝档案", "白丝"]
            return httpx.Response(
                200,
                json={
                    "id": 493454,
                    "title": {"pretty": "测试本子"},
                    "pages": [{"url": "https://example.com/1.jpg"}],
                },
            )
        if request.url == httpx.URL("https://example.com/1.jpg"):
            return httpx.Response(200, content=page)
        raise AssertionError(f"未预期的请求：{request.url}")

    async with httpx.AsyncClient(transport=httpx.MockTransport(responder)) as client:
        generated = await DoujinshiService(tmp_path).fetch_random_pdf(
            tags=["碧蓝档案", "白丝"], client=client
        )

    assert generated.gallery.id == 493454


def _image_bytes(color: str) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (24, 36), color).save(buffer, format="PNG")
    return buffer.getvalue()
