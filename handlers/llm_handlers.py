"""LLM 工具处理器模块。"""

from __future__ import annotations

import json
import re

import mcp.types

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from .command_handlers import CommandHandler


# 匹配 \uXXXX 格式的 Unicode 转义序列
_UNICODE_ESCAPE_PATTERN = re.compile(r"\\u([0-9a-fA-F]{4})")


def _decode_unicode_escapes(text: str) -> str:
    """解码字符串中的 Unicode 转义序列（如 \\u74f7\\u7b25\\u6728\\u684c -> 碧蓝档案）。

    只处理 \\uXXXX 格式的 Unicode 转义，避免过度解码其他转义序列（如 \\n, \\t 等）。
    """
    if not text or "\\u" not in text:
        return text
    try:
        # 先尝试使用 json.loads 解码（处理带引号的 JSON 字符串）
        if text.startswith('"') and text.endswith('"'):
            return json.loads(text)
        # 使用正则表达式只替换 \\uXXXX 格式的转义序列
        return _UNICODE_ESCAPE_PATTERN.sub(lambda m: chr(int(m.group(1), 16)), text)
    except (ValueError, UnicodeDecodeError):
        return text


class LlmHandlers:
    """LLM 工具处理器集合。"""

    def __init__(self, plugin):
        """初始化处理器。

        参数:
            plugin: SetuPlugin 实例
        """
        self.plugin = plugin
        self._cmd_handler: CommandHandler | None = None

    @property
    def core(self):
        """获取核心实例。"""
        return self.plugin._core

    @property
    def cmd_handler(self) -> CommandHandler:
        """获取命令处理器（惰性初始化）。"""
        if self._cmd_handler is None:
            self._cmd_handler = CommandHandler(self.core, self.core.config)
        return self._cmd_handler

    def _check_admin(self, event: AstrMessageEvent) -> bool:
        """检查用户是否为管理员。"""
        try:
            if hasattr(event, "is_admin") and callable(getattr(event, "is_admin")):
                if event.is_admin():
                    return True
            if hasattr(event, "is_super_user") and callable(
                getattr(event, "is_super_user")
            ):
                if event.is_super_user():
                    return True
            if hasattr(event, "message_obj"):
                msg_obj = event.message_obj
                if hasattr(msg_obj, "sender") and hasattr(msg_obj.sender, "role"):
                    role = msg_obj.sender.role
                    if role in ("admin", "owner"):
                        return True
        except AttributeError:
            pass
        return False

    async def _llm_get_setu_handler(
        self,
        event: AstrMessageEvent,
        count=1,
        tags: list[str] | str | dict | None = None,
    ) -> mcp.types.CallToolResult:
        """LLM 工具处理器：获取色图并直接发送。"""
        if not self.core:
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

            # 构建 tags 字符串，确保所有元素为字符串，并解码 Unicode 转义
            if isinstance(tags, list):
                decoded_tags = [_decode_unicode_escapes(str(tag)) for tag in tags]
                tags_str = " ".join(decoded_tags)
            else:
                tags_str = _decode_unicode_escapes(str(tags or ""))

            # 跟踪发送结果
            sent_count = 0
            has_error = False

            async for result in self.cmd_handler.handle_setu_command(
                event, count=str(count), tags=tags_str
            ):
                if result is not None:
                    # 检查内部成功标记
                    if isinstance(result, dict) and result.get("send_success"):
                        sent_count = result.get("image_count", 0)
                        continue
                    try:
                        await self.plugin.context.send_message(
                            event.unified_msg_origin, result
                        )
                        # 注意：这里不递增 sent_count，因为 result 可能是错误消息
                        # 只有成功标记中的 image_count 才是实际发送的图片数
                    except Exception as exc:
                        has_error = True
                        logger.warning("[llm_tool] Failed to send: %s", exc)

            # 根据实际结果返回不同消息
            if sent_count == 0:
                if has_error:
                    msg = "图片发送失败"
                else:
                    msg = "没有获取到图片或发送被阻止"
            else:
                msg = f"已成功发送 {sent_count} 张图片"

            return mcp.types.CallToolResult(
                content=[mcp.types.TextContent(type="text", text=msg)]
            )
        except (TypeError, ValueError, RuntimeError) as e:
            logger.exception("LLM 工具获取色图失败")
            return mcp.types.CallToolResult(
                content=[
                    mcp.types.TextContent(type="text", text=f"获取图片失败：{str(e)}")
                ]
            )

    async def _llm_get_content_mode_handler(
        self,
        event: AstrMessageEvent,
    ) -> mcp.types.CallToolResult:
        """LLM 工具处理器：查看当前内容分级。"""
        if not self.core:
            return mcp.types.CallToolResult(
                content=[
                    mcp.types.TextContent(
                        type="text", text="插件尚未就绪，请稍后再试。"
                    )
                ]
            )
        try:
            session_id = event.get_session_id()
            is_group = bool(event.get_group_id())

            # 获取会话级别的覆盖配置
            session_mode = await self.core.session_config.get_session_content_mode(
                session_id, is_group
            )
            # 获取全局配置
            global_mode = self.core.config.content_mode
            # 获取实际生效的模式
            effective_mode = await self.core.get_effective_content_mode(event)

            session_type = "群聊" if is_group else "私聊"

            if session_mode:
                msg = (
                    f"当前{session_type}的内容分级设置：\n"
                    f"- 会话覆盖：{session_mode}\n"
                    f"- 全局配置：{global_mode}\n"
                    f"- 生效模式：{effective_mode}\n\n"
                    f"说明：此会话已设置独立的内容分级，优先于全局配置。"
                )
            else:
                msg = (
                    f"当前{session_type}的内容分级设置：\n"
                    f"- 会话覆盖：未设置（使用全局配置）\n"
                    f"- 全局配置：{global_mode}\n"
                    f"- 生效模式：{effective_mode}\n\n"
                    f"说明：此会话使用全局内容分级配置。"
                )

            return mcp.types.CallToolResult(
                content=[mcp.types.TextContent(type="text", text=msg)]
            )
        except Exception as e:
            logger.exception("LLM 工具查看内容分级失败")
            return mcp.types.CallToolResult(
                content=[
                    mcp.types.TextContent(
                        type="text", text=f"查看内容分级失败：{str(e)}"
                    )
                ]
            )

    async def _llm_set_content_mode_handler(
        self,
        event: AstrMessageEvent,
        mode: str | dict | None = None,
    ) -> mcp.types.CallToolResult:
        """LLM 工具处理器：设置内容分级。"""
        if not self.core:
            return mcp.types.CallToolResult(
                content=[
                    mcp.types.TextContent(
                        type="text", text="插件尚未就绪，请稍后再试。"
                    )
                ]
            )

        # 检查权限（管理员或超级管理员）
        if not self._check_admin(event):
            return mcp.types.CallToolResult(
                content=[
                    mcp.types.TextContent(
                        type="text",
                        text="❌ 权限不足：设置内容分级需要管理员或超级管理员权限。",
                    )
                ]
            )

        try:
            # 处理可能被包装成字典的参数
            if isinstance(mode, dict):
                mode = mode.get("value", "")
            if not mode:
                return mcp.types.CallToolResult(
                    content=[
                        mcp.types.TextContent(
                            type="text",
                            text="❌ 请指定要设置的内容分级：sfw（全年龄）、r18（成人）、mix（混合）或 clear（清除设置）。",
                        )
                    ]
                )

            mode = str(mode).strip().lower()
            if mode not in ("sfw", "r18", "mix", "clear"):
                return mcp.types.CallToolResult(
                    content=[
                        mcp.types.TextContent(
                            type="text",
                            text=f"❌ 无效的模式 '{mode}'。\n可用模式：sfw（全年龄）、r18（成人）、mix（混合）、clear（清除设置）",
                        )
                    ]
                )

            session_id = event.get_session_id()
            is_group = bool(event.get_group_id())
            session_type = "群聊" if is_group else "私聊"

            if mode == "clear":
                success = await self.core.session_config.clear_session_content_mode(
                    session_id, is_group
                )
                if success:
                    global_mode = self.core.config.content_mode
                    msg = (
                        f"✅ 已清除当前{session_type}的内容分级设置，将使用全局配置。\n"
                        f"当前全局配置为：{global_mode}"
                    )
                else:
                    msg = "ℹ️ 当前会话没有设置覆盖，已在使用全局配置。"
            else:
                success = await self.core.session_config.set_session_content_mode(
                    session_id, is_group, mode
                )
                if success:
                    msg = (
                        f"✅ 已将当前{session_type}的内容分级设置为：{mode}\n"
                        f"此后发送的图片将使用此模式（优先于全局配置）。"
                    )
                else:
                    msg = "❌ 设置失败，请稍后再试。"

            return mcp.types.CallToolResult(
                content=[mcp.types.TextContent(type="text", text=msg)]
            )
        except Exception as e:
            logger.exception("LLM 工具设置内容分级失败")
            return mcp.types.CallToolResult(
                content=[
                    mcp.types.TextContent(
                        type="text", text=f"设置内容分级失败：{str(e)}"
                    )
                ]
            )

    async def _llm_set_r18_docx_mode_handler(
        self,
        event: AstrMessageEvent,
        enabled: bool | dict | None = None,
    ) -> mcp.types.CallToolResult:
        """LLM 工具处理器：设置会话级别的 R18 Docx 模式。"""
        if not self.core:
            return mcp.types.CallToolResult(
                content=[
                    mcp.types.TextContent(
                        type="text", text="插件尚未就绪，请稍后再试。"
                    )
                ]
            )

        if not self._check_admin(event):
            return mcp.types.CallToolResult(
                content=[
                    mcp.types.TextContent(
                        type="text",
                        text="❌ 权限不足：设置 R18 Docx 模式需要管理员或超级管理员权限。",
                    )
                ]
            )

        try:
            # 处理可能被包装成字典的参数
            if isinstance(enabled, dict):
                enabled = enabled.get("value")

            session_id = event.get_session_id()
            is_group = bool(event.get_group_id())
            session_type = "群聊" if is_group else "私聊"

            # 获取当前全局配置
            global_mode = self.core.config.r18_docx_mode

            if enabled == "clear" or enabled is None:
                # 清除会话设置
                success = await self.core.session_config.clear_session_r18_docx_mode(
                    session_id, is_group
                )
                if success:
                    msg = (
                        f"✅ 已清除当前{session_type}的 R18 Docx 模式设置，将使用全局配置。\n"
                        f"当前全局配置为：{'启用' if global_mode else '禁用'}"
                    )
                else:
                    msg = "ℹ️ 当前会话没有设置覆盖，已在使用全局配置。"
            else:
                # 转换为布尔值
                bool_enabled = bool(enabled)
                success = await self.core.session_config.set_session_r18_docx_mode(
                    session_id, is_group, bool_enabled
                )
                if success:
                    msg = (
                        f"✅ 已将当前{session_type}的 R18 Docx 模式设置为：{'启用' if bool_enabled else '禁用'}\n"
                        f"此后发送的 R18 图片将{'打包为 DOCX 文件' if bool_enabled else '直接发送'}（优先于全局配置）。"
                    )
                else:
                    msg = "❌ 设置失败，请稍后再试。"

            return mcp.types.CallToolResult(
                content=[mcp.types.TextContent(type="text", text=msg)]
            )
        except Exception as e:
            logger.exception("LLM 工具设置 R18 Docx 模式失败")
            return mcp.types.CallToolResult(
                content=[
                    mcp.types.TextContent(
                        type="text", text=f"设置 R18 Docx 模式失败：{str(e)}"
                    )
                ]
            )

    async def _llm_set_auto_revoke_handler(
        self,
        event: AstrMessageEvent,
        enabled: bool | dict | None = None,
    ) -> mcp.types.CallToolResult:
        """LLM 工具处理器：设置会话级别的自动撤回。"""
        if not self.core:
            return mcp.types.CallToolResult(
                content=[
                    mcp.types.TextContent(
                        type="text", text="插件尚未就绪，请稍后再试。"
                    )
                ]
            )

        if not self._check_admin(event):
            return mcp.types.CallToolResult(
                content=[
                    mcp.types.TextContent(
                        type="text",
                        text="❌ 权限不足：设置自动撤回需要管理员或超级管理员权限。",
                    )
                ]
            )

        try:
            # 处理可能被包装成字典的参数
            if isinstance(enabled, dict):
                enabled = enabled.get("value")

            session_id = event.get_session_id()
            is_group = bool(event.get_group_id())
            session_type = "群聊" if is_group else "私聊"

            # 获取当前全局配置
            global_mode = self.core.config.auto_revoke_r18
            delay = self.core.config.auto_revoke_delay

            if enabled == "clear" or enabled is None:
                # 清除会话设置
                success = await self.core.session_config.clear_session_auto_revoke_r18(
                    session_id, is_group
                )
                if success:
                    msg = (
                        f"✅ 已清除当前{session_type}的自动撤回设置，将使用全局配置。\n"
                        f"当前全局配置为：{'启用' if global_mode else '禁用'}（延迟 {delay} 秒）"
                    )
                else:
                    msg = "ℹ️ 当前会话没有设置覆盖，已在使用全局配置。"
            else:
                # 转换为布尔值
                bool_enabled = bool(enabled)
                success = await self.core.session_config.set_session_auto_revoke_r18(
                    session_id, is_group, bool_enabled
                )
                if success:
                    msg = (
                        f"✅ 已将当前{session_type}的自动撤回设置为：{'启用' if bool_enabled else '禁用'}\n"
                        f"此后发送的 R18 内容将{'在 {delay} 秒后自动撤回' if bool_enabled else '不会自动撤回'}（优先于全局配置）。"
                    )
                else:
                    msg = "❌ 设置失败，请稍后再试。"

            return mcp.types.CallToolResult(
                content=[mcp.types.TextContent(type="text", text=msg)]
            )
        except Exception as e:
            logger.exception("LLM 工具设置自动撤回失败")
            return mcp.types.CallToolResult(
                content=[
                    mcp.types.TextContent(
                        type="text", text=f"设置自动撤回失败：{str(e)}"
                    )
                ]
            )
