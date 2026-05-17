"""Tests for FileBackedAccessControlRepo."""

from __future__ import annotations

import pytest

from astrbot_plugin_setu.src.infrastructure.persistence import (
    FileBackedAccessControlRepo,
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
