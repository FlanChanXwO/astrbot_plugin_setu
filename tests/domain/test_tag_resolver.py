"""Tests for TagResolverService domain service."""

from __future__ import annotations


from astrbot_plugin_setu.src.domain.setu import TagResolverService


class TestTagResolverService:
    """Test TagResolverService."""

    def test_init_default(self) -> None:
        """Test initialization with default alias map."""
        resolver = TagResolverService()
        alias_map = resolver.get_alias_map()
        assert "萝莉" in alias_map
        assert "loli" in alias_map["萝莉"]

    def test_init_custom(self) -> None:
        """Test initialization with custom alias map."""
        custom_map = {"test": ["alias1", "alias2"]}
        resolver = TagResolverService(custom_map)
        assert resolver.get_alias_map() == custom_map

    def test_resolve_tags_empty(self) -> None:
        """Test resolving empty tag string."""
        resolver = TagResolverService()
        assert resolver.resolve_tags("") == []

    def test_resolve_tags_single(self) -> None:
        """Test resolving single tag."""
        resolver = TagResolverService()
        tags = resolver.resolve_tags("girl")
        assert tags == ["少女"]

    def test_resolve_tags_multiple(self) -> None:
        """Test resolving multiple tags."""
        resolver = TagResolverService()
        tags = resolver.resolve_tags("girl,cute,long_hair")
        assert tags == ["少女", "cute", "长发"]

    def test_resolve_tags_with_alias(self) -> None:
        """Test resolving tag with alias."""
        resolver = TagResolverService()
        tags = resolver.resolve_tags("loli")
        assert tags == ["萝莉"]

    def test_resolve_tags_chinese_comma(self) -> None:
        """Test resolving tags with Chinese comma."""
        resolver = TagResolverService()
        tags = resolver.resolve_tags("girl，cute")
        assert tags == ["少女", "cute"]

    def test_resolve_tags_with_spaces(self) -> None:
        """Test resolving tags with spaces."""
        resolver = TagResolverService()
        tags = resolver.resolve_tags("girl cute long_hair")
        assert tags == ["少女", "cute", "长发"]

    def test_resolve_tags_mixed_separators(self) -> None:
        """Test resolving tags with mixed separators."""
        resolver = TagResolverService()
        tags = resolver.resolve_tags("girl, cute，long_hair cat")
        assert tags == ["少女", "cute", "长发", "cat"]

    def test_parse_alias_map_from_string(self) -> None:
        """Test parsing alias map from config string."""
        alias_str = """# Comment line
canonical1=alias1,alias2
canonical2=alias3

# Another comment
canonical3=alias4,alias5
"""
        result = TagResolverService.parse_alias_map_from_string(alias_str)
        assert result == {
            "canonical1": ["alias1", "alias2"],
            "canonical2": ["alias3"],
            "canonical3": ["alias4", "alias5"],
        }

    def test_parse_alias_map_empty(self) -> None:
        """Test parsing empty alias string."""
        result = TagResolverService.parse_alias_map_from_string("")
        assert result == {}

    def test_parse_alias_map_invalid_lines(self) -> None:
        """Test parsing alias string with invalid lines."""
        alias_str = """
valid=test1,alias1
invalid line
=alias2
test2=
"""
        result = TagResolverService.parse_alias_map_from_string(alias_str)
        assert result == {"valid": ["test1", "alias1"]}

    def test_update_alias_map(self) -> None:
        """Test updating alias map."""
        resolver = TagResolverService()
        new_map = {"custom": ["alias1", "alias2"]}
        resolver.update_alias_map(new_map)
        assert resolver.get_alias_map() == new_map

    def test_find_canonical_tag_case_insensitive(self) -> None:
        """Test canonical tag lookup is case-insensitive."""
        resolver = TagResolverService()
        assert resolver._find_canonical_tag("萝莉") == "萝莉"
        assert resolver._find_canonical_tag("LOLI") == "萝莉"
        assert resolver._find_canonical_tag("loli") == "萝莉"
