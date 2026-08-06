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


def test_onebot_uses_file_and_upstream_metadata_inside_merged_forward_node(
    tmp_path: Path,
) -> None:
    chain = build_doujinshi_file_chain(
        _generated_pdf(tmp_path), platform_name="aiocqhttp", self_id="10001"
    )

    assert len(chain) == 1
    assert isinstance(chain[0], Comp.Nodes)
    assert len(chain[0].nodes) == 3
    file_node, title_node, url_node = chain[0].nodes
    assert file_node.name == "测试本子"
    assert file_node.uin == "10001"
    assert isinstance(file_node.content[0], Comp.File)
    assert file_node.content[0].name == "测试本子.pdf"
    assert title_node.name == "标题"
    assert title_node.uin == "10001"
    assert isinstance(title_node.content[0], Comp.Plain)
    assert title_node.content[0].text == "测试本子"
    assert url_node.name == "原始地址"
    assert url_node.uin == "10001"
    assert isinstance(url_node.content[0], Comp.Plain)
    assert url_node.content[0].text == "https://example.com/galleries/123"


def test_onebot_omits_metadata_nodes_missing_from_upstream(tmp_path: Path) -> None:
    chain = build_doujinshi_file_chain(
        _generated_pdf(tmp_path, upstream_title=None, source_url=None),
        platform_name="aiocqhttp",
        self_id="10001",
    )

    assert len(chain[0].nodes) == 1


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
