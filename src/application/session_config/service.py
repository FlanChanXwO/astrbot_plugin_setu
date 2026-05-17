"""Application service for session-scoped configuration overrides."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..settings import get_delivery_settings, get_fortune_settings, get_setu_settings
from .dto import JsonValue, SessionConfigRecord, SessionConfigSnapshot
from .keys import (
    SESSION_CONFIG_KEYS,
    get_key_definition,
    normalize_config_value,
    normalize_session_type,
)

if TYPE_CHECKING:
    from ..ports.session_config_repository import SessionConfigRepository


class SessionConfigService:
    """Coordinate validation, persistence, and effective session config snapshots."""

    def __init__(self, repository: SessionConfigRepository) -> None:
        self._repo = repository

    async def list_snapshots(self) -> list[SessionConfigSnapshot]:
        """Return effective snapshots for all stored sessions."""
        records = await self._repo.list_sessions()
        return [self._snapshot_from_record(record) for record in records]

    async def get_snapshot(
        self,
        session_id: str,
        session_type: str = "private",
        display_name: str = "",
    ) -> SessionConfigSnapshot:
        """Return the effective config snapshot for a session."""
        record = await self._repo.get_session(_normalize_session_id(session_id))
        if record is None:
            record = SessionConfigRecord(
                session_id=_normalize_session_id(session_id),
                session_type=normalize_session_type(session_type),
                display_name=display_name.strip(),
            )
        return self._snapshot_from_record(record)

    async def get_effective_value(
        self,
        session_id: str,
        key: str,
        session_type: str = "private",
        display_name: str = "",
    ) -> JsonValue:
        """Return one effective value for a session."""
        snapshot = await self.get_snapshot(session_id, session_type, display_name)
        return snapshot.effective[key]

    async def set_value(
        self,
        session_id: str,
        session_type: str,
        key: str,
        value: Any,
        display_name: str = "",
    ) -> SessionConfigSnapshot:
        """Set one override value and return the updated snapshot."""
        session_id = _normalize_session_id(session_id)
        normalized_key = key.strip()
        record = await self._repo.get_session(session_id)
        if record is None:
            record = SessionConfigRecord(
                session_id=session_id,
                session_type=normalize_session_type(session_type),
                display_name=display_name.strip(),
            )

        overrides = dict(record.overrides)
        overrides[normalized_key] = normalize_config_value(normalized_key, value)
        updated = SessionConfigRecord(
            session_id=session_id,
            session_type=normalize_session_type(session_type or record.session_type),
            display_name=(display_name or record.display_name).strip(),
            overrides=overrides,
        )
        saved = await self._repo.upsert_session(updated)
        return self._snapshot_from_record(saved)

    async def clear(
        self,
        session_id: str,
        session_type: str,
        key: str | None = None,
        display_name: str = "",
    ) -> SessionConfigSnapshot:
        """Clear one override or all overrides while keeping the session record."""
        session_id = _normalize_session_id(session_id)
        record = await self._repo.get_session(session_id)
        if record is None:
            record = SessionConfigRecord(
                session_id=session_id,
                session_type=normalize_session_type(session_type),
                display_name=display_name.strip(),
            )

        overrides = dict(record.overrides)
        if key:
            get_key_definition(key)
            overrides.pop(key.strip(), None)
        else:
            overrides.clear()

        updated = SessionConfigRecord(
            session_id=session_id,
            session_type=normalize_session_type(session_type or record.session_type),
            display_name=(display_name or record.display_name).strip(),
            overrides=overrides,
        )
        saved = await self._repo.upsert_session(updated)
        return self._snapshot_from_record(saved)

    async def upsert_session(
        self,
        session_id: str,
        session_type: str,
        display_name: str = "",
        overrides: dict[str, Any] | None = None,
    ) -> SessionConfigSnapshot:
        """Create or replace a session config record from WebUI input."""
        normalized_overrides = {
            key.strip(): normalize_config_value(key, value)
            for key, value in (overrides or {}).items()
        }
        record = SessionConfigRecord(
            session_id=_normalize_session_id(session_id),
            session_type=normalize_session_type(session_type),
            display_name=display_name.strip(),
            overrides=normalized_overrides,
        )
        saved = await self._repo.upsert_session(record)
        return self._snapshot_from_record(saved)

    async def delete_session(self, session_id: str) -> bool:
        """Delete a whole session record."""
        return await self._repo.delete_session(_normalize_session_id(session_id))

    def _snapshot_from_record(
        self, record: SessionConfigRecord
    ) -> SessionConfigSnapshot:
        global_values = get_global_session_config_values()
        overrides = _filter_known_overrides(record.overrides)
        effective = dict(global_values)
        effective.update(overrides)
        return SessionConfigSnapshot(
            session_id=record.session_id,
            session_type=record.session_type,
            display_name=record.display_name,
            overrides=overrides,
            global_values=global_values,
            effective=effective,
        )


def get_global_session_config_values() -> dict[str, JsonValue]:
    """Return current read-only global values relevant to session overrides."""
    setu = get_setu_settings()
    delivery = get_delivery_settings()
    fortune = get_fortune_settings()
    return {
        "setu.content_mode": setu.content_mode,
        "setu.r18_docx": delivery.r18_docx_mode,
        "setu.auto_revoke": delivery.auto_revoke_r18,
        "setu.send_mode": delivery.send_mode,
        "fortune.tags": fortune.tags,
        "fortune.content_mode": fortune.content_mode,
    }


def _filter_known_overrides(overrides: dict[str, Any]) -> dict[str, JsonValue]:
    """Keep only known and valid override values."""
    result: dict[str, JsonValue] = {}
    for key, value in overrides.items():
        if key in SESSION_CONFIG_KEYS:
            result[key] = normalize_config_value(key, value)
    return result


def _normalize_session_id(session_id: str) -> str:
    normalized = str(session_id).strip()
    if not normalized:
        raise ValueError("session_id 不能为空")
    return normalized
