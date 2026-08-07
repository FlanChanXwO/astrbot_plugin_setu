from __future__ import annotations

from pathlib import Path

import astrbot.api.message_components as Comp

from astrbot_plugin_setu.src.infrastructure.doujinshi import (
    DoujinshiGallery,
    GeneratedDoujinshiPdf,
)
from astrbot_plugin_setu.src.infrastructure.sending import build_doujinshi_file_chain


def _generated_pdf(
    tmp_path: Path,
    *,
    upstream_title: str | None = "测试本子",
    source_url: str | None = "https://example.com/galleries/123",
) -> GeneratedDoujinshiPdf:
    return GeneratedDoujinshiPdf(
        gallery=DoujinshiGallery(
            id=123,
            title="测试本子",
            page_urls=("https://example.com/1.jpg",),
            upstream_title=upstream_title,
            source_url=source_url,
        ),
        path=tmp_path / "doujinshi-123.pdf",
    )


def test_all_platforms_send_pdf_as_a_direct_file(tmp_path: Path) -> None:
    chain = build_doujinshi_file_chain(_generated_pdf(tmp_path))

    assert len(chain) == 1
    assert isinstance(chain[0], Comp.File)
    assert chain[0].file_ == str(tmp_path / "doujinshi-123.pdf")
    assert chain[0].name == "测试本子.pdf"


def test_archive_mode_uses_zip_file_name(tmp_path: Path) -> None:
    generated = GeneratedDoujinshiPdf(
        gallery=DoujinshiGallery(
            id=123,
            title="测试本子",
            page_urls=("https://example.com/1.jpg",),
        ),
        path=tmp_path / "doujinshi-123.zip",
        mode="archive",
    )

    chain = build_doujinshi_file_chain(generated)

    assert isinstance(chain[0], Comp.File)
    assert chain[0].file_ == str(tmp_path / "doujinshi-123.zip")
    assert chain[0].name == "测试本子.zip"


def test_file_name_sanitizes_path_characters_but_keeps_title(
    tmp_path: Path,
) -> None:
    generated = GeneratedDoujinshiPdf(
        gallery=DoujinshiGallery(
            id=123,
            title="测试/本子",
            page_urls=("https://example.com/1.jpg",),
        ),
        path=tmp_path / "doujinshi-123.pdf",
    )

    chain = build_doujinshi_file_chain(generated)

    assert chain[0].name == "测试_本子.pdf"
