from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import astrbot.api.message_components as Comp
import pytest

from astrbot_plugin_setu.src.infrastructure.astrbot.commands.setu import (
    SetuCommandHandler,
)
from astrbot_plugin_setu.src.infrastructure.doujinshi import (
    DoujinshiGallery,
    GeneratedDoujinshiPdf,
)


class _Config:
    auto_revoke_delay = 1800
    auto_revoke_doujinshi_enabled = True
    doujinshi_send_mode = "pdf"
    doujinshi_max_page = 0
    tag_alias = "碧蓝档案=blue_archive"

    def resolve_message(self, key: str, **kwargs: object) -> str:
        return {
            "doujinshi_fetching": "正在生成文件",
            "doujinshi_failed": "生成失败",
        }.get(key, "")


class _DoujinshiService:
    def __init__(self, generated: GeneratedDoujinshiPdf) -> None:
        self.generated = generated
        self.requested_tags: list[str] | None = None
        self.requested_mode: str | None = None
        self.requested_max_page: int | None = None

    async def fetch_random_file(
        self,
        tags: list[str] | None = None,
        *,
        mode: str = "pdf",
        max_page: int | None = None,
    ) -> GeneratedDoujinshiPdf:
        self.requested_tags = tags
        self.requested_mode = mode
        self.requested_max_page = max_page
        return self.generated


@pytest.mark.asyncio
async def test_random_doujinshi_command_yields_direct_pdf_file(
    tmp_path: Path, mock_event, monkeypatch: pytest.MonkeyPatch
) -> None:
    generated = GeneratedDoujinshiPdf(
        gallery=DoujinshiGallery(
            id=123,
            title="测试本子",
            page_urls=("https://example.com/1.jpg",),
        ),
        path=tmp_path / "doujinshi-123.pdf",
    )
    handler = SetuCommandHandler(tmp_path)
    service = _DoujinshiService(generated)
    handler._doujinshi_service = service
    mock_event.platform.name = "aiocqhttp"

    async def allow_access(event, config) -> tuple[bool, str]:
        return True, ""

    monkeypatch.setattr(
        "astrbot_plugin_setu.src.infrastructure.astrbot.commands.setu.get_config",
        lambda: _Config(),
    )
    monkeypatch.setattr(handler, "_check_access", allow_access)

    results = [
        result
        async for result in handler.random_doujinshi_command(
            mock_event, tags="blue_archive"
        )
    ]

    assert mock_event.plain_result.call_args.args == ("正在生成文件",)
    assert service.requested_tags == ["碧蓝档案"]
    assert service.requested_mode == "pdf"
    assert isinstance(results[-1].result_chain[0], Comp.File)


@pytest.mark.asyncio
async def test_random_doujinshi_passes_archive_mode_from_config(
    tmp_path: Path, mock_event, monkeypatch: pytest.MonkeyPatch
) -> None:
    generated = GeneratedDoujinshiPdf(
        gallery=DoujinshiGallery(
            id=123,
            title="测试本子",
            page_urls=("https://example.com/1.jpg",),
        ),
        path=tmp_path / "doujinshi-123.zip",
        mode="archive",
    )
    service = _DoujinshiService(generated)
    handler = SetuCommandHandler(tmp_path)
    handler._doujinshi_service = service
    config = _Config()
    config.doujinshi_send_mode = "archive"

    async def allow_access(event, current_config) -> tuple[bool, str]:
        return True, ""

    monkeypatch.setattr(
        "astrbot_plugin_setu.src.infrastructure.astrbot.commands.setu.get_config",
        lambda: config,
    )
    monkeypatch.setattr(handler, "_check_access", allow_access)

    results = [result async for result in handler.random_doujinshi_command(mock_event)]

    assert service.requested_mode == "archive"
    assert isinstance(results[-1].result_chain[0], Comp.File)
    assert results[-1].result_chain[0].name == "测试本子.zip"


@pytest.mark.asyncio
async def test_random_doujinshi_passes_max_page_from_config(
    tmp_path: Path, mock_event, monkeypatch: pytest.MonkeyPatch
) -> None:
    generated = GeneratedDoujinshiPdf(
        gallery=DoujinshiGallery(
            id=123,
            title="测试本子",
            page_urls=("https://example.com/1.jpg",),
        ),
        path=tmp_path / "doujinshi-123.pdf",
    )
    service = _DoujinshiService(generated)
    handler = SetuCommandHandler(tmp_path)
    handler._doujinshi_service = service
    config = _Config()
    config.doujinshi_max_page = 11

    async def allow_access(event, current_config) -> tuple[bool, str]:
        return True, ""

    monkeypatch.setattr(
        "astrbot_plugin_setu.src.infrastructure.astrbot.commands.setu.get_config",
        lambda: config,
    )
    monkeypatch.setattr(handler, "_check_access", allow_access)

    results = [result async for result in handler.random_doujinshi_command(mock_event)]

    assert service.requested_max_page == 11
    assert isinstance(results[-1].result_chain[0], Comp.File)


@pytest.mark.asyncio
async def test_random_doujinshi_schedules_direct_file_revoke(
    tmp_path: Path, mock_event, monkeypatch: pytest.MonkeyPatch
) -> None:
    generated_path = tmp_path / "doujinshi-123.pdf"
    generated_path.write_bytes(b"test-pdf")
    generated = GeneratedDoujinshiPdf(
        gallery=DoujinshiGallery(
            id=123,
            title="测试本子",
            page_urls=("https://example.com/1.jpg",),
        ),
        path=generated_path,
    )
    context = MagicMock()
    scheduler = MagicMock()
    scheduler.schedule_revoke = AsyncMock(return_value=True)
    handler = SetuCommandHandler(
        tmp_path,
        plugin_context=context,
        revoke_scheduler=scheduler,
    )
    handler._doujinshi_service = _DoujinshiService(generated)
    mock_event.platform.name = "aiocqhttp"
    mock_event.get_group_id.return_value = "10001"
    mock_event.get_self_id.return_value = "10000"
    mock_event.bot = MagicMock()
    mock_event.bot.send_group_msg = AsyncMock(
        return_value={"data": {"message_id": "file-message"}}
    )

    async def allow_access(event, config) -> tuple[bool, str]:
        return True, ""

    monkeypatch.setattr(
        "astrbot_plugin_setu.src.infrastructure.astrbot.commands.setu.get_config",
        lambda: _Config(),
    )
    monkeypatch.setattr(handler, "_check_access", allow_access)

    results = [result async for result in handler.random_doujinshi_command(mock_event)]

    assert len(results) == 1
    scheduler.schedule_revoke.assert_awaited_once_with(mock_event, "file-message", 1800)
    mock_event.bot.send_group_msg.assert_awaited_once()
    payload = mock_event.bot.send_group_msg.await_args.kwargs
    file_value = payload["message"][0]["data"]["file"]
    assert file_value == generated_path.as_uri()
    context.send_message.assert_not_called()
