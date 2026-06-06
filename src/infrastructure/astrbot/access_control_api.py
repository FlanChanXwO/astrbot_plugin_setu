"""WebUI API handlers for access control management."""

from __future__ import annotations

from typing import Any

from quart import jsonify, request

from ...shared import get_logger
from ..persistence import get_access_control_repo

PLUGIN_NAME = "astrbot_plugin_setu"
logger = get_logger()


class AccessControlApi:
    """Quart handlers registered through AstrBot's plugin Web API bridge."""

    async def get_state(self):
        """Return access-control modes and table entries."""
        try:
            repo = get_access_control_repo()
            return jsonify(
                {
                    "success": True,
                    "modes": repo.get_modes(),
                    "entries": repo.list_entries(),
                }
            )
        except Exception as exc:
            return _internal_error_response(exc, "get access-control state")

    async def save_modes(self):
        """Persist access-control mode settings."""
        try:
            payload = await request.get_json()
            payload = payload or {}
            repo = get_access_control_repo()
            modes = await repo.set_modes(_dict(payload.get("modes", payload)))
            return jsonify({"success": True, "modes": modes})
        except (ValueError, TypeError) as exc:
            return _validation_error_response(exc)
        except Exception as exc:
            return _internal_error_response(exc, "save access-control modes")

    async def upsert_entry(self):
        """Create or update one access-control table row."""
        try:
            payload = await request.get_json()
            payload = payload or {}
            repo = get_access_control_repo()
            entry = await repo.upsert_entry(_dict(payload))
            return jsonify({"success": True, "data": entry})
        except (ValueError, TypeError) as exc:
            return _validation_error_response(exc)
        except Exception as exc:
            return _internal_error_response(exc, "upsert access-control entry")

    async def delete_entry(self):
        """Delete one access-control table row."""
        try:
            payload = await request.get_json()
            payload = payload or {}
            repo = get_access_control_repo()
            deleted = await repo.delete_entry(str(payload.get("id", "")))
            return jsonify({"success": True, "deleted": deleted})
        except (ValueError, TypeError) as exc:
            return _validation_error_response(exc)
        except Exception as exc:
            return _internal_error_response(exc, "delete access-control entry")


def register_access_control_web_apis(context: Any) -> None:
    """Register WebUI APIs for the accessControl page."""
    api = AccessControlApi()
    context.register_web_api(
        f"/{PLUGIN_NAME}/access-control",
        api.get_state,
        ["GET"],
        "Get access control state",
    )
    context.register_web_api(
        f"/{PLUGIN_NAME}/access-control/modes",
        api.save_modes,
        ["POST"],
        "Save access control modes",
    )
    context.register_web_api(
        f"/{PLUGIN_NAME}/access-control/entries/upsert",
        api.upsert_entry,
        ["POST"],
        "Create or update access control entry",
    )
    context.register_web_api(
        f"/{PLUGIN_NAME}/access-control/entries/delete",
        api.delete_entry,
        ["POST"],
        "Delete access control entry",
    )


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _validation_error_response(exc: Exception):
    """Return sanitized client-facing validation errors."""
    message = str(exc).strip() or "请求参数无效"
    return jsonify({"success": False, "error": message}), 400


def _internal_error_response(exc: Exception, action: str):
    """Log full internal errors while keeping WebUI responses safe."""
    logger.exception("[access_control_api] %s failed: %s", action, exc)
    return jsonify({"success": False, "error": "Internal server error"}), 500
