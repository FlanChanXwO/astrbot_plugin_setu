from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from astrbot_plugin_setu.src.infrastructure.astrbot import access_control_api
from quart import Quart


class MessageConfig:
    def __init__(self, messages: dict[str, str]) -> None:
        self.messages = messages

    def resolve_message(self, key: str, **kwargs) -> str | None:
        return self.messages.get(key)


@pytest.mark.asyncio
async def test_validation_error_response_uses_configured_fallback(
    monkeypatch,
) -> None:
    app = Quart(__name__)
    monkeypatch.setattr(
        access_control_api,
        "get_config",
        lambda: MessageConfig({"error.invalid_request": "坏请求"}),
    )

    async with app.app_context():
        response, status = access_control_api._validation_error_response(ValueError(""))
        assert status == 400
        assert await response.get_json() == {"success": False, "error": "坏请求"}


@pytest.mark.asyncio
async def test_validation_error_response_preserves_exception_message(
    monkeypatch,
) -> None:
    app = Quart(__name__)
    monkeypatch.setattr(
        access_control_api,
        "get_config",
        lambda: MessageConfig({"error.invalid_request": "坏请求"}),
    )

    async with app.app_context():
        response, status = access_control_api._validation_error_response(
            ValueError("字段无效")
        )
        assert status == 400
        assert await response.get_json() == {"success": False, "error": "字段无效"}


@pytest.mark.asyncio
async def test_internal_error_response_uses_configured_safe_message(
    monkeypatch,
) -> None:
    app = Quart(__name__)
    log_exception = MagicMock()
    monkeypatch.setattr(access_control_api.logger, "exception", log_exception)
    monkeypatch.setattr(
        access_control_api,
        "get_config",
        lambda: MessageConfig({"error.internal_server": "服务器开小差了"}),
    )

    async with app.app_context():
        response, status = access_control_api._internal_error_response(
            RuntimeError("secret"), "save"
        )
        assert status == 500
        assert await response.get_json() == {
            "success": False,
            "error": "服务器开小差了",
        }
    log_exception.assert_called_once()
