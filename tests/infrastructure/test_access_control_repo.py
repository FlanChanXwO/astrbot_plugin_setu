"""Tests for FileBackedAccessControlRepo."""

from __future__ import annotations

import json

import pytest
from astrbot_plugin_setu.src.infrastructure.persistence import (
    FileBackedAccessControlRepo,
)
from astrbot_plugin_setu.src.infrastructure.persistence.access_control_repo import (
    AccessControlPersistenceError,
)


class TestFileBackedAccessControlRepo:
    """Test FileBackedAccessControlRepo."""

    @pytest.mark.asyncio
    async def test_initialize(self, temp_data_dir, mock_astrbot_config) -> None:
        """Test repository initialization."""
        repo = FileBackedAccessControlRepo(temp_data_dir, mock_astrbot_config)
        await repo.initialize()
        assert repo._config_file.exists()

    @pytest.mark.asyncio
    async def test_initialize_does_not_rewrite_unchanged_config(
        self, temp_data_dir, mock_astrbot_config, monkeypatch
    ) -> None:
        """Repeated initialization should not touch an unchanged config file."""
        repo = FileBackedAccessControlRepo(temp_data_dir, mock_astrbot_config)
        await repo.initialize()

        writes: list[str] = []
        original_write = FileBackedAccessControlRepo._write_config_file

        def record_write(self, data: str) -> None:
            writes.append(data)
            original_write(self, data)

        monkeypatch.setattr(
            FileBackedAccessControlRepo, "_write_config_file", record_write
        )

        repo2 = FileBackedAccessControlRepo(temp_data_dir, mock_astrbot_config)
        await repo2.initialize()

        assert writes == []

    @pytest.mark.asyncio
    async def test_setu_user_blacklist(
        self, temp_data_dir, mock_astrbot_config
    ) -> None:
        """Test Setu user blacklist operations."""
        repo = FileBackedAccessControlRepo(temp_data_dir, mock_astrbot_config)
        await repo.initialize()

        # Add to blacklist
        assert await repo.add_setu_blocked_user("user123") is True
        assert await repo.is_setu_user_blocked("user123") is True

        # Remove from blacklist
        assert await repo.remove_setu_blocked_user("user123") is True
        assert await repo.is_setu_user_blocked("user123") is False

    @pytest.mark.asyncio
    async def test_setu_user_whitelist(
        self, temp_data_dir, mock_astrbot_config
    ) -> None:
        """Test Setu user whitelist operations."""
        repo = FileBackedAccessControlRepo(temp_data_dir, mock_astrbot_config)
        await repo.initialize()

        # Add to whitelist
        assert await repo.add_setu_whitelist_user("user456") is True
        assert await repo.is_setu_user_whitelisted("user456") is True

        # Remove from whitelist
        assert await repo.remove_setu_whitelist_user("user456") is True
        assert await repo.is_setu_user_whitelisted("user456") is False

    @pytest.mark.asyncio
    async def test_setu_group_blacklist(
        self, temp_data_dir, mock_astrbot_config
    ) -> None:
        """Test Setu group blacklist operations."""
        repo = FileBackedAccessControlRepo(temp_data_dir, mock_astrbot_config)
        await repo.initialize()

        # Add to blacklist
        assert await repo.add_setu_blocked_group("group789") is True
        assert await repo.is_setu_group_blocked("group789") is True

        # Remove from blacklist
        assert await repo.remove_setu_blocked_group("group789") is True
        assert await repo.is_setu_group_blocked("group789") is False

    @pytest.mark.asyncio
    async def test_setu_group_whitelist(
        self, temp_data_dir, mock_astrbot_config
    ) -> None:
        """Test Setu group whitelist operations."""
        repo = FileBackedAccessControlRepo(temp_data_dir, mock_astrbot_config)
        await repo.initialize()

        # Add to whitelist
        assert await repo.add_setu_whitelist_group("group101") is True
        assert await repo.is_setu_group_whitelisted("group101") is True

        # Remove from whitelist
        assert await repo.remove_setu_whitelist_group("group101") is True
        assert await repo.is_setu_group_whitelisted("group101") is False

    @pytest.mark.asyncio
    async def test_fortune_user_operations(
        self, temp_data_dir, mock_astrbot_config
    ) -> None:
        """Test Fortune user operations."""
        repo = FileBackedAccessControlRepo(temp_data_dir, mock_astrbot_config)
        await repo.initialize()

        # Blacklist
        assert await repo.add_fortune_blocked_user("user222") is True
        assert await repo.is_fortune_user_blocked("user222") is True

        # Whitelist
        assert await repo.add_fortune_whitelist_user("user333") is True
        assert await repo.is_fortune_user_whitelisted("user333") is True

    @pytest.mark.asyncio
    async def test_fortune_group_operations(
        self, temp_data_dir, mock_astrbot_config
    ) -> None:
        """Test Fortune group operations."""
        repo = FileBackedAccessControlRepo(temp_data_dir, mock_astrbot_config)
        await repo.initialize()

        # Blacklist
        assert await repo.add_fortune_blocked_group("group444") is True
        assert await repo.is_fortune_group_blocked("group444") is True

        # Whitelist
        assert await repo.add_fortune_whitelist_group("group555") is True
        assert await repo.is_fortune_group_whitelisted("group555") is True

    @pytest.mark.asyncio
    async def test_mutual_exclusion_blacklist_whitelist(
        self, temp_data_dir, mock_astrbot_config
    ) -> None:
        """Test that adding to blacklist removes from whitelist and vice versa."""
        repo = FileBackedAccessControlRepo(temp_data_dir, mock_astrbot_config)
        await repo.initialize()

        # Add to blacklist, then whitelist
        await repo.add_setu_blocked_user("user666")
        assert await repo.is_setu_user_blocked("user666") is True

        await repo.add_setu_whitelist_user("user666")
        assert await repo.is_setu_user_whitelisted("user666") is True
        assert await repo.is_setu_user_blocked("user666") is False

        # Add to whitelist, then blacklist
        await repo.add_setu_blocked_user("user666")
        assert await repo.is_setu_user_blocked("user666") is True
        assert await repo.is_setu_user_whitelisted("user666") is False

    @pytest.mark.asyncio
    async def test_table_entries_drive_legacy_checks(
        self, temp_data_dir, mock_astrbot_config
    ) -> None:
        """Table-style entries should back old checker methods."""
        repo = FileBackedAccessControlRepo(temp_data_dir, mock_astrbot_config)
        await repo.initialize()

        entry = await repo.upsert_entry(
            {
                "feature": "setu",
                "subject_type": "user",
                "list_type": "blacklist",
                "target_id": "user-table",
                "note": "manual",
            }
        )

        assert await repo.is_setu_user_blocked("user-table") is True
        entries = repo.list_entries()
        stored_entry = next(item for item in entries if item["id"] == entry["id"])
        assert stored_entry["note"] == "manual"

        assert await repo.delete_entry(entry["id"]) is True
        assert await repo.is_setu_user_blocked("user-table") is False

    @pytest.mark.asyncio
    async def test_set_modes_surfaces_persistence_failure(
        self, temp_data_dir, mock_astrbot_config, monkeypatch
    ) -> None:
        """WebUI writes should not report success when the JSON save fails."""
        repo = FileBackedAccessControlRepo(temp_data_dir, mock_astrbot_config)
        await repo.initialize()

        async def fail_save() -> bool:
            return False

        monkeypatch.setattr(repo, "_save_config", fail_save)

        with pytest.raises(AccessControlPersistenceError):
            await repo.set_modes({"setu_user_access_control_mode": "blacklist"})

    @pytest.mark.asyncio
    async def test_modes_are_persisted(
        self, temp_data_dir, mock_astrbot_config
    ) -> None:
        """Access modes should be managed by the new safety page store."""
        repo = FileBackedAccessControlRepo(temp_data_dir, mock_astrbot_config)
        await repo.initialize()

        modes = await repo.set_modes(
            {
                "setu_user_access_control_mode": "blacklist",
                "fortune_group_access_control_mode": "whitelist",
            }
        )

        assert modes["setu_user_access_control_mode"] == "blacklist"
        assert modes["fortune_group_access_control_mode"] == "whitelist"

        repo2 = FileBackedAccessControlRepo(temp_data_dir, mock_astrbot_config)
        await repo2.initialize()
        assert repo2.get_modes()["setu_user_access_control_mode"] == "blacklist"

    @pytest.mark.asyncio
    async def test_imports_legacy_config_file_lists(
        self, temp_data_dir, mock_astrbot_config
    ) -> None:
        """Old config.json list keys should migrate into table entries."""
        (temp_data_dir / "config.json").write_text(
            json.dumps(
                {
                    "setu_blocked_users": ["legacy-user"],
                    "fortune_whitelist_groups": ["legacy-group"],
                }
            ),
            encoding="utf-8",
        )
        repo = FileBackedAccessControlRepo(temp_data_dir, mock_astrbot_config)
        await repo.initialize()

        entries = repo.list_entries()
        assert await repo.is_setu_user_blocked("legacy-user") is True
        assert await repo.is_fortune_group_whitelisted("legacy-group") is True
        assert {entry["target_id"] for entry in entries} == {
            "legacy-user",
            "legacy-group",
        }
