"""Tests for JSON-backed session configuration."""

from __future__ import annotations

import json

import pytest
from astrbot_plugin_setu.src.application.session_config import (
    SessionConfigService,
    SessionConfigValidationError,
)
from astrbot_plugin_setu.src.application.settings import clear_application_config
from astrbot_plugin_setu.src.infrastructure.persistence.session_config_json_repository import (
    JsonSessionConfigRepository,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def clear_config() -> None:
    """Keep global config defaults deterministic."""
    clear_application_config()


async def test_session_config_repo_creates_initial_file(temp_data_dir) -> None:
    """Repository initializes the independent session override store."""
    repo = JsonSessionConfigRepository(temp_data_dir)
    await repo.initialize()

    data = json.loads((temp_data_dir / "session_overrides.json").read_text())
    assert data == {"version": 1, "sessions": []}


async def test_session_config_service_sets_and_clears_values(temp_data_dir) -> None:
    """Service validates values and keeps a record when clearing overrides."""
    repo = JsonSessionConfigRepository(temp_data_dir)
    await repo.initialize()
    service = SessionConfigService(repo)

    snapshot = await service.set_value(
        "platform:group:1000", "group", "setu.content_mode", "r18", "测试群"
    )
    assert snapshot.overrides["setu.content_mode"] == "r18"
    assert snapshot.effective["setu.content_mode"] == "r18"

    snapshot = await service.set_value(
        "platform:group:1000", "group", "setu.auto_revoke", "on", "测试群"
    )
    assert snapshot.overrides["setu.auto_revoke"] is True

    snapshot = await service.clear(
        "platform:group:1000", "group", "setu.content_mode", "测试群"
    )
    assert "setu.content_mode" not in snapshot.overrides
    assert snapshot.effective["setu.content_mode"] == "sfw"

    sessions = await service.list_snapshots()
    assert len(sessions) == 1
    assert sessions[0].session_id == "platform:group:1000"


async def test_session_config_service_rejects_unknown_key(temp_data_dir) -> None:
    """Unknown config keys are rejected before persistence."""
    repo = JsonSessionConfigRepository(temp_data_dir)
    await repo.initialize()
    service = SessionConfigService(repo)

    with pytest.raises(SessionConfigValidationError):
        await service.set_value("session", "private", "unknown.key", "value")
