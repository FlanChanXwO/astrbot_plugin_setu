"""Domain service for tag alias resolution.

Extracted from SafetyConfigMixin.resolve_tags() to separate domain logic
from infrastructure/config layer.
"""

from __future__ import annotations


class TagResolverService:
    """Domain service for resolving tag aliases.

    Provides pure functions for tag normalization and alias lookup.
    """

    DEFAULT_TAG_ALIAS: dict[str, list[str]] = {
        "萝莉": ["loli", "roricon"],
        "少女": ["girl", "girls"],
        "猫耳": ["cat_ears", "nekomimi"],
        "狗耳": ["dog_ears", "inumimi"],
        "长发": ["long_hair"],
        "短发": ["short_hair"],
        "双马尾": ["twintails", "twin_tails"],
        "丝袜": ["pantyhose", "stockings"],
        "白丝": ["white_stockings", "white_pantyhose"],
        "黑丝": ["black_stockings", "black_pantyhose"],
        "泳装": ["swimsuit", "mizugi"],
        "校服": ["school_uniform", "seifuku"],
    }

    def __init__(self, alias_map: dict[str, list[str]] | None = None) -> None:
        """Initialize tag resolver.

        Args:
            alias_map: Custom tag alias mapping (canonical -> [aliases]).
                      If None, uses DEFAULT_TAG_ALIAS.
        """
        self._alias_map = alias_map if alias_map is not None else self.DEFAULT_TAG_ALIAS

    def resolve_tags(self, raw_tags: str) -> list[str]:
        """Resolve and normalize tag string to canonical tag names.

        Args:
            raw_tags: Comma or space-separated tag string

        Returns:
            List of canonical tag names
        """
        if not raw_tags:
            return []

        # Normalize separators
        normalized = raw_tags.replace("，", ",").replace(" ", ",")
        raw_list = [t.strip() for t in normalized.split(",") if t.strip()]

        return [self._resolve_single_tag(tag) for tag in raw_list]

    def _resolve_single_tag(self, tag: str) -> str:
        """Resolve a single tag to its canonical name.

        Args:
            tag: Tag name (may be alias or canonical)

        Returns:
            Canonical tag name, or original tag if not found in alias map
        """
        canonical = self._find_canonical_tag(tag)
        return canonical if canonical else tag

    def _find_canonical_tag(self, tag: str) -> str | None:
        """Find canonical tag name from alias map.

        Args:
            tag: Tag name to look up

        Returns:
            Canonical tag name, or None if not found
        """
        normalized = tag.lower()

        for canonical, aliases in self._alias_map.items():
            if not isinstance(canonical, str):
                continue

            if normalized == canonical.lower():
                return canonical

            if isinstance(aliases, list):
                for alias in aliases:
                    if isinstance(alias, str) and normalized == alias.lower():
                        return canonical

        return None

    @classmethod
    def parse_alias_map_from_string(cls, alias_str: str) -> dict[str, list[str]]:
        """Parse alias map from config string format.

        Format: "canonical=alias1,alias2" (one per line, # or ; for comments)

        Args:
            alias_str: Raw alias string from config

        Returns:
            Parsed alias map
        """
        if not alias_str or not isinstance(alias_str, str):
            return {}

        result: dict[str, list[str]] = {}
        lines = alias_str.strip().replace("\r\n", "\n").split("\n")

        for line in lines:
            line = line.strip()

            # Skip comments and empty lines
            if not line or line.startswith(("#", ";")):
                continue

            if "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()

            if not key or not value:
                continue

            aliases = [a.strip() for a in value.split(",") if a.strip()]
            if aliases:
                result[key] = aliases

        return result

    def get_alias_map(self) -> dict[str, list[str]]:
        """Get the current alias map.

        Returns:
            Copy of the alias map
        """
        return dict(self._alias_map)

    def update_alias_map(self, new_map: dict[str, list[str]]) -> None:
        """Update the alias map.

        Args:
            new_map: New alias map to use
        """
        self._alias_map = dict(new_map) if new_map else {}
