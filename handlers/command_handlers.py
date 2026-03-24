"""命令处理器。"""

from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from ..config import SetuConfig, parse_count
from ..constants import COMMAND_PATTERN

if TYPE_CHECKING:
    from ..core import SetuCore


class CommandHandler:
    """命令处理器。"""

    def __init__(self, core: SetuCore, config: SetuConfig):
        self._core = core
        self._config = config

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

    async def handle_random_picture(self, event: AstrMessageEvent):
        """处理色图请求命令。"""
        if not self._core:
            yield event.plain_result("插件尚未就绪，请稍后再试。")
            return

        # 限流检查：每个用户同时只能有一个请求
        if not await self._core.rate_limiter.acquire(event):
            yield event.plain_result("你有一个请求正在处理中，请稍后再试~")
            return

        try:
            async for result in self._handle_random_picture_internal(event):
                yield result
        finally:
            # 无论成功或失败，都释放锁
            await self._core.rate_limiter.release(event)

    async def _handle_random_picture_internal(self, event: AstrMessageEvent):
        """处理色图请求命令的内部逻辑。"""
        match = re.match(COMMAND_PATTERN, event.message_str.strip())
        if not match:
            return

        if self._core.is_group_blocked(event):
            return

        num_str = match.group(2)
        num = parse_count(num_str)
        max_count = self._config.max_count

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

        tag_str = match.group(4).strip()
        tags = self._config.resolve_tags(tag_str)

        if self._config.msg_fetching_enabled:
            yield event.plain_result(self._config.msg_fetching_text)

        try:
            effective_content_mode = await self._core.get_effective_content_mode(event)
            is_r18 = self._core.determine_r18(effective_content_mode)
            logger.debug("num = %d invoke params = %s , r18 = %s", num, tags, is_r18)

            # 检查是否使用 URL 发送模式
            if self._config.url_send_mode:
                # URL 模式：获取 URL 并直接发送
                provider = self._core._get_provider()
                if provider:
                    img_urls = await provider.fetch_image_urls(
                        num=num, tags=tags, r18=is_r18, exclude_ai=self._config.exclude_ai
                    )
                    async for result in self._core.send_images_by_url(
                        event, img_urls, is_r18, tags
                    ):
                        yield result
                else:
                    yield event.plain_result("没有可用的图片源，请联系管理员。")
            else:
                # 正常模式：下载后发送
                downloaded = await asyncio.wait_for(
                    self._core.fetch_and_download_images(num, tags, is_r18), timeout=60.0
                )
                if not downloaded:
                    tags_info = f"标签: {', '.join(tags)}" if tags else ""
                    yield event.plain_result(
                        f"未找到{tags_info}符合要求的图片，请尝试其他标签或检查标签拼写~"
                    )
                    return

                async for result in self._core.send_images(event, downloaded, is_r18, tags):
                    yield result
        except asyncio.TimeoutError:
            logger.warning("get_random_picture timeout (>60s)")
            yield event.plain_result("获取图片超时，网络可能不稳定，请稍后再试。")
        except (OSError, RuntimeError, ValueError):
            logger.exception("get_random_picture failed")
            yield event.plain_result("获取图片失败，网络或服务异常，请稍后再试。")

    async def handle_setu_command(
        self, event: AstrMessageEvent, count: str = "1", *, tags: str = ""
    ):
        """处理 /setu 命令。"""
        if not self._core:
            yield event.plain_result("插件尚未就绪，请稍后再试。")
            return

        # 限流检查：每个用户同时只能有一个请求
        if not await self._core.rate_limiter.acquire(event):
            yield event.plain_result("你有一个请求正在处理中，请稍后再试~")
            return

        try:
            async for result in self._handle_setu_command_internal(event, count, tags=tags):
                yield result
        finally:
            await self._core.rate_limiter.release(event)

    async def _handle_setu_command_internal(
        self, event: AstrMessageEvent, count: str = "1", *, tags: str = ""
    ):
        """处理 /setu 命令的内部逻辑。"""
        if self._core.is_group_blocked(event):
            return

        max_count = self._config.max_count
        num_str = count
        num = parse_count(num_str)

        extra_tag = ""
        if num == -1:
            num = 1
            extra_tag = count

        all_tags = tags
        if extra_tag:
            all_tags = f"{extra_tag} {all_tags}".strip()

        if num > max_count:
            yield event.plain_result(f"一次最多只能获取{max_count}张哦~")
            return

        parsed_tags = self._config.resolve_tags(all_tags)

        if self._config.msg_fetching_enabled:
            yield event.plain_result(self._config.msg_fetching_text)

        try:
            effective_content_mode = await self._core.get_effective_content_mode(event)
            is_r18 = self._core.determine_r18(effective_content_mode)

            # 检查是否使用 URL 发送模式
            if self._config.url_send_mode:
                provider = self._core._get_provider()
                if provider:
                    img_urls = await provider.fetch_image_urls(
                        num=num, tags=parsed_tags, r18=is_r18, exclude_ai=self._config.exclude_ai
                    )
                    async for result in self._core.send_images_by_url(
                        event, img_urls, is_r18, parsed_tags
                    ):
                        yield result
                else:
                    yield event.plain_result("没有可用的图片源，请联系管理员。")
            else:
                downloaded = await asyncio.wait_for(
                    self._core.fetch_and_download_images(num, parsed_tags, is_r18),
                    timeout=60.0,
                )
                if not downloaded:
                    tags_info = f"标签: {', '.join(parsed_tags)}" if parsed_tags else ""
                    yield event.plain_result(
                        f"未找到{tags_info}符合要求的图片，请尝试其他标签或检查标签拼写~"
                    )
                    return

                async for result in self._core.send_images(
                    event, downloaded, is_r18, parsed_tags
                ):
                    yield result
        except asyncio.TimeoutError:
            logger.warning("setu command timeout (>60s)")
            yield event.plain_result("获取图片超时，网络可能不稳定，请稍后再试。")
        except (OSError, RuntimeError, ValueError):
            logger.exception("setu command failed")
            yield event.plain_result("获取图片失败，网络或服务异常，请稍后再试。")

    async def handle_setu_mode(self, event: AstrMessageEvent, mode: str = ""):
        """处理 /setu_mode 命令。"""
        if not self._core:
            yield event.plain_result("插件尚未就绪，请稍后再试。")
            return

        if not self._check_admin(event):
            yield event.plain_result("❌ 权限不足：此命令仅限管理员或超级管理员使用。")
            return

        mode = mode.strip().lower()
        if not mode:
            async for result in self._show_mode_status(event):
                yield result
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

    async def _show_mode_status(self, event: AstrMessageEvent):
        """显示当前会话的模式状态。"""
        session_id = event.get_session_id()
        is_group = bool(event.get_group_id())

        current_mode = await self._core.session_config.get_session_content_mode(
            session_id, is_group
        )
        global_mode = self._core.config.content_mode

        session_docx = await self._core.session_config.get_session_r18_docx_mode(
            session_id, is_group
        )
        global_docx = self._core.config.r18_docx_mode
        effective_docx = await self._core.get_effective_r18_docx_mode(event)

        session_revoke = await self._core.session_config.get_session_auto_revoke_r18(
            session_id, is_group
        )
        global_revoke = self._core.config.auto_revoke_r18
        delay = self._core.config.auto_revoke_delay
        effective_revoke = await self._core.get_effective_auto_revoke_r18(event)

        def fmt(val, is_bool=True):
            if val is None:
                return "未设置"
            return "启用" if val else "禁用" if is_bool else str(val)

        msg = (
            f"📋 当前会话配置：\n\n"
            f"1️⃣ 内容分级：\n"
            f"   会话覆盖：{fmt(current_mode, False) if current_mode else '未设置'}\n"
            f"   全局配置：{global_mode}\n"
            f"   生效模式：{current_mode or global_mode}\n\n"
            f"2️⃣ R18 Docx 打包：\n"
            f"   会话覆盖：{fmt(session_docx)}\n"
            f"   全局配置：{'启用' if global_docx else '禁用'}\n"
            f"   生效设置：{'启用' if effective_docx else '禁用'}\n\n"
            f"3️⃣ R18 自动撤回：\n"
            f"   会话覆盖：{fmt(session_revoke)}\n"
            f"   全局配置：{'启用' if global_revoke else '禁用'}（延迟 {delay} 秒）\n"
            f"   生效设置：{'启用' if effective_revoke else '禁用'}\n\n"
            f"可用命令：\n"
            f"   /setu_mode sfw|r18|mix|clear - 设置内容分级\n"
            f"   LLM 工具：set_setu_r18_docx_mode - 设置 R18 Docx 模式\n"
            f"   LLM 工具：set_setu_auto_revoke - 设置自动撤回"
        )
        yield event.plain_result(msg)
