"""LLM 工具注册管理模块。

集中管理所有 LLM 工具的定义、注册和注销。
将工具定义从 main.py 分离，便于维护和扩展。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from astrbot.core.provider.register import llm_tools

if TYPE_CHECKING:
    pass


@dataclass
class LlmToolDefinition:
    """LLM 工具定义。

    包含工具的名称、描述、参数和处理函数。
    """

    name: str
    handler: Callable[..., Any]
    args: list[dict[str, Any]] = field(default_factory=list)
    description: str = ""
    module_path: str | None = None


class LlmToolRegistry:
    """LLM 工具注册管理器。

    管理工具的注册和注销，支持按模块分组管理。
    """

    def __init__(self):
        self._registered_tools: dict[str, str] = {}
        # key: tool_name, value: module_path (用于追踪工具来源)

    def register_tool(self, tool_def: LlmToolDefinition, module_path: str) -> bool:
        """注册单个 LLM 工具。

        Args:
            tool_def: 工具定义
            module_path: 模块路径（用于插件管理）

        Returns:
            是否成功注册
        """
        try:
            llm_tools.add_func(
                name=tool_def.name,
                func_args=tool_def.args,
                desc=tool_def.description,
                handler=tool_def.handler,
            )
            tool = llm_tools.get_func(tool_def.name)
            if tool:
                tool.handler_module_path = module_path

            self._registered_tools[tool_def.name] = module_path
            return True
        except (AttributeError, RuntimeError):
            return False

    def register_tools(
        self, tools: list[LlmToolDefinition], module_path: str
    ) -> list[str]:
        """批量注册 LLM 工具。

        Args:
            tools: 工具定义列表
            module_path: 模块路径

        Returns:
            成功注册的工具名称列表
        """
        registered: list[str] = []
        for tool_def in tools:
            if self.register_tool(tool_def, module_path):
                registered.append(tool_def.name)
        return registered

    def unregister_tool(self, name: str) -> bool:
        """注销单个 LLM 工具。

        Args:
            name: 工具名称

        Returns:
            是否成功注销
        """
        try:
            llm_tools.remove_func(name)
            self._registered_tools.pop(name, None)
            return True
        except (AttributeError, RuntimeError):
            return False

    def unregister_tools(self, names: list[str]) -> list[str]:
        """批量注销 LLM 工具。

        Args:
            names: 工具名称列表

        Returns:
            成功注销的工具名称列表
        """
        unregistered: list[str] = []
        for name in names:
            if self.unregister_tool(name):
                unregistered.append(name)
        return unregistered

    def unregister_by_module(self, module_path: str) -> list[str]:
        """注销指定模块的所有工具。

        Args:
            module_path: 模块路径

        Returns:
            成功注销的工具名称列表
        """
        tools_to_remove = [
            name for name, path in self._registered_tools.items() if path == module_path
        ]
        return self.unregister_tools(tools_to_remove)

    def get_registered_tools(self) -> dict[str, str]:
        """获取已注册的工具映射。

        Returns:
            工具名称到模块路径的映射
        """
        return self._registered_tools.copy()


# 全局注册管理器实例
_registry = LlmToolRegistry()


def get_registry() -> LlmToolRegistry:
    """获取全局 LLM 工具注册管理器。"""
    return _registry


# ==================== Setu 工具定义 ====================


def get_setu_tool_definitions(handler) -> list[LlmToolDefinition]:
    """获取 Setu 相关的 LLM 工具定义。

    Args:
        handler: LlmHandlers 实例

    Returns:
        工具定义列表
    """
    return [
        LlmToolDefinition(
            name="get_setu_image",
            handler=handler._llm_get_setu_handler,
            args=[
                {
                    "name": "count",
                    "type": "integer",
                    "description": "Number of images.",
                },
                {"name": "tags", "type": "array", "items": {"type": "string"}},
            ],
            description="Fetch random anime images.",
        ),
        LlmToolDefinition(
            name="get_setu_content_mode",
            handler=handler._llm_get_content_mode_handler,
            args=[],
            description="Get content mode.",
        ),
        LlmToolDefinition(
            name="set_setu_content_mode",
            handler=handler._llm_set_content_mode_handler,
            args=[
                {
                    "name": "mode",
                    "type": "string",
                    "enum": ["sfw", "r18", "mix", "clear"],
                },
            ],
            description="Set content mode.",
        ),
        LlmToolDefinition(
            name="set_setu_r18_docx_mode",
            handler=handler._llm_set_r18_docx_mode_handler,
            args=[
                {"name": "enabled", "type": "boolean"},
            ],
            description="Set R18 Docx mode.",
        ),
        LlmToolDefinition(
            name="set_setu_auto_revoke",
            handler=handler._llm_set_auto_revoke_handler,
            args=[
                {"name": "enabled", "type": "boolean"},
            ],
            description="Set auto-revoke.",
        ),
        LlmToolDefinition(
            name="set_setu_send_mode",
            handler=handler._llm_set_send_mode_handler,
            args=[
                {
                    "name": "mode",
                    "type": "string",
                    "enum": ["image", "forward", "auto", "clear"],
                    "description": "Send mode override for current session.",
                }
            ],
            description="Set session send mode.",
        ),
    ]


SETU_TOOL_NAMES = [
    "get_setu_image",
    "get_setu_content_mode",
    "set_setu_content_mode",
    "set_setu_r18_docx_mode",
    "set_setu_auto_revoke",
    "set_setu_send_mode",
]


def register_setu_tools(handler, module_path: str) -> list[str]:
    """注册 Setu 相关的 LLM 工具。

    Args:
        handler: LlmHandlers 实例
        module_path: 模块路径

    Returns:
        成功注册的工具名称列表
    """
    tools = get_setu_tool_definitions(handler)
    return _registry.register_tools(tools, module_path)


def unregister_setu_tools() -> list[str]:
    """注销 Setu 相关的 LLM 工具。

    Returns:
        成功注销的工具名称列表
    """
    return _registry.unregister_tools(SETU_TOOL_NAMES)


# ==================== Fortune 工具定义 ====================


def get_fortune_tool_definitions(handler) -> list[LlmToolDefinition]:
    """获取今日运势相关的 LLM 工具定义。

    Args:
        handler: FortuneLlmHandler 实例

    Returns:
        工具定义列表
    """
    return [
        LlmToolDefinition(
            name="get_today_fortune",
            handler=handler.llm_get_fortune,
            args=[],
            description="Get today's fortune for the user.",
        ),
        LlmToolDefinition(
            name="refresh_my_fortune",
            handler=handler.llm_refresh_fortune,
            args=[],
            description="Refresh my today's fortune (admin only).",
        ),
        LlmToolDefinition(
            name="refresh_group_fortune",
            handler=handler.llm_refresh_group_fortune,
            args=[],
            description="Refresh today's fortune for the current group (admin only).",
        ),
        LlmToolDefinition(
            name="refresh_all_fortune",
            handler=handler.llm_refresh_all_fortune,
            args=[],
            description="Refresh today's fortune for all users (super admin only).",
        ),
        LlmToolDefinition(
            name="get_fortune_config",
            handler=handler.llm_get_fortune_config,
            args=[],
            description="Get the fortune configuration for the current session.",
        ),
        LlmToolDefinition(
            name="set_fortune_config",
            handler=handler.llm_set_fortune_config,
            args=[
                {
                    "name": "tags",
                    "type": "string",
                    "description": "Tags for fortune images, e.g., 'girl,cute'. Leave empty to clear.",
                },
                {
                    "name": "mode",
                    "type": "string",
                    "enum": ["sfw", "r18", "mix"],
                    "description": "Content mode for fortune images.",
                },
            ],
            description="Set the fortune configuration for the current session (admin only).",
        ),
    ]


FORTUNE_TOOL_NAMES = [
    "get_today_fortune",
    "refresh_my_fortune",
    "refresh_group_fortune",
    "refresh_all_fortune",
    "get_fortune_config",
    "set_fortune_config",
]


def register_fortune_tools(handler, module_path: str) -> list[str]:
    """注册今日运势相关的 LLM 工具。

    Args:
        handler: FortuneLlmHandler 实例
        module_path: 模块路径

    Returns:
        成功注册的工具名称列表
    """
    tools = get_fortune_tool_definitions(handler)
    return _registry.register_tools(tools, module_path)


def unregister_fortune_tools() -> list[str]:
    """注销今日运势相关的 LLM 工具。

    Returns:
        成功注销的工具名称列表
    """
    return _registry.unregister_tools(FORTUNE_TOOL_NAMES)


def unregister_all_tools() -> list[str]:
    """注销所有工具（包括 Setu 和 Fortune）。

    Returns:
        成功注销的工具名称列表
    """
    all_names = SETU_TOOL_NAMES + FORTUNE_TOOL_NAMES
    return _registry.unregister_tools(all_names)


__all__ = [
    "LlmToolDefinition",
    "LlmToolRegistry",
    "get_registry",
    # Setu 工具
    "get_setu_tool_definitions",
    "register_setu_tools",
    "unregister_setu_tools",
    "SETU_TOOL_NAMES",
    # Fortune 工具
    "get_fortune_tool_definitions",
    "register_fortune_tools",
    "unregister_fortune_tools",
    "FORTUNE_TOOL_NAMES",
    # 综合操作
    "unregister_all_tools",
]
