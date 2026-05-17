"""WebUI API handlers for session configuration management."""

from __future__ import annotations

from typing import Any

from quart import jsonify, request

from ...application.session_config import (
    SESSION_CONFIG_KEYS,
    SessionConfigService,
    get_global_session_config_values,
)
from ..persistence import get_session_config_repo
from .config import get_config

PLUGIN_NAME = "astrbot_plugin_setu"


class SessionConfigApi:
    """Quart handlers registered through AstrBot's plugin Web API bridge."""

    async def list_sessions(self):
        """Return session config schema, globals, and all records."""
        try:
            service = SessionConfigService(get_session_config_repo())
            snapshots = await service.list_snapshots()
            return jsonify(
                {
                    "success": True,
                    "keys": [item.to_dict() for item in SESSION_CONFIG_KEYS.values()],
                    "global": get_global_session_config_values(),
                    "sessions": [snapshot.to_dict() for snapshot in snapshots],
                    "config_loaded": get_config() is not None,
                }
            )
        except Exception as exc:
            return jsonify({"success": False, "error": str(exc)}), 500

    async def upsert_session(self):
        """Create or replace one session record."""
        try:
            payload = await request.get_json()
            payload = payload or {}
            service = SessionConfigService(get_session_config_repo())
            snapshot = await service.upsert_session(
                session_id=str(payload.get("session_id", "")),
                session_type=str(payload.get("session_type", "private")),
                display_name=str(payload.get("display_name", "")),
                overrides=_dict(payload.get("overrides")),
            )
            return jsonify({"success": True, "data": snapshot.to_dict()})
        except Exception as exc:
            return jsonify({"success": False, "error": str(exc)}), 400

    async def delete_session(self):
        """Delete a session record."""
        try:
            payload = await request.get_json()
            payload = payload or {}
            service = SessionConfigService(get_session_config_repo())
            deleted = await service.delete_session(str(payload.get("session_id", "")))
            return jsonify({"success": True, "deleted": deleted})
        except Exception as exc:
            return jsonify({"success": False, "error": str(exc)}), 400

    async def clear_session(self):
        """Clear all overrides or one key for a session while keeping the record."""
        try:
            payload = await request.get_json()
            payload = payload or {}
            service = SessionConfigService(get_session_config_repo())
            key = str(payload.get("key", "")).strip() or None
            snapshot = await service.clear(
                session_id=str(payload.get("session_id", "")),
                session_type=str(payload.get("session_type", "private")),
                key=key,
                display_name=str(payload.get("display_name", "")),
            )
            return jsonify({"success": True, "data": snapshot.to_dict()})
        except Exception as exc:
            return jsonify({"success": False, "error": str(exc)}), 400


def register_session_config_web_apis(context: Any) -> None:
    """Register WebUI APIs for the sessionConfig page."""
    api = SessionConfigApi()
    context.register_web_api(
        f"/{PLUGIN_NAME}/session-config",
        api.list_sessions,
        ["GET"],
        "List session config records",
    )
    context.register_web_api(
        f"/{PLUGIN_NAME}/session-config/upsert",
        api.upsert_session,
        ["POST"],
        "Create or update session config",
    )
    context.register_web_api(
        f"/{PLUGIN_NAME}/session-config/delete",
        api.delete_session,
        ["POST"],
        "Delete session config",
    )
    context.register_web_api(
        f"/{PLUGIN_NAME}/session-config/clear",
        api.clear_session,
        ["POST"],
        "Clear session config overrides",
    )


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
