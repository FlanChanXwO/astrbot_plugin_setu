"""JSON-backed repository for session configuration overrides."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from astrbot.api import logger

from ...application.ports import SessionConfigRepository
from ...application.session_config import (
    SessionConfigRecord,
    normalize_config_value,
    normalize_session_type,
)

SESSION_CONFIG_VERSION = 1


class JsonSessionConfigRepository(SessionConfigRepository):
    """Persist session overrides in `<data_dir>/session_overrides.json`."""

    def __init__(self, data_dir: Path) -> None:
        self._path = data_dir / "session_overrides.json"
        self._lock = asyncio.Lock()
        self._sessions: dict[str, SessionConfigRecord] = {}

    async def initialize(self) -> None:
        """Load existing records or create an empty store."""
        async with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            if not self._path.exists():
                self._sessions = {}
                await self._save_unlocked()
                return
            self._sessions = await asyncio.to_thread(self._load_from_disk)

    async def list_sessions(self) -> list[SessionConfigRecord]:
        """List all stored session records."""
        async with self._lock:
            return sorted(
                self._sessions.values(),
                key=lambda record: (
                    record.session_type,
                    record.display_name,
                    record.session_id,
                ),
            )

    async def get_session(self, session_id: str) -> SessionConfigRecord | None:
        """Get a session record by ID."""
        async with self._lock:
            return self._sessions.get(str(session_id).strip())

    async def upsert_session(self, record: SessionConfigRecord) -> SessionConfigRecord:
        """Create or replace a session record."""
        normalized = _normalize_record(record)
        async with self._lock:
            self._sessions[normalized.session_id] = normalized
            await self._save_unlocked()
            return normalized

    async def delete_session(self, session_id: str) -> bool:
        """Delete a session record."""
        async with self._lock:
            existed = self._sessions.pop(str(session_id).strip(), None) is not None
            if existed:
                await self._save_unlocked()
            return existed

    def _load_from_disk(self) -> dict[str, SessionConfigRecord]:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed to load session overrides: %s", exc)
            return {}

        sessions: dict[str, SessionConfigRecord] = {}
        for item in data.get("sessions", []):
            if not isinstance(item, dict):
                continue
            try:
                record = _record_from_dict(item)
            except (TypeError, ValueError) as exc:
                logger.warning("Ignoring invalid session override record: %s", exc)
                continue
            sessions[record.session_id] = record
        return sessions

    async def _save_unlocked(self) -> None:
        data = {
            "version": SESSION_CONFIG_VERSION,
            "sessions": [record.to_dict() for record in self._sessions.values()],
        }
        await asyncio.to_thread(self._write_json, data)

    def _write_json(self, data: dict[str, Any]) -> None:
        tmp_path = self._path.with_suffix(".tmp")
        tmp_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        tmp_path.replace(self._path)


def _record_from_dict(data: dict[str, Any]) -> SessionConfigRecord:
    raw_overrides = (
        data.get("overrides") if isinstance(data.get("overrides"), dict) else {}
    )
    overrides = {
        str(key).strip(): normalize_config_value(str(key).strip(), value)
        for key, value in raw_overrides.items()
    }
    return SessionConfigRecord(
        session_id=str(data.get("session_id", "")).strip(),
        session_type=normalize_session_type(str(data.get("session_type", "private"))),
        display_name=str(data.get("display_name", "")).strip(),
        overrides=overrides,
    )


def _normalize_record(record: SessionConfigRecord) -> SessionConfigRecord:
    overrides = {
        key.strip(): normalize_config_value(key, value)
        for key, value in record.overrides.items()
    }
    return SessionConfigRecord(
        session_id=str(record.session_id).strip(),
        session_type=normalize_session_type(record.session_type),
        display_name=record.display_name.strip(),
        overrides=overrides,
    )
