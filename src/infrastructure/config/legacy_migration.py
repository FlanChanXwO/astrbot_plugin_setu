"""Legacy AstrBot config migration helpers for Setu."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from ...application.session_config.keys import TRUE_VALUES


def record_config_heal(changes: list[str], path: str, reason: str) -> None:
    """Record one config healing decision for startup logs and tests."""
    changes.append(f"{path}: {reason}")


def apply_legacy_config_aliases(
    raw_config: dict[str, Any],
    changes: list[str],
) -> dict[str, Any]:
    """Migrate legacy config keys before schema normalization."""
    normalized = deepcopy(raw_config)
    delivery = normalized.get("delivery")
    if isinstance(delivery, dict) and "auto_revoke_r18" in delivery:
        legacy_value = delivery.pop("auto_revoke_r18")
        if "auto_revoke_scope" not in delivery:
            delivery["auto_revoke_scope"] = _legacy_revoke_bool_to_scope(legacy_value)
            record_config_heal(
                changes,
                "delivery.auto_revoke_r18",
                "migrated to delivery.auto_revoke_scope",
            )
        else:
            record_config_heal(
                changes,
                "delivery.auto_revoke_r18",
                "removed legacy key because auto_revoke_scope exists",
            )

    if isinstance(delivery, dict) and "doujinshi_file_cleanup_delay" in delivery:
        legacy_value = delivery.pop("doujinshi_file_cleanup_delay")
        if "auto_revoke_delay" not in delivery:
            delivery["auto_revoke_delay"] = legacy_value
            record_config_heal(
                changes,
                "delivery.doujinshi_file_cleanup_delay",
                "migrated to delivery.auto_revoke_delay",
            )
        else:
            record_config_heal(
                changes,
                "delivery.doujinshi_file_cleanup_delay",
                "removed legacy key because auto_revoke_delay exists",
            )

    session_configs = normalized.get("session_configs")
    if isinstance(session_configs, list):
        for index, item in enumerate(session_configs):
            if not isinstance(item, dict) or "auto_revoke_r18" not in item:
                continue
            legacy_value = item.pop("auto_revoke_r18")
            if "auto_revoke_scope" not in item:
                item["auto_revoke_scope"] = _legacy_revoke_bool_to_scope(legacy_value)
                record_config_heal(
                    changes,
                    f"session_configs[{index}].auto_revoke_r18",
                    "migrated to auto_revoke_scope",
                )
            else:
                record_config_heal(
                    changes,
                    f"session_configs[{index}].auto_revoke_r18",
                    "removed legacy key because auto_revoke_scope exists",
                )

    return normalized


def _legacy_revoke_bool_to_scope(value: Any) -> str:
    """Map the old bool-ish R18 revoke toggle to the new scope enum."""
    if isinstance(value, bool):
        return "r18" if value else "none"
    text = str(value or "").strip().lower()
    return "r18" if text in TRUE_VALUES else "none"
