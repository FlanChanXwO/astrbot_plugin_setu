"""Setu（随机图片）插件 - 主入口。

支持多 API 提供商、可配置的内容模式、多种发送模式、
HTML 卡片包装、LLM 工具调用、以及自定义 API 支持。
"""

from __future__ import annotations

from pathlib import Path

from astrbot.api.event import filter
from astrbot.api.star import Context, Star, StarTools
from astrbot.core import AstrBotConfig
from astrbot.core.provider.register import llm_tools

from .config import SetuConfig
from .constants import COMMAND_PATTERN
from .core import SetuCore
from .handlers import CommandHandler, LlmHandlers


class SetuPlugin(Star):
    """色图插件主类。"""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context, config)
        self.context = context
        self.config = config
        self._core: SetuCore | None = None
        self._plugin_data_dir: Path = StarTools.get_data_dir(self.name)
        self._cmd_handler: CommandHandler | None = None
        self._llm_handlers: LlmHandlers | None = None

    async def initialize(self) -> None:
        """初始化插件。"""
        cfg = SetuConfig(self.config)
        self._core = SetuCore(self, cfg, self._plugin_data_dir)
        await self._core.initialize()

        self._cmd_handler = CommandHandler(self._core, cfg)
        self._llm_handlers = LlmHandlers(self)

        # 注册 LLM 工具
        tools = [
            (
                "get_setu_image",
                self._llm_handlers._llm_get_setu_handler,
                [
                    {
                        "name": "count",
                        "type": "integer",
                        "description": "Number of images.",
                    },
                    {"name": "tags", "type": "array", "items": {"type": "string"}},
                ],
                "Fetch random anime images.",
            ),
            (
                "get_setu_content_mode",
                self._llm_handlers._llm_get_content_mode_handler,
                [],
                "Get content mode.",
            ),
            (
                "set_setu_content_mode",
                self._llm_handlers._llm_set_content_mode_handler,
                [
                    {
                        "name": "mode",
                        "type": "string",
                        "enum": ["sfw", "r18", "mix", "clear"],
                    },
                ],
                "Set content mode.",
            ),
            (
                "set_setu_r18_docx_mode",
                self._llm_handlers._llm_set_r18_docx_mode_handler,
                [
                    {"name": "enabled", "type": "boolean"},
                ],
                "Set R18 Docx mode.",
            ),
            (
                "set_setu_auto_revoke",
                self._llm_handlers._llm_set_auto_revoke_handler,
                [
                    {"name": "enabled", "type": "boolean"},
                ],
                "Set auto-revoke.",
            ),
        ]

        for name, handler, args, desc in tools:
            try:
                llm_tools.add_func(
                    name=name, func_args=args, desc=desc, handler=handler
                )
                tool = llm_tools.get_func(name)
                if tool:
                    tool.handler_module_path = __name__
            except (AttributeError, RuntimeError):
                pass

    async def terminate(self) -> None:
        """卸载插件。"""
        if self._core:
            self._core.terminate()
        for name in [
            "get_setu_image",
            "get_setu_content_mode",
            "set_setu_content_mode",
            "set_setu_r18_docx_mode",
            "set_setu_auto_revoke",
        ]:
            try:
                llm_tools.remove_func(name)
            except (AttributeError, RuntimeError):
                pass

    @filter.regex(COMMAND_PATTERN)
    async def get_random_picture(self, event):
        """处理色图请求命令。"""
        if self._cmd_handler:
            async for result in self._cmd_handler.handle_random_picture(event):
                yield result

    @filter.command("setu")
    async def setu_command(self, event, count: str = "1", *, tags: str = ""):
        """处理 /setu 命令。"""
        if self._cmd_handler:
            async for result in self._cmd_handler.handle_setu_command(
                event, count, tags=tags
            ):
                yield result

    @filter.command("setu_mode")
    async def setu_mode_command(self, event, mode: str = ""):
        """处理 /setu_mode 命令。"""
        if self._cmd_handler:
            async for result in self._cmd_handler.handle_setu_mode(event, mode):
                yield result
