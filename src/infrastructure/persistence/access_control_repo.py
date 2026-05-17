"""File-backed repository for access control data.

Implements AccessControlRepository interface using JSON file persistence.
Extracted from ConfigManager to separate persistence from domain logic.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from astrbot.api import logger

from ...application.ports import AccessControlRepository

if TYPE_CHECKING:
    from astrbot.core import AstrBotConfig


class FileBackedAccessControlRepo(AccessControlRepository):
    """File-backed repository for access control lists.

    Stores blacklist/whitelist data in JSON file with async lock protection.
    Syncs with AstrBotConfig for WebUI compatibility.
    """

    SAFETY_LIST_KEYS = (
        "setu_blocked_users",
        "setu_whitelist_users",
        "setu_blocked_groups",
        "setu_whitelist_groups",
        "fortune_blocked_users",
        "fortune_whitelist_users",
        "fortune_blocked_groups",
        "fortune_whitelist_groups",
    )

    def __init__(
        self, data_dir: Path, astrbot_config: AstrBotConfig | None = None
    ) -> None:
        """Initialize repository.

        Args:
            data_dir: Plugin data directory
            astrbot_config: AstrBot config for WebUI sync
        """
        self._data_dir = data_dir
        self._config_file = data_dir / "config.json"
        self._cache: dict[str, Any] = {}
        self._astrbot_config = astrbot_config
        self._main_config_cache: dict[str, Any] | None = None
        self._main_config_cache_mtime: float | None = None
        self._main_config_cache_path: Path | None = None

    async def initialize(self) -> None:
        """Initialize repository, load existing config."""
        self._load_config()
        imported = self._sync_from_astrbot_config()
        if not imported:
            self._sync_to_astrbot_config()
        if not self._config_file.exists():
            await self._save_config()

    def _load_config(self) -> None:
        """Load config from file."""
        if not self._config_file.exists():
            self._cache = {}
            return

        try:
            with open(self._config_file, encoding="utf-8") as f:
                self._cache = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load config file: %s", e)
            self._cache = {}

    async def _save_config(self) -> bool:
        """Save config to file via executor.

        Returns:
            True if save succeeded
        """
        try:
            self._data_dir.mkdir(parents=True, exist_ok=True)
            data = json.dumps(self._cache, ensure_ascii=False, indent=2)
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._write_config_file, data)
            self._sync_to_astrbot_config()
            return True
        except (OSError, TypeError) as e:
            logger.error("Failed to save config file: %s", e)
            return False

    def _write_config_file(self, data: str) -> None:
        """Write config data to file (called in thread pool)."""
        with open(self._config_file, "w", encoding="utf-8") as f:
            f.write(data)

    # Setu user access control
    async def add_setu_blocked_user(self, user_id: str) -> bool:
        """Add user to Setu blacklist."""
        user_id = str(user_id).strip()
        if not user_id:
            return False
        await self.remove_setu_whitelist_user(user_id)
        return await self._add_to_list("setu_blocked_users", user_id)

    async def remove_setu_blocked_user(self, user_id: str) -> bool:
        """Remove user from Setu blacklist."""
        return await self._remove_from_list("setu_blocked_users", user_id)

    async def is_setu_user_blocked(self, user_id: str) -> bool:
        """Check if user is in Setu blacklist."""
        return self._is_in_list("setu_blocked_users", user_id)

    async def add_setu_whitelist_user(self, user_id: str) -> bool:
        """Add user to Setu whitelist."""
        user_id = str(user_id).strip()
        if not user_id:
            return False
        await self.remove_setu_blocked_user(user_id)
        return await self._add_to_list("setu_whitelist_users", user_id)

    async def remove_setu_whitelist_user(self, user_id: str) -> bool:
        """Remove user from Setu whitelist."""
        return await self._remove_from_list("setu_whitelist_users", user_id)

    async def is_setu_user_whitelisted(self, user_id: str) -> bool:
        """Check if user is in Setu whitelist."""
        return self._is_in_list("setu_whitelist_users", user_id)

    # Setu group access control
    async def add_setu_blocked_group(self, group_id: str) -> bool:
        """Add group to Setu blacklist."""
        return await self._add_to_list("setu_blocked_groups", group_id)

    async def remove_setu_blocked_group(self, group_id: str) -> bool:
        """Remove group from Setu blacklist."""
        return await self._remove_from_list("setu_blocked_groups", group_id)

    async def is_setu_group_blocked(self, group_id: str) -> bool:
        """Check if group is in Setu blacklist."""
        return self._is_in_list("setu_blocked_groups", group_id)

    async def add_setu_whitelist_group(self, group_id: str) -> bool:
        """Add group to Setu whitelist."""
        return await self._add_to_list("setu_whitelist_groups", group_id)

    async def remove_setu_whitelist_group(self, group_id: str) -> bool:
        """Remove group from Setu whitelist."""
        return await self._remove_from_list("setu_whitelist_groups", group_id)

    async def is_setu_group_whitelisted(self, group_id: str) -> bool:
        """Check if group is in Setu whitelist."""
        return self._is_in_list("setu_whitelist_groups", group_id)

    # Fortune user access control
    async def add_fortune_blocked_user(self, user_id: str) -> bool:
        """Add user to Fortune blacklist."""
        user_id = str(user_id).strip()
        if not user_id:
            return False
        await self.remove_fortune_whitelist_user(user_id)
        return await self._add_to_list("fortune_blocked_users", user_id)

    async def remove_fortune_blocked_user(self, user_id: str) -> bool:
        """Remove user from Fortune blacklist."""
        return await self._remove_from_list("fortune_blocked_users", user_id)

    async def is_fortune_user_blocked(self, user_id: str) -> bool:
        """Check if user is in Fortune blacklist."""
        return self._is_in_list("fortune_blocked_users", user_id)

    async def add_fortune_whitelist_user(self, user_id: str) -> bool:
        """Add user to Fortune whitelist."""
        user_id = str(user_id).strip()
        if not user_id:
            return False
        await self.remove_fortune_blocked_user(user_id)
        return await self._add_to_list("fortune_whitelist_users", user_id)

    async def remove_fortune_whitelist_user(self, user_id: str) -> bool:
        """Remove user from Fortune whitelist."""
        return await self._remove_from_list("fortune_whitelist_users", user_id)

    async def is_fortune_user_whitelisted(self, user_id: str) -> bool:
        """Check if user is in Fortune whitelist."""
        return self._is_in_list("fortune_whitelist_users", user_id)

    # Fortune group access control
    async def add_fortune_blocked_group(self, group_id: str) -> bool:
        """Add group to Fortune blacklist."""
        return await self._add_to_list("fortune_blocked_groups", group_id)

    async def remove_fortune_blocked_group(self, group_id: str) -> bool:
        """Remove group from Fortune blacklist."""
        return await self._remove_from_list("fortune_blocked_groups", group_id)

    async def is_fortune_group_blocked(self, group_id: str) -> bool:
        """Check if group is in Fortune blacklist."""
        return self._is_in_list("fortune_blocked_groups", group_id)

    async def add_fortune_whitelist_group(self, group_id: str) -> bool:
        """Add group to Fortune whitelist."""
        return await self._add_to_list("fortune_whitelist_groups", group_id)

    async def remove_fortune_whitelist_group(self, group_id: str) -> bool:
        """Remove group from Fortune whitelist."""
        return await self._remove_from_list("fortune_whitelist_groups", group_id)

    async def is_fortune_group_whitelisted(self, group_id: str) -> bool:
        """Check if group is in Fortune whitelist."""
        return self._is_in_list("fortune_whitelist_groups", group_id)

    # Helper methods
    async def _add_to_list(self, key: str, item: str) -> bool:
        """Add item to list (normalized on write)."""
        current = self._cache.setdefault(key, [])
        item_str = str(item).strip()
        if not item_str or item_str in current:
            return True
        current.append(item_str)
        return await self._save_config()

    async def _remove_from_list(self, key: str, item: str) -> bool:
        """Remove item from list."""
        current = self._cache.get(key, [])
        item_str = str(item).strip()
        if item_str not in current:
            return True
        current.remove(item_str)
        return await self._save_config()

    def _is_in_list(self, key: str, item: str) -> bool:
        """Check if item is in list."""
        current = self._cache.get(key, [])
        return str(item).strip() in current

    # WebUI sync methods
    def _sync_to_astrbot_config(self) -> None:
        """Sync local config to AstrBotConfig for WebUI."""
        if self._astrbot_config is None:
            return

        try:
            updated = False

            if "safety" not in self._astrbot_config:
                self._astrbot_config["safety"] = {}
                updated = True

            safety_config = self._astrbot_config["safety"]
            if not isinstance(safety_config, dict):
                safety_config = {}
                self._astrbot_config["safety"] = safety_config
                updated = True

            for key in self.SAFETY_LIST_KEYS:
                if key not in self._cache:
                    continue
                value = self._cache.get(key)
                if not isinstance(value, list):
                    value = []
                if safety_config.get(key) != value:
                    safety_config[key] = value
                    updated = True

            if updated and hasattr(self._astrbot_config, "save_config"):
                if callable(getattr(self._astrbot_config, "save_config")):
                    self._astrbot_config.save_config()

        except Exception as e:
            logger.debug("Failed to sync to AstrBot config: %s", e)

    def _sync_from_astrbot_config(self) -> bool:
        """Sync from AstrBotConfig to local cache."""
        if self._astrbot_config is None:
            return False

        try:
            imported = False
            updated = False

            safety_config = self._astrbot_config.get("safety", {})
            if not isinstance(safety_config, dict):
                return False

            for key in self.SAFETY_LIST_KEYS:
                if key not in safety_config:
                    continue
                imported = True
                value = safety_config.get(key)
                if not isinstance(value, list):
                    value = []
                value = [str(v).strip() for v in value if str(v).strip()]
                if self._cache.get(key) != value:
                    self._cache[key] = value
                    updated = True

            if updated:
                self._data_dir.mkdir(parents=True, exist_ok=True)
                with open(self._config_file, "w", encoding="utf-8") as f:
                    json.dump(self._cache, f, ensure_ascii=False, indent=2)

            return imported

        except Exception as e:
            logger.debug("Failed to sync from AstrBot config: %s", e)
            return False
