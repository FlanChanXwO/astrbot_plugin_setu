"""DTOs for per-session configuration overrides."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

JsonValue = str | int | float | bool | None | list[Any] | dict[str, Any]
SessionType = Literal["group", "private"]


@dataclass(frozen=True, slots=True)
class SessionConfigRecord:
    """Stored override record for one chat session."""

    session_id: str
    session_type: SessionType = "private"
    display_name: str = ""
    overrides: dict[str, JsonValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "session_id": self.session_id,
            "session_type": self.session_type,
            "display_name": self.display_name,
            "overrides": dict(self.overrides),
        }


@dataclass(frozen=True, slots=True)
class SessionConfigSnapshot:
    """Effective configuration for one session."""

    session_id: str
    session_type: SessionType
    display_name: str
    overrides: dict[str, JsonValue]
    global_values: dict[str, JsonValue]
    effective: dict[str, JsonValue]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "session_id": self.session_id,
            "session_type": self.session_type,
            "display_name": self.display_name,
            "overrides": dict(self.overrides),
            "global": dict(self.global_values),
            "effective": dict(self.effective),
        }
