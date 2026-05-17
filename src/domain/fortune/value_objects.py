"""Fortune domain value objects."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class FortuneSeed:
    """Value object identifying a fortune request."""

    user_id: str
    date_str: str

    @classmethod
    def for_today(cls, user_id: str) -> FortuneSeed:
        """Create seed for today's fortune."""
        return cls(user_id, date.today().isoformat())

    @property
    def cache_key(self) -> str:
        """Return cache key for this fortune."""
        return f"{self.user_id}_{self.date_str}"


@dataclass(frozen=True)
class FortuneResult:
    """Value object containing fortune generation result."""

    seed: FortuneSeed
    title: str
    star_count: int
    description: str
    extra_message: str
    theme_color: str

    @property
    def max_stars(self) -> int:
        """Maximum possible stars."""
        return 7
