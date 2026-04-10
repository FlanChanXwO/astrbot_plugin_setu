"""Shared helpers for AstrBotConfig-backed session-level configuration."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from astrbot.core import AstrBotConfig


class SessionConfigBase:
    """Base utilities for session config managers.

    Subclasses provide key-specific validation and value conversion logic.
    """

    def __init__(
        self,
        config: AstrBotConfig,
        *,
        config_key: str,
    ):
        self._config = config
        self._config_key = config_key
        self._lock = asyncio.Lock()

    @staticmethod
    def _session_type(is_group: bool) -> str:
        return "group" if is_group else "private"

    def _get_session_key(self, session_id: str, is_group: bool) -> str:
        return f"{self._session_type(is_group)}:{session_id}"

    def _get_configs(self) -> list[dict]:
        return list(self._config.get(self._config_key, []))

    def _save_configs(self, configs: list[dict]) -> None:
        self._config[self._config_key] = configs
        self._config.save_config()

    def _find_session_index(
        self,
        configs: list[dict],
        session_id: str,
        is_group: bool,
    ) -> int | None:
        session_type = self._session_type(is_group)
        for i, cfg in enumerate(configs):
            if (
                cfg.get("session_id") == session_id
                and cfg.get("session_type") == session_type
            ):
                return i
        return None

    def _find_session_config(
        self,
        session_id: str,
        is_group: bool,
    ) -> dict | None:
        configs = self._get_configs()
        idx = self._find_session_index(configs, session_id, is_group)
        if idx is None:
            return None
        return configs[idx]

    @staticmethod
    def _parse_session_key(session_key: str) -> tuple[str, str] | None:
        parts = session_key.split(":", 1)
        if len(parts) != 2:
            return None
        session_type, session_id = parts
        if session_type not in {"group", "private"}:
            return None
        return session_type, session_id

    @staticmethod
    def merge_session_item(configs: list[dict], item: dict) -> None:
        """Insert or replace a session config item by (session_id, session_type)."""
        session_id = item.get("session_id")
        session_type = item.get("session_type")
        if not session_id or session_type not in {"group", "private"}:
            return
        for i, cfg in enumerate(configs):
            if (
                cfg.get("session_id") == session_id
                and cfg.get("session_type") == session_type
            ):
                configs[i] = item
                return
        configs.append(item)
