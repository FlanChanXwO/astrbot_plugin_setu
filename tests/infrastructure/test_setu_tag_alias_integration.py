"""Integration-like tests for Setu tag alias mapping in command handler."""

from __future__ import annotations

from types import SimpleNamespace

from astrbot_plugin_setu.src.infrastructure.astrbot.commands.setu import (
    SetuCommandHandler,
)


class TestSetuTagAliasIntegration:
    """Verify configured tag aliases are applied in runtime command paths."""

    def test_resolve_tags_uses_configured_alias_map(self) -> None:
        handler = SetuCommandHandler()
        config = SimpleNamespace(tag_alias="二次元=acg,anime")

        resolved = handler._resolve_tags("acg cute", config)

        assert resolved == ["二次元", "cute"]

    def test_resolve_tags_from_list_uses_configured_alias_map(self) -> None:
        handler = SetuCommandHandler()
        config = SimpleNamespace(tag_alias="少女=girl")

        resolved = handler._resolve_tags_from_list(["girl", "kawaii"], config)

        assert resolved == ["少女", "kawaii"]

    def test_resolve_tags_from_list_keeps_multi_word_tags(self) -> None:
        handler = SetuCommandHandler()
        config = SimpleNamespace(tag_alias="碧蓝档案=blue archive")

        resolved = handler._resolve_tags_from_list(
            ["blue archive", "white hair"], config
        )

        assert resolved == ["碧蓝档案", "white hair"]
