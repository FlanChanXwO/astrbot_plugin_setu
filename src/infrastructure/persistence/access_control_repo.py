"""File-backed repository for access control data.

Implements AccessControlRepository interface using JSON file persistence.
Extracted from ConfigManager to separate persistence from domain logic.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from astrbot.api import logger

from ...application.ports import AccessControlRepository

if TYPE_CHECKING:
    from astrbot.core import AstrBotConfig


class AccessControlPersistenceError(RuntimeError):
    """Raised when access-control changes cannot be persisted."""


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
    MODE_KEYS = (
        "setu_user_access_control_mode",
        "setu_group_access_control_mode",
        "fortune_user_access_control_mode",
        "fortune_group_access_control_mode",
    )
    DEFAULT_MODES = {
        "setu_user_access_control_mode": "none",
        "setu_group_access_control_mode": "none",
        "fortune_user_access_control_mode": "none",
        "fortune_group_access_control_mode": "none",
    }
    ENTRY_META = {
        "setu_blocked_users": ("setu", "user", "blacklist"),
        "setu_whitelist_users": ("setu", "user", "whitelist"),
        "setu_blocked_groups": ("setu", "group", "blacklist"),
        "setu_whitelist_groups": ("setu", "group", "whitelist"),
        "fortune_blocked_users": ("fortune", "user", "blacklist"),
        "fortune_whitelist_users": ("fortune", "user", "whitelist"),
        "fortune_blocked_groups": ("fortune", "group", "blacklist"),
        "fortune_whitelist_groups": ("fortune", "group", "whitelist"),
    }

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
        config_exists = self._config_file.exists()
        cache_before = dict(self._cache) if isinstance(self._cache, dict) else {}
        self._normalize_cache()
        imported = self._sync_from_astrbot_config()
        if not imported:
            self._sync_to_astrbot_config()
        if not config_exists or self._cache != cache_before:
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

    def _normalize_cache(self) -> None:
        """Ensure cache has the new access-control shape."""
        if not isinstance(self._cache, dict):
            self._cache = {}
        modes = self._cache.get("modes")
        if not isinstance(modes, dict):
            modes = {}
        self._cache["modes"] = {
            key: _normalize_mode(modes.get(key, self.DEFAULT_MODES[key]))
            for key in self.MODE_KEYS
        }
        entries = self._cache.get("entries")
        if not isinstance(entries, list):
            entries = []
        self._cache["entries"] = [
            entry
            for entry in (_normalize_entry(item) for item in entries)
            if entry is not None
        ]
        for key in self.SAFETY_LIST_KEYS:
            values = self._cache.get(key)
            if isinstance(values, list):
                normalized = [str(v).strip() for v in values if str(v).strip()]
                self._merge_legacy_list_entries(key, normalized)
        self._sync_legacy_lists_from_entries()

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

    def get_modes(self) -> dict[str, str]:
        """Return configured access-control modes."""
        modes = self._cache.setdefault("modes", dict(self.DEFAULT_MODES))
        return {
            key: _normalize_mode(modes.get(key, self.DEFAULT_MODES[key]))
            for key in self.MODE_KEYS
        }

    async def set_modes(self, modes: dict[str, Any]) -> dict[str, str]:
        """Update access-control modes used by runtime checks."""
        current = self.get_modes()
        for key in self.MODE_KEYS:
            if key in modes:
                current[key] = _normalize_mode(modes.get(key))
        self._cache["modes"] = current
        await self._ensure_saved()
        return self.get_modes()

    def list_entries(self) -> list[dict[str, str]]:
        """Return normalized table entries for the WebUI page."""
        return [dict(entry) for entry in self._cache.setdefault("entries", [])]

    async def upsert_entry(self, payload: dict[str, Any]) -> dict[str, str]:
        """Create or update one access-control table entry."""
        entry = _normalize_entry(payload)
        if entry is None:
            raise ValueError("访问控制记录缺少必要字段")
        entries = self._cache.setdefault("entries", [])
        replaced = False
        for index, existing in enumerate(entries):
            if existing.get("id") == entry["id"]:
                entries[index] = entry
                replaced = True
                break
        if not replaced:
            entries.append(entry)
        self._dedupe_entry_conflicts(entry)
        self._sync_legacy_lists_from_entries()
        await self._ensure_saved()
        return entry

    async def delete_entry(self, entry_id: str) -> bool:
        """Delete an access-control table entry by id."""
        entry_id = str(entry_id).strip()
        entries = self._cache.setdefault("entries", [])
        next_entries = [entry for entry in entries if entry.get("id") != entry_id]
        deleted = len(next_entries) != len(entries)
        if deleted:
            self._cache["entries"] = next_entries
            self._sync_legacy_lists_from_entries()
            await self._ensure_saved()
        return deleted

    async def _ensure_saved(self) -> None:
        """Persist current cache or surface the failure to callers."""
        if not await self._save_config():
            raise AccessControlPersistenceError("访问控制配置保存失败")

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
        item_str = str(item).strip()
        if not item_str:
            return False
        current = self._cache.setdefault(key, [])
        if item_str in current:
            return True
        entry = self._entry_from_legacy_item(key, item_str)
        if entry is None:
            return False
        entries = self._cache.setdefault("entries", [])
        if not any(
            existing.get("feature") == entry["feature"]
            and existing.get("subject_type") == entry["subject_type"]
            and existing.get("list_type") == entry["list_type"]
            and existing.get("target_id") == entry["target_id"]
            for existing in entries
        ):
            entries.append(entry)
        current.append(item_str)
        return await self._save_config()

    async def _remove_from_list(self, key: str, item: str) -> bool:
        """Remove item from list."""
        current = self._cache.get(key, [])
        item_str = str(item).strip()
        if item_str not in current:
            return True
        current.remove(item_str)
        meta = self.ENTRY_META.get(key)
        if meta:
            feature, subject_type, list_type = meta
            self._cache["entries"] = [
                entry
                for entry in self._cache.setdefault("entries", [])
                if not (
                    entry.get("feature") == feature
                    and entry.get("subject_type") == subject_type
                    and entry.get("list_type") == list_type
                    and entry.get("target_id") == item_str
                )
            ]
        return await self._save_config()

    def _is_in_list(self, key: str, item: str) -> bool:
        """Check if item is in list."""
        current = self._cache.get(key, [])
        return str(item).strip() in current

    def _entry_from_legacy_item(self, key: str, item: str) -> dict[str, str] | None:
        meta = self.ENTRY_META.get(key)
        if meta is None:
            return None
        feature, subject_type, list_type = meta
        return {
            "id": uuid4().hex,
            "feature": feature,
            "subject_type": subject_type,
            "list_type": list_type,
            "target_id": item,
            "note": "",
        }

    def _sync_legacy_lists_from_entries(self) -> None:
        """Maintain old list keys from the new table representation."""
        lists = {key: [] for key in self.SAFETY_LIST_KEYS}
        reverse = {meta: key for key, meta in self.ENTRY_META.items()}
        for entry in self._cache.setdefault("entries", []):
            key = reverse.get(
                (
                    entry.get("feature"),
                    entry.get("subject_type"),
                    entry.get("list_type"),
                )
            )
            target_id = str(entry.get("target_id", "")).strip()
            if key and target_id and target_id not in lists[key]:
                lists[key].append(target_id)
        self._cache.update(lists)

    def _dedupe_entry_conflicts(self, entry: dict[str, str]) -> None:
        """Keep one list assignment per feature/subject/target tuple."""
        self._cache["entries"] = [
            existing
            for existing in self._cache.setdefault("entries", [])
            if existing.get("id") == entry["id"]
            or not (
                existing.get("feature") == entry["feature"]
                and existing.get("subject_type") == entry["subject_type"]
                and existing.get("target_id") == entry["target_id"]
            )
        ]

    # WebUI sync methods
    def _sync_to_astrbot_config(self) -> None:
        """Do not write access-control data back into plugin config.

        Access control is managed by the accessControl page and persisted in the
        plugin data directory. AstrBotConfig is only used as a one-time legacy
        import source.
        """
        return

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

            modes = self.get_modes()
            for key in self.MODE_KEYS:
                if key not in safety_config:
                    continue
                imported = True
                value = _normalize_mode(safety_config.get(key))
                if modes.get(key) != value:
                    modes[key] = value
                    updated = True
            self._cache["modes"] = modes

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
                    self._merge_legacy_list_entries(key, value)
                    updated = True

            if updated:
                self._sync_legacy_lists_from_entries()

            return imported

        except Exception as e:
            logger.debug("Failed to sync from AstrBot config: %s", e)
            return False

    def _merge_legacy_list_entries(self, key: str, values: list[str]) -> None:
        """Import old safety list values into the new table entries."""
        entries = self._cache.setdefault("entries", [])
        meta = self.ENTRY_META.get(key)
        if meta is None:
            return
        feature, subject_type, list_type = meta
        for value in values:
            if any(
                entry.get("feature") == feature
                and entry.get("subject_type") == subject_type
                and entry.get("list_type") == list_type
                and entry.get("target_id") == value
                for entry in entries
            ):
                continue
            entries.append(
                {
                    "id": uuid4().hex,
                    "feature": feature,
                    "subject_type": subject_type,
                    "list_type": list_type,
                    "target_id": value,
                    "note": "",
                }
            )


def _normalize_mode(value: Any) -> str:
    text = str(value or "none").strip().lower()
    return text if text in {"none", "blacklist", "whitelist"} else "none"


def _normalize_entry(value: Any) -> dict[str, str] | None:
    if not isinstance(value, dict):
        return None
    feature = str(value.get("feature", "")).strip().lower()
    subject_type = str(value.get("subject_type", "")).strip().lower()
    list_type = str(value.get("list_type", "")).strip().lower()
    target_id = str(value.get("target_id", "")).strip()
    if feature not in {"setu", "fortune"}:
        return None
    if subject_type not in {"user", "group"}:
        return None
    if list_type not in {"blacklist", "whitelist"}:
        return None
    if not target_id:
        return None
    return {
        "id": str(value.get("id") or uuid4().hex).strip(),
        "feature": feature,
        "subject_type": subject_type,
        "list_type": list_type,
        "target_id": target_id,
        "note": str(value.get("note", "")).strip(),
    }
