"""Setu（随机图片）插件 - 主入口。

支持多 API 提供商（策略模式）、可配置的内容模式
（和谐/成人/混合）、多种发送模式（直接发送/模拟转发）、图片混淆重试、
智能补充机制、HTML 卡片包装（防审核）、LLM 工具调用、以及自定义 API 支持。

命令：
    来份色图              - 获取 1 张随机图片。
    来3份色图             - 获取 3 张随机图片。
    来份[标签]色图        - 获取带指定标签的 1 张随机图片。
    来5个白丝福利图       - 获取 5 张 tagged "白丝" 的图片。
    /setu [数量] [标签]   - 使用 /setu 命令获取图片，标签支持多标签（用,或，或空格分隔）。
    /setu_mode [模式]     - 设置当前会话的内容模式（sfw/r18/mix/clear），仅限管理员。
"""

from __future__ import annotations

import re
from pathlib import Path

import mcp.types

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools, register
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
        self._plugin_data_dir: Path = StarTools.get_data_dir(self.name)

    async def initialize(self) -> None:
        """初始化插件，注册 LLM 工具。"""
        try:
            llm_tools.add_func(
                name="get_setu_image",
                func_args=[
                    {
                        "name": "count",
                        "type": "integer",
                        "description": "Number of images to fetch. Default is 1.",
                    },
                    {
                        "name": "tags",
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of search tags. Pass as an array of strings.",
                    },
                ],
                desc=(
                    "Fetch random anime/illustration images. "
                    "Use this when users ask for images. "
                    "Supports count and tags."
                ),
                handler=self._llm_get_setu_handler,
            )
            tool = llm_tools.get_func("get_setu_image")
            if tool:
                tool.handler_module_path = __name__
        except (AttributeError, RuntimeError):
            logger.exception("LLM tool registration failed")

        try:
            cfg = SetuConfig(self.config)
            self._core = SetuCore(self, cfg, self._plugin_data_dir)
            await self._core.initialize()
        except (OSError, RuntimeError, ValueError):
            logger.exception("Setu core initialize failed")
            self._core = None

    async def terminate(self) -> None:
        """卸载插件，注销 LLM 工具。"""
        try:
            llm_tools.remove_func("get_setu_image")
        except (AttributeError, RuntimeError):
            logger.exception("LLM tool unregister failed")

    async def _llm_get_setu_handler(
        self,
        event: AstrMessageEvent,
        count=1,
        tags: list[str] | str | dict | None = None,
    ) -> mcp.types.CallToolResult:
        """LLM 工具处理器：获取色图并直接发送。"""
        if not self._core:
            return mcp.types.CallToolResult(
                content=[
                    mcp.types.TextContent(
                        type="text", text="插件尚未就绪，请稍后再试。"
                    )
                ]
            )
        try:
            # 处理可能被包装成字典的参数
            if isinstance(count, dict):
                count = count.get("value", 1)
            if isinstance(tags, dict):
                tags = tags.get("value", [])

            success, message = await self._core.handle_llm_tool(event, int(count), tags)
            return mcp.types.CallToolResult(
                content=[mcp.types.TextContent(type="text", text=message)]
            )
        except (TypeError, ValueError, RuntimeError) as e:
            logger.exception("LLM 工具获取色图失败")
            return mcp.types.CallToolResult(
                content=[
                    mcp.types.TextContent(type="text", text=f"获取图片失败：{str(e)}")
                ]
            )

    @filter.regex(COMMAND_PATTERN)
    async def get_random_picture(self, event: AstrMessageEvent):
        """处理色图请求命令，支持中文数字解析和标签。"""
        if not self._core:
            yield event.plain_result("插件尚未就绪，请稍后再试。")
            return
        match = re.match(COMMAND_PATTERN, event.message_str.strip())
        if not match:
            return

        cfg = SetuConfig(self.config)

        # 检查群聊是否被屏蔽
        if self._core and self._core.is_group_blocked(event):
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
        tag_str = match.group(3).strip()
        tags = cfg.resolve_tags(tag_str)

        if cfg.msg_fetching_enabled:
            yield event.plain_result(cfg.msg_fetching_text)
        try:
            # 获取生效的内容模式（优先会话配置）
            effective_content_mode = await self._core.get_effective_content_mode(event)
            is_r18 = self._core.determine_r18(effective_content_mode)
            downloaded = await self._core.fetch_and_download_images(num, tags, is_r18)
            async for result in self._core.send_images(event, downloaded, is_r18, tags):
                yield result
        except (OSError, RuntimeError, ValueError):
            logger.exception("get_random_picture failed")
            yield event.plain_result("获取图片失败，请稍后再试。")

    @filter.command("setu")
    async def setu_command(
        self, event: AstrMessageEvent, count: str = "1", *, tags: str = ""
    ):
        """/setu 命令处理器，作为正则匹配响应器的别名。

        用法：
            /setu              - 获取 1 张随机图片
            /setu 5            - 获取 5 张随机图片
            /setu 3 白丝       - 获取 3 张白丝图片
            /setu 白丝,萝莉    - 获取 1 张带白丝和萝莉标签的图片
            /setu 5 白丝 萝莉  - 获取 5 张带白丝和萝莉标签的图片
        """
        if not self._core:
            yield event.plain_result("插件尚未就绪，请稍后再试。")
            return
        cfg = SetuConfig(self.config)

        # 检查群聊是否被屏蔽
        if self._core and self._core.is_group_blocked(event):
            return

        max_count = cfg.max_count

        # 尝试解析数量，如果第一个参数是数字则作为数量，否则作为标签
        num_str = count
        num = parse_count(num_str)

        # 如果解析失败(num == -1)或参数不是数字，则将其视为标签的一部分
        extra_tag = ""
        if num == -1:
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

        if cfg.msg_fetching_enabled:
            yield event.plain_result(cfg.msg_fetching_text)
        try:
            # 获取生效的内容模式（优先会话配置）
            effective_content_mode = await self._core.get_effective_content_mode(event)
            is_r18 = self._core.determine_r18(effective_content_mode)
            downloaded = await self._core.fetch_and_download_images(
                num, parsed_tags, is_r18
            )
            async for result in self._core.send_images(
                event, downloaded, is_r18, parsed_tags
            ):
                yield result
        except (OSError, RuntimeError, ValueError):
            logger.exception("setu command failed")
            yield event.plain_result("获取图片失败，请稍后再试。")

    @filter.command("setu_mode")
    async def setu_mode_command(self, event: AstrMessageEvent, mode: str = ""):
        """设置当前会话的内容模式。

        用法：
            /setu_mode sfw    - 设置当前会话为全年龄模式
            /setu_mode r18    - 设置当前会话为 R18 模式
            /setu_mode mix    - 设置当前会话为混合模式
            /setu_mode clear  - 清除当前会话的覆盖设置，使用全局配置

        注意：此命令仅限管理员或超级管理员使用。
        """
        if not self._core:
            yield event.plain_result("插件尚未就绪，请稍后再试。")
            return

        # 检查权限（管理员或超级管理员）
        # AstrBot 提供了 event.is_admin() 和 event.is_super_user() 方法
        is_admin = False
        try:
            # 尝试多种方式检查权限
            if hasattr(event, "is_admin") and callable(getattr(event, "is_admin")):
                is_admin = event.is_admin()
            if (
                not is_admin
                and hasattr(event, "is_super_user")
                and callable(getattr(event, "is_super_user"))
            ):
                is_admin = event.is_super_user()
            # 检查 sender 的 role 属性
            if not is_admin and hasattr(event, "message_obj"):
                msg_obj = event.message_obj
                if hasattr(msg_obj, "sender") and hasattr(msg_obj.sender, "role"):
                    role = msg_obj.sender.role
                    if role in ("admin", "owner"):
                        is_admin = True
        except AttributeError:
            pass

        if not is_admin:
            yield event.plain_result("❌ 权限不足：此命令仅限管理员或超级管理员使用。")
            return

        mode = mode.strip().lower()
        if not mode:
            # 显示当前会话的配置状态
            session_id = event.get_session_id()
            is_group = bool(event.get_group_id())
            current_mode = await self._core.session_config.get_session_content_mode(
                session_id, is_group
            )
            global_mode = self._core.config.content_mode

            if current_mode:
                msg = (
                    f"📋 当前会话内容模式：\n"
                    f"   会话覆盖：{current_mode}\n"
                    f"   全局配置：{global_mode}\n"
                    f"   生效模式：{current_mode}\n\n"
                    f"可用命令：/setu_mode sfw|r18|mix|clear"
                )
            else:
                msg = (
                    f"📋 当前会话内容模式：\n"
                    f"   会话覆盖：未设置（使用全局配置）\n"
                    f"   全局配置：{global_mode}\n"
                    f"   生效模式：{global_mode}\n\n"
                    f"可用命令：/setu_mode sfw|r18|mix|clear"
                )
            yield event.plain_result(msg)
            return

        if mode not in ("sfw", "r18", "mix", "clear"):
            yield event.plain_result(
                "❌ 无效的模式。\n"
                "可用模式：sfw（全年龄）、r18（成人）、mix（混合）、clear（清除设置）"
            )
            return

        session_id = event.get_session_id()
        is_group = bool(event.get_group_id())

        if mode == "clear":
            success = await self._core.session_config.clear_session_content_mode(
                session_id, is_group
            )
            if success:
                yield event.plain_result(
                    "✅ 已清除当前会话的内容模式设置，将使用全局配置。"
                )
            else:
                yield event.plain_result("ℹ️ 当前会话没有设置覆盖，已在使用全局配置。")
        else:
            success = await self._core.session_config.set_session_content_mode(
                session_id, is_group, mode
            )
            if success:
                session_type = "群聊" if is_group else "私聊"
                yield event.plain_result(
                    f"✅ 已将当前{session_type}的内容模式设置为：{mode}\n"
                    f"此后发送的图片将使用此模式（优先于全局配置）。"
                )
            else:
                yield event.plain_result("❌ 设置失败，请稍后再试。")
