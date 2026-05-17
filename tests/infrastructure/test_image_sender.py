"""Tests for image sender transport behavior."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import astrbot.api.message_components as Comp
from astrbot_plugin_setu.src.application.setu import ImagePayload
from astrbot_plugin_setu.src.infrastructure.astrbot.config import (
    clear_config,
    set_plugin_context,
)
from astrbot_plugin_setu.src.infrastructure.sending.image_sender import ImageSender
from astrbot_plugin_setu.src.infrastructure.sending.send_strategies import (
    DirectSendStrategy,
)
from astrbot_plugin_setu.src.shared.config import SetuPluginConfig


@pytest.fixture(autouse=True)
def reset_singletons() -> None:
    """Keep config/context singletons isolated."""
    clear_config()
    yield
    clear_config()


@pytest.mark.asyncio
async def test_send_images_streams_on_fallback(
    tmp_path: Path, mock_event, sample_config_dict
) -> None:
    """A failed normal path send uses NapCat stream upload and retries once."""
    image_path = tmp_path / "image.jpg"
    image_path.write_bytes(b"image-data")

    context = MagicMock()
    sent_results: list[Any] = []

    async def send_message(_origin: str, result: Any) -> Any:
        sent_results.append(result)
        if len(sent_results) == 1:
            return {"message_id": "found"}
        if len(sent_results) == 2:
            return None
        return {"message_id": "streamed"}

    context.send_message.side_effect = send_message
    set_plugin_context(context)

    mock_event.platform.name = "aiocqhttp"
    mock_event.bot = MagicMock()
    mock_event.bot.api = None

    async def call_action(action: str, **params: Any) -> dict[str, Any]:
        assert action == "upload_file_stream"
        if params.get("is_complete"):
            return {"status": "ok", "retcode": 0, "data": {"file_path": "stream://image"}}
        return {"status": "ok", "retcode": 0, "data": {}}

    mock_event.bot.call_action = AsyncMock(side_effect=call_action)

    config = SetuPluginConfig(**sample_config_dict)
    payload = ImagePayload(
        urls=("https://example.com/image.jpg",),
        raw_bytes=(),
        file_paths=(image_path,),
        items=(image_path,),
        r18=False,
        tags=(),
    )

    results = [item async for item in ImageSender(config).send_images(payload, mock_event)]

    assert results == [{"send_success": True, "image_count": 1}]
    assert len(sent_results) == 3
    retried_chain = sent_results[-1].result_chain
    assert retried_chain[0].file == "stream://image"
    assert mock_event.bot.call_action.called


@pytest.mark.asyncio
async def test_send_images_materializes_local_files_before_direct_send(
    tmp_path: Path, mock_event, sample_config_dict
) -> None:
    image_path = tmp_path / "image.jpg"
    image_path.write_bytes(b"image-data")

    context = MagicMock()
    sent_results: list[Any] = []

    async def send_message(_origin: str, result: Any) -> dict[str, str]:
        sent_results.append(result)
        return {"message_id": "ok"}

    context.send_message = AsyncMock(side_effect=send_message)
    set_plugin_context(context)

    config_dict = sample_config_dict.copy()
    config_dict["delivery"] = {**sample_config_dict["delivery"], "napcat_stream_mode": "disabled"}
    config = SetuPluginConfig(**config_dict)
    payload = ImagePayload(
        urls=(),
        raw_bytes=(),
        file_paths=(image_path,),
        items=(image_path,),
        r18=False,
        tags=(),
    )

    results = [item async for item in ImageSender(config).send_images(payload, mock_event)]

    assert results == [{"send_success": True, "image_count": 1}]
    image_comp = sent_results[-1].result_chain[0]
    assert isinstance(image_comp, Comp.Image)
    assert isinstance(image_comp.file, str)
    assert image_comp.file.startswith("base64://")


@pytest.mark.asyncio
async def test_direct_send_strategy_passthroughs_onebot_stream_refs(mock_event) -> None:
    context = MagicMock()
    strategy = DirectSendStrategy(context)

    mock_event.platform.name = "aiocqhttp"
    mock_event.get_group_id.return_value = "123456"
    mock_event.get_sender_id.return_value = "654321"
    mock_event.bot = MagicMock()
    mock_event.bot.send_group_msg = AsyncMock(return_value={"message_id": "ok"})

    success = await strategy.send(mock_event, [Comp.Image(file="stream://image")])

    assert success is True
    mock_event.bot.send_group_msg.assert_awaited_once_with(
        group_id=123456,
        message=[{"type": "image", "data": {"file": "stream://image"}}],
    )
