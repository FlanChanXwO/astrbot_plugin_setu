"""Setu（随机图片）插件 - 主入口。

支持多 API 提供商、可配置的内容模式、多种发送模式、
HTML 卡片包装、LLM 工具调用、以及自定义 API 支持。
集成今日运势功能。
"""

from __future__ import annotations

from pathlib import Path

from astrbot.api.event import filter
from astrbot.api.star import Context, Star, StarTools
from astrbot.core import AstrBotConfig
from astrbot.core.provider.register import llm_tools

from .config import SetuConfig
from .constants import COMMAND_PATTERN, FORTUNE_PATTERN
from .core import SetuCore
from .fortune import FortuneManager
from .handlers import CommandHandler, LlmHandlers


class SetuPlugin(Star):
    """色图插件主类（含今日运势）。"""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context, config)
        self.context = context
        self.config = config
        self._core: SetuCore | None = None
        self._plugin_data_dir: Path = StarTools.get_data_dir(self.name)
        self._cmd_handler: CommandHandler | None = None
        self._llm_handlers: LlmHandlers | None = None
        self._fortune_manager: FortuneManager | None = None

    async def initialize(self) -> None:
        """初始化插件。"""
        cfg = SetuConfig(self.config)
        self._core = SetuCore(self, cfg, self._plugin_data_dir)
        await self._core.initialize()

        self._cmd_handler = CommandHandler(self._core, cfg)
        self._llm_handlers = LlmHandlers(self)

        # 初始化今日运势模块
        fortune_cfg = getattr(cfg, "fortune", {})
        if isinstance(fortune_cfg, dict) and fortune_cfg.get("enabled", True):
            self._fortune_manager = FortuneManager(
                self, self._plugin_data_dir / "fortune", fortune_cfg
            )
            await self._fortune_manager.initialize()
            await self._register_fortune_llm_tools()

        # 注册 Setu LLM 工具
        await self._register_setu_llm_tools()

    async def _register_setu_llm_tools(self) -> None:
        """注册 Setu 相关的 LLM 工具。"""
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

    async def _register_fortune_llm_tools(self) -> None:
        """注册今日运势的 LLM 工具。"""
        if not self._fortune_manager or not self._fortune_manager.llm_handler:
            return

        handler = self._fortune_manager.llm_handler

        tools = [
            (
                "get_today_fortune",
                handler.llm_get_fortune,
                [],
                "获取今日运势。",
            ),
            (
                "refresh_my_fortune",
                handler.llm_refresh_fortune,
                [],
                "刷新我的今日运势（管理员）。",
            ),
            (
                "refresh_group_fortune",
                handler.llm_refresh_group_fortune,
                [],
                "刷新群组今日运势（管理员）。",
            ),
            (
                "refresh_all_fortune",
                handler.llm_refresh_all_fortune,
                [],
                "刷新全局今日运势（超级管理员）。",
            ),
            (
                "get_fortune_config",
                handler.llm_get_fortune_config,
                [],
                "获取今日运势配置。",
            ),
            (
                "set_fortune_config",
                handler.llm_set_fortune_config,
                [
                    {
                        "name": "tags",
                        "type": "string",
                        "description": "标签，如'少女,可爱'。留空则清除设置。",
                    },
                    {
                        "name": "mode",
                        "type": "string",
                        "enum": ["sfw", "r18", "mix"],
                        "description": "内容模式。",
                    },
                ],
                "设置今日运势配置（管理员）。",
            ),
        ]

        for name, h, args, desc in tools:
            try:
                llm_tools.add_func(name=name, func_args=args, desc=desc, handler=h)
                tool = llm_tools.get_func(name)
                if tool:
                    tool.handler_module_path = __name__
            except (AttributeError, RuntimeError):
                pass

    async def terminate(self) -> None:
        """卸载插件。"""
        if self._core:
            self._core.terminate()
        if self._fortune_manager:
            self._fortune_manager.terminate()

        # 注销 LLM 工具
        for name in [
            "get_setu_image",
            "get_setu_content_mode",
            "set_setu_content_mode",
            "set_setu_r18_docx_mode",
            "set_setu_auto_revoke",
            "get_today_fortune",
            "refresh_my_fortune",
            "refresh_group_fortune",
            "refresh_all_fortune",
            "get_fortune_config",
            "set_fortune_config",
        ]:
            try:
                llm_tools.remove_func(name)
            except (AttributeError, RuntimeError):
                pass

    # ==================== Setu 命令 ====================

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

    # ==================== Fortune 命令 ====================

    @filter.regex(FORTUNE_PATTERN)
    async def fortune_command(self, event):
        """处理今日运势命令 (/jrys, /今日运势)。"""
        if self._fortune_manager and self._fortune_manager.cmd_handler:
            async for result in self._fortune_manager.cmd_handler.handle_fortune(event):
                yield result

    @filter.command(command_name="今日运势", alias={"jrys"})
    async def jrys_command(self, event):
        """处理 /jrys 命令。"""
        if self._fortune_manager and self._fortune_manager.cmd_handler:
            async for result in self._fortune_manager.cmd_handler.handle_fortune(event):
                yield result

    @filter.command("刷新今日运势", alias={"刷新jrys", "flush_jrys"})
    async def refresh_fortune_command(self, event):
        """处理 /刷新今日运势 命令。"""
        if self._fortune_manager and self._fortune_manager.cmd_handler:
            async for (
                result
            ) in self._fortune_manager.cmd_handler.handle_refresh_fortune(event):
                yield result

    @filter.command("刷新本群今日运势", alias={"刷新本群jrys", "flush_group_jrys"})
    async def refresh_group_fortune_command(self, event):
        """处理 /刷新本群今日运势 命令。"""
        if self._fortune_manager and self._fortune_manager.cmd_handler:
            async for (
                result
            ) in self._fortune_manager.cmd_handler.handle_refresh_group_fortune(event):
                yield result

    @filter.command("刷新全局今日运势", alias={"刷新全局jrys", "flush_all_jrys"})
    async def refresh_all_fortune_command(self, event):
        """处理 /刷新全局今日运势 命令。"""
        if self._fortune_manager and self._fortune_manager.cmd_handler:
            async for (
                result
            ) in self._fortune_manager.cmd_handler.handle_refresh_all_fortune(event):
                yield result

    @filter.command("jrys_config")
    async def jrys_config_command(self, event, args: str = ""):
        """处理 /jrys_config 命令。"""
        if self._fortune_manager and self._fortune_manager.cmd_handler:
            async for result in self._fortune_manager.cmd_handler.handle_fortune_config(
                event, args
            ):
                yield result
