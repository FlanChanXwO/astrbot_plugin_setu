"""Setu domain value objects."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SetuRequest:
    """Value object representing a Setu image request."""

    count: int
    tags: tuple[str, ...]
    r18: bool
    exclude_ai: bool

    @classmethod
    def from_user_input(
        cls, count: int, tags: list[str], r18: bool, exclude_ai: bool = True
    ) -> SetuRequest:
        """Create from user input, normalizing tags to tuple."""
        return cls(count, tuple(tags), r18, exclude_ai)

    def with_tags(self, new_tags: list[str]) -> SetuRequest:
        """Return a new SetuRequest with different tags."""
        return SetuRequest(self.count, tuple(new_tags), self.r18, self.exclude_ai)
