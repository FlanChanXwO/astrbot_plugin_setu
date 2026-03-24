"""今日运势模块。

集成到 Setu 插件的今日运势功能。
参照 Java 版本 winefox-bot FortunePlugin 实现。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from astrbot.api import logger

from .core import FortuneCore
from .handlers import FortuneCommandHandler
from .llm_handlers import FortuneLlmHandler
from .renderer import FortuneRenderer
from .session_config import FortuneSessionConfig


class FortuneManager:
    """今日运势管理器。

    封装今日运势的所有功能，便于在主插件中集成。
    """

    def __init__(self, plugin, data_dir: Path, config: dict[str, Any]):
        self.plugin = plugin
        self.data_dir = data_dir
        self.config = config

        self._core: FortuneCore | None = None
        self._renderer: FortuneRenderer | None = None
        self._session_config: FortuneSessionConfig | None = None
        self._cmd_handler: FortuneCommandHandler | None = None
        self._llm_handler: FortuneLlmHandler | None = None

    async def initialize(self) -> None:
        """初始化今日运势模块。"""
        logger.info("[fortune] Initializing FortuneManager...")

        # 初始化核心组件
        self._core = FortuneCore(self.data_dir, self.config)
        await self._core.initialize()

        self._renderer = FortuneRenderer()
        self._session_config = FortuneSessionConfig(self.data_dir)
        await self._session_config.initialize()

        # 初始化处理器
        self._cmd_handler = FortuneCommandHandler(
            self.plugin._core,  # SetuCore
            self.plugin.config,  # SetuConfig
            self._core,
            self._renderer,
            self._session_config,
        )

        self._llm_handler = FortuneLlmHandler(
            self.plugin,
            self.plugin._core,
            self._core,
            self._session_config,
        )

        logger.info("[fortune] FortuneManager initialized successfully")

    def terminate(self) -> None:
        """清理资源。"""
        logger.info("[fortune] FortuneManager terminated")

    @property
    def cmd_handler(self) -> FortuneCommandHandler | None:
        """获取命令处理器。"""
        return self._cmd_handler

    @property
    def llm_handler(self) -> FortuneLlmHandler | None:
        """获取 LLM 处理器。"""
        return self._llm_handler

    @property
    def core(self) -> FortuneCore | None:
        """获取核心实例。"""
        return self._core

    @property
    def session_config(self) -> FortuneSessionConfig | None:
        """获取会话配置。"""
        return self._session_config


__all__ = [
    "FortuneManager",
    "FortuneCore",
    "FortuneRenderer",
    "FortuneSessionConfig",
    "FortuneCommandHandler",
    "FortuneLlmHandler",
]
