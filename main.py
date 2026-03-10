"""Setu（随机图片）插件 - 主入口。

从 Java WineFoxBot SetuPlugin 迁移而来。
支持多 API 提供商（策略模式）、可配置的内容模式
（和谐/成人/混合）、多种发送模式（直接发送/模拟转发）、图片混淆重试、
智能补充机制、HTML 卡片包装（防审核）、LLM 工具调用、以及自定义 API 支持。

命令：
    来份色图              - 获取 1 张随机图片。
    来3份色图             - 获取 3 张随机图片。
    来份[标签]色图        - 获取带指定标签的 1 张随机图片。
    来5个白丝福利图       - 获取 5 张 tagged "白丝" 的图片。
    /setu [数量] [标签]   - 使用 /setu 命令获取图片，标签支持多标签（用,或，或空格分隔）。
"""
from __future__ import annotations

import re

import mcp.types

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register
from astrbot.core import AstrBotConfig
from astrbot.core.provider.register import llm_tools

from .config import SetuConfig, parse_count
from .constants import COMMAND_PATTERN
from .core import SetuCore


@register("astrbot_plugin_setu", "WineFox Migrate", "瑟瑟功能插件", "2.1.0")
class SetuPlugin(Star):
    """支持多提供商、HTML卡片包装、LLM工具调用和自定义API的色图插件。"""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context, config)
        self.context = context
        self.config = config
        self._core: SetuCore | None = None

    async def initialize(self) -> None:
        """初始化插件，注册 LLM 工具。"""
        # 注册 LLM 工具
        llm_tools.add_func(
            name="get_setu_image",
            func_args=[
                {"name": "count", "type": "integer", "description": "要获取的图片数量，默认为1"},
                {"name": "tags", "type": "string", "description": "搜索标签，多个标签用逗号分隔，例如：白丝,萝莉"},
            ],
            desc="获取随机动漫/插画图片（色图）。当用户想要看图片、anime pictures 或要求发图时调用。支持指定数量和标签。",
            handler=self._llm_get_setu_handler,
        )
        tool = llm_tools.get_func("get_setu_image")
        if tool:
            tool.handler_module_path = __name__

        # 初始化核心处理器
        cfg = SetuConfig(self.config)
        self._core = SetuCore(self, cfg)

    async def terminate(self) -> None:
        """卸载插件，注销 LLM 工具。"""
        llm_tools.remove_func("get_setu_image")

    async def _llm_get_setu_handler(
        self, event: AstrMessageEvent, count=1, tags=""
    ) -> mcp.types.CallToolResult:
        """LLM 工具处理器：获取色图并直接发送。"""
        try:
            # 处理可能被包装成字典的参数
            if isinstance(count, dict):
                count = count.get("value", 1)
            if isinstance(tags, dict):
                tags = tags.get("value", "")

            success, message = await self._core.handle_llm_tool(event, int(count), str(tags))
            return mcp.types.CallToolResult(
                content=[mcp.types.TextContent(type="text", text=message)]
            )
        except Exception as e:
            logger.exception("LLM 工具获取色图失败")
            return mcp.types.CallToolResult(
                content=[mcp.types.TextContent(type="text", text=f"获取图片失败：{str(e)}")]
            )

    @filter.regex(COMMAND_PATTERN)
    async def get_random_picture(self, event: AstrMessageEvent):
        """处理色图请求命令，支持中文数字解析和标签。"""
        match = re.match(COMMAND_PATTERN, event.message_str.strip())
        if not match:
            return

        cfg = SetuConfig(self.config)

        # 检查群聊是否被屏蔽
        if self._core and self._core._is_group_blocked(event):
            return

        # 解析数量
        num_str = match.group(2)
        num = parse_count(num_str)
        max_count = cfg.max_count

        if num < 1 or num > max_count:
            if num == -1:
                yield event.plain_result(
                    f"数量解析失败，请使用数字或中文数字，图片数量必须在1-{max_count}之间"
                )
            elif num > max_count:
                yield event.plain_result(f"一次最多只能获取{max_count}张哦~")
            else:
                yield event.plain_result(f"图片数量必须在1-{max_count}之间哦~")
            return

        # 解析标签
        tag_str = match.group(4).strip()
        tags = cfg.resolve_tags(tag_str)

        # 处理请求
        yield event.plain_result("正在获取图片，请稍候...")

        is_r18 = self._core._determine_r18(cfg.content_mode)
        downloaded = await self._core.fetch_and_download_images(num, tags, is_r18)

        async for result in self._core.send_images(event, downloaded, is_r18):
            yield result

    @filter.command("setu")
    async def setu_command(self, event: AstrMessageEvent, count: str = "1", *, tags: str = ""):
        """/setu 命令处理器，作为正则匹配响应器的别名。

        用法：
            /setu              - 获取 1 张随机图片
            /setu 5            - 获取 5 张随机图片
            /setu 3 白丝       - 获取 3 张白丝图片
            /setu 白丝,萝莉    - 获取 1 张带白丝和萝莉标签的图片
            /setu 5 白丝 萝莉  - 获取 5 张带白丝和萝莉标签的图片
        """
        cfg = SetuConfig(self.config)

        # 检查群聊是否被屏蔽
        if self._core and self._core._is_group_blocked(event):
            return

        max_count = cfg.max_count

        # 尝试解析数量，如果第一个参数是数字则作为数量，否则作为标签
        num_str = count
        num = parse_count(num_str)

        # 如果第一个参数不是有效数字，则将其视为标签的一部分
        extra_tag = ""
        if num < 1:
            num = 1
            extra_tag = count

        # 合并标签（命令参数标签 + 位置参数标签）
        all_tags = tags
        if extra_tag:
            all_tags = f"{extra_tag} {all_tags}".strip()

        # 限制数量
        if num > max_count:
            yield event.plain_result(f"一次最多只能获取{max_count}张哦~")
            return

        # 解析标签（支持,，和空格分隔）
        parsed_tags = cfg.resolve_tags(all_tags)

        # 处理请求
        yield event.plain_result("正在获取图片，请稍候...")

        is_r18 = self._core._determine_r18(cfg.content_mode)
        downloaded = await self._core.fetch_and_download_images(num, parsed_tags, is_r18)

        async for result in self._core.send_images(event, downloaded, is_r18):
            yield result
