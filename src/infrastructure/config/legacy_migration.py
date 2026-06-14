"""Legacy AstrBot config migration helpers for Setu."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

_TRUE_VALUES = {"1", "true", "yes", "on", "enable", "enabled", "开", "开启", "启用"}


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
    return "r18" if text in _TRUE_VALUES else "none"
