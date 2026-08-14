"""标签解析共享辅助函数的集成式测试。"""

from __future__ import annotations

from types import SimpleNamespace

from astrbot_plugin_setu.src.application.setu.tag_resolution import (
    resolve_user_tag_list,
    resolve_user_tags,
)


class TestSetuTagAliasIntegration:
    """验证色图与本子可共享的标签别名解析。"""

    def test_resolve_tags_uses_configured_alias_map(self) -> None:
        config = SimpleNamespace(tag_alias="二次元=acg,anime")

        resolved = resolve_user_tags("acg cute", config.tag_alias)

        assert resolved == ["二次元", "cute"]

    def test_resolve_tags_from_list_uses_configured_alias_map(self) -> None:
        config = SimpleNamespace(tag_alias="少女=girl")

        resolved = resolve_user_tag_list(["girl", "kawaii"], config.tag_alias)

        assert resolved == ["少女", "kawaii"]

    def test_resolve_tags_from_list_keeps_multi_word_tags(self) -> None:
        config = SimpleNamespace(tag_alias="碧蓝档案=blue archive")

        resolved = resolve_user_tag_list(
            ["blue archive", "white hair"], config.tag_alias
        )

        assert resolved == ["碧蓝档案", "white hair"]
