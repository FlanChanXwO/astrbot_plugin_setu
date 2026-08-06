from __future__ import annotations

from pathlib import Path

import astrbot.api.message_components as Comp

from astrbot_plugin_setu.src.infrastructure.doujinshi import (
    DoujinshiGallery,
    GeneratedDoujinshiPdf,
)
from astrbot_plugin_setu.src.infrastructure.sending import build_doujinshi_file_chain


def _generated_pdf(tmp_path: Path) -> GeneratedDoujinshiPdf:
    return GeneratedDoujinshiPdf(
        gallery=DoujinshiGallery(
            id=123,
            title="测试本子",
            page_urls=("https://example.com/1.jpg",),
        ),
        path=tmp_path / "doujinshi-123.pdf",
    )


def test_onebot_uses_file_inside_merged_forward_node(tmp_path: Path) -> None:
    chain = build_doujinshi_file_chain(
        _generated_pdf(tmp_path), platform_name="aiocqhttp", self_id="10001"
    )

    assert len(chain) == 1
    assert isinstance(chain[0], Comp.Nodes)
    assert len(chain[0].nodes) == 1
    node = chain[0].nodes[0]
    assert node.name == "测试本子"
    assert node.uin == "10001"
    assert isinstance(node.content[0], Comp.File)
    assert node.content[0].name == "测试本子.pdf"


def test_non_onebot_sends_direct_file(tmp_path: Path) -> None:
    chain = build_doujinshi_file_chain(
        _generated_pdf(tmp_path), platform_name="telegram", self_id="10001"
    )

    assert len(chain) == 1
    assert isinstance(chain[0], Comp.File)
    assert chain[0].file_ == str(tmp_path / "doujinshi-123.pdf")
    assert chain[0].name == "测试本子.pdf"


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

    chain = build_doujinshi_file_chain(
        generated, platform_name="aiocqhttp", self_id="10001"
    )

    assert chain[0].nodes[0].content[0].name == "测试_本子.pdf"
