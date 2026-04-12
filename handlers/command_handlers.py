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

        # 检查全局黑白名单和色图功能级黑名单
        if self._core.is_group_blocked(event, feature="setu"):
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
                    try:
                        img_urls = await asyncio.wait_for(
                            provider.fetch_image_urls(
                                num=num,
                                tags=tags,
                                r18=is_r18,
                                exclude_ai=self._config.exclude_ai,
                            ),
                            timeout=60.0,
                        )
                    except asyncio.TimeoutError:
                        logger.warning(
                            "url mode fetch_image_urls timeout (>60s), tags=%s, r18=%s",
                            tags,
                            is_r18,
                        )
                        yield event.plain_result("图片获取超时，请稍后重试。")
                        return

                    async for result in self._core.send_images_by_url(
                        event, img_urls, is_r18, tags
                    ):
                        yield result
                else:
                    yield event.plain_result("没有可用的图片源，请联系管理员。")
            else:
                # 正常模式：下载后发送
                downloaded = await asyncio.wait_for(
                    self._core.fetch_and_download_images(num, tags, is_r18),
                    timeout=60.0,
                )
                if not downloaded:
                    tags_info = f"标签: {', '.join(tags)}" if tags else ""
                    yield event.plain_result(
                        f"未找到{tags_info}符合要求的图片，请尝试其他标签或检查标签拼写~"
                    )
                    return

                async for result in self._core.send_images(
                    event, downloaded, is_r18, tags
                ):
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
            async for result in self._handle_setu_command_internal(
                event, count, tags=tags
            ):
                yield result
        finally:
            await self._core.rate_limiter.release(event)

    async def _handle_setu_command_internal(
        self, event: AstrMessageEvent, count: str = "1", *, tags: str = ""
    ):
        """处理 /setu 命令的内部逻辑。"""
        if self._core.is_group_blocked(event, feature="setu"):
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
                    try:
                        img_urls = await asyncio.wait_for(
                            provider.fetch_image_urls(
                                num=num,
                                tags=parsed_tags,
                                r18=is_r18,
                                exclude_ai=self._config.exclude_ai,
                            ),
                            timeout=60.0,
                        )
                    except asyncio.TimeoutError:
                        logger.warning(
                            "url mode fetch_image_urls timeout (>60s), tags=%s, r18=%s",
                            parsed_tags,
                            is_r18,
                        )
                        yield event.plain_result("图片获取超时，请稍后重试。")
                        return

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

        session_send = await self._core.session_config.get_session_send_mode(
            session_id, is_group
        )
        global_send = self._core.config.send_mode
        effective_send = await self._core.get_effective_send_mode(event)

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
            f"4️⃣ 发送模式：\n"
            f"   会话覆盖：{fmt(session_send, False) if session_send else '未设置'}\n"
            f"   全局配置：{global_send}\n"
            f"   生效模式：{effective_send}\n\n"
            f"可用命令：\n"
            f"   /setu_config mode <sfw|r18|mix|clear> - 设置内容分级\n"
            f"   /setu_config docx <on|off|clear> - 设置 R18 Docx 模式\n"
            f"   /setu_config revoke <on|off|clear> - 设置自动撤回\n"
            f"   /setu_config send <image|forward|auto|clear> - 设置发送模式\n"
            f"   /setu_config show - 显示当前配置"
        )
        yield event.plain_result(msg)

    async def handle_setu_config(self, event: AstrMessageEvent, args: str = ""):
        """处理 /setu_config 命令（统一配置管理）。"""
        if not self._core:
            yield event.plain_result("插件尚未就绪，请稍后再试。")
            return

        if not self._check_admin(event):
            yield event.plain_result("❌ 权限不足：此命令仅限管理员或超级管理员使用。")
            return

        args = args.strip()
        if not args or args.lower() == "show":
            async for result in self._show_mode_status(event):
                yield result
            return

        # 解析命令（只将命令部分转为小写）
        parts = args.split(maxsplit=1)
        cmd = parts[0].lower()
        value = parts[1].lower() if len(parts) > 1 else ""

        session_id = event.get_session_id()
        is_group = bool(event.get_group_id())
        session_type = "群聊" if is_group else "私聊"

        if cmd == "mode":
            # 内容分级设置
            async for result in self._handle_config_mode(
                event, session_id, is_group, session_type, value
            ):
                yield result

        elif cmd == "docx":
            # R18 Docx 打包模式设置
            async for result in self._handle_config_docx(
                event, session_id, is_group, session_type, value
            ):
                yield result

        elif cmd == "revoke":
            # 自动撤回设置
            async for result in self._handle_config_revoke(
                event, session_id, is_group, session_type, value
            ):
                yield result

        elif cmd == "send":
            # 发送模式设置
            async for result in self._handle_config_send(
                event, session_id, is_group, session_type, value
            ):
                yield result

        else:
            yield event.plain_result(
                "❌ 未知的配置项。\n"
                "可用配置项：mode（内容分级）、docx（打包模式）、revoke（自动撤回）、send（发送模式）\n"
                "使用 /setu_config show 查看当前配置。"
            )

    async def _handle_config_mode(
        self, event, session_id, is_group, session_type, value
    ):
        """处理内容分级配置。"""
        if value not in ("sfw", "r18", "mix", "clear"):
            yield event.plain_result(
                "❌ 无效的模式。\n"
                "可用模式：sfw（全年龄）、r18（成人）、mix（混合）、clear（清除设置）"
            )
            return

        if value == "clear":
            success = await self._core.session_config.clear_session_content_mode(
                session_id, is_group
            )
            if success:
                global_mode = self._core.config.content_mode
                yield event.plain_result(
                    f"✅ 已清除当前{session_type}的内容分级设置，将使用全局配置。\n"
                    f"当前全局配置为：{global_mode}"
                )
            else:
                yield event.plain_result("ℹ️ 当前会话没有设置覆盖，已在使用全局配置。")
        else:
            success = await self._core.session_config.set_session_content_mode(
                session_id, is_group, value
            )
            if success:
                yield event.plain_result(
                    f"✅ 已将当前{session_type}的内容分级设置为：{value}\n"
                    f"此后发送的图片将使用此模式（优先于全局配置）。"
                )
            else:
                yield event.plain_result("❌ 设置失败，请稍后再试。")

    async def _handle_config_docx(
        self, event, session_id, is_group, session_type, value
    ):
        """处理 R18 Docx 打包模式配置。"""
        if value not in ("on", "off", "clear", ""):
            yield event.plain_result(
                "❌ 无效的设置。\n可用值：on（启用）、off（禁用）、clear（清除设置）"
            )
            return

        global_docx = self._core.config.r18_docx_mode

        if value == "clear" or value == "":
            success = await self._core.session_config.clear_session_r18_docx_mode(
                session_id, is_group
            )
            if success:
                yield event.plain_result(
                    f"✅ 已清除当前{session_type}的 R18 Docx 打包模式设置，将使用全局配置。\n"
                    f"当前全局配置为：{'启用' if global_docx else '禁用'}"
                )
            else:
                yield event.plain_result("ℹ️ 当前会话没有设置覆盖，已在使用全局配置。")
        else:
            enabled = value == "on"
            success = await self._core.session_config.set_session_r18_docx_mode(
                session_id, is_group, enabled
            )
            if success:
                yield event.plain_result(
                    f"✅ 已将当前{session_type}的 R18 Docx 打包模式设置为：{'启用' if enabled else '禁用'}\n"
                    f"此后发送的 R18 图片将{'打包为 DOCX 文件' if enabled else '直接发送'}（优先于全局配置）。"
                )
            else:
                yield event.plain_result("❌ 设置失败，请稍后再试。")

    async def _handle_config_revoke(
        self, event, session_id, is_group, session_type, value
    ):
        """处理自动撤回配置。"""
        if value not in ("on", "off", "clear", ""):
            yield event.plain_result(
                "❌ 无效的设置。\n可用值：on（启用）、off（禁用）、clear（清除设置）"
            )
            return

        global_revoke = self._core.config.auto_revoke_r18
        delay = self._core.config.auto_revoke_delay

        if value == "clear" or value == "":
            success = await self._core.session_config.clear_session_auto_revoke_r18(
                session_id, is_group
            )
            if success:
                yield event.plain_result(
                    f"✅ 已清除当前{session_type}的自动撤回设置，将使用全局配置。\n"
                    f"当前全局配置为：{'启用' if global_revoke else '禁用'}（延迟 {delay} 秒）"
                )
            else:
                yield event.plain_result("ℹ️ 当前会话没有设置覆盖，已在使用全局配置。")
        else:
            enabled = value == "on"
            success = await self._core.session_config.set_session_auto_revoke_r18(
                session_id, is_group, enabled
            )
            if success:
                yield event.plain_result(
                    f"✅ 已将当前{session_type}的自动撤回设置为：{'启用' if enabled else '禁用'}\n"
                    f"此后发送的 R18 内容将{'在 {delay} 秒后自动撤回' if enabled else '不会自动撤回'}（优先于全局配置）。"
                )
            else:
                yield event.plain_result("❌ 设置失败，请稍后再试。")

    async def _handle_config_send(
        self, event, session_id, is_group, session_type, value
    ):
        """处理发送模式配置。"""
        if value not in ("image", "forward", "auto", "clear", ""):
            yield event.plain_result(
                "❌ 无效的发送模式。\n"
                "可用模式：image（直接发送）、forward（合并转发）、auto（自动选择）、clear（清除设置）"
            )
            return

        global_send = self._core.config.send_mode

        if value == "clear" or value == "":
            success = await self._core.session_config.clear_session_send_mode(
                session_id, is_group
            )
            if success:
                yield event.plain_result(
                    f"✅ 已清除当前{session_type}的发送模式设置，将使用全局配置。\n"
                    f"当前全局配置为：{global_send}"
                )
            else:
                yield event.plain_result("ℹ️ 当前会话没有设置覆盖，已在使用全局配置。")
        else:
            success = await self._core.session_config.set_session_send_mode(
                session_id, is_group, value
            )
            if success:
                mode_desc = {
                    "image": "直接发送图片",
                    "forward": "合并转发消息",
                    "auto": "自动选择（单张直接发送，多张合并转发）",
                }
                yield event.plain_result(
                    f"✅ 已将当前{session_type}的发送模式设置为：{value}\n"
                    f"说明：{mode_desc.get(value, '')}（优先于全局配置）。"
                )
            else:
                yield event.plain_result("❌ 设置失败，请稍后再试。")

    # ============ 黑白名单管理命令（简化中文版）============

    async def handle_setu_block_user(self, event: AstrMessageEvent, args: str = ""):
        """处理 /拉黑色图用户 命令（AT某人加入Setu黑名单）。"""
        if not self._core:
            yield event.plain_result("插件尚未就绪，请稍后再试。")
            return

        if not self._check_admin(event):
            yield event.plain_result("❌ 权限不足：此命令仅限管理员或超级管理员使用。")
            return

        target_id = self._extract_target_id(event, args)
        if not target_id:
            yield event.plain_result(
                "❌ 请通过 AT (@) 指定要拉黑的用户。\n用法：/拉黑色图用户 @用户名"
            )
            return

        sender_id = event.get_sender_id()
        if target_id == str(sender_id):
            yield event.plain_result("❌ 不能将自己加入黑名单。")
            return

        success = self._core.access_control.add_setu_blocked_user(target_id)
        if success:
            yield event.plain_result(f"✅ 已将用户 `{target_id}` 加入色图功能黑名单。")
        else:
            yield event.plain_result("❌ 操作失败，请稍后再试。")

    async def handle_setu_unblock_user(self, event: AstrMessageEvent, args: str = ""):
        """处理 /解除色图拉黑 命令（AT某人从Setu黑名单移除）。"""
        if not self._core:
            yield event.plain_result("插件尚未就绪，请稍后再试。")
            return

        if not self._check_admin(event):
            yield event.plain_result("❌ 权限不足：此命令仅限管理员或超级管理员使用。")
            return

        target_id = self._extract_target_id(event, args)
        if not target_id:
            yield event.plain_result(
                "❌ 请通过 AT (@) 指定要解除拉黑的用户。\n用法：/解除色图拉黑 @用户名"
            )
            return

        success = self._core.access_control.remove_setu_blocked_user(target_id)
        if success:
            yield event.plain_result(
                f"✅ 已将用户 `{target_id}` 从色图功能黑名单移除。"
            )
        else:
            yield event.plain_result("❌ 操作失败，请稍后再试。")

    async def handle_fortune_block_user(self, event: AstrMessageEvent, args: str = ""):
        """处理 /拉黑运势用户 命令（AT某人加入Fortune黑名单）。"""
        if not self._core:
            yield event.plain_result("插件尚未就绪，请稍后再试。")
            return

        if not self._check_admin(event):
            yield event.plain_result("❌ 权限不足：此命令仅限管理员或超级管理员使用。")
            return

        target_id = self._extract_target_id(event, args)
        if not target_id:
            yield event.plain_result(
                "❌ 请通过 AT (@) 指定要拉黑的用户。\n用法：/拉黑运势用户 @用户名"
            )
            return

        sender_id = event.get_sender_id()
        if target_id == str(sender_id):
            yield event.plain_result("❌ 不能将自己加入黑名单。")
            return

        success = self._core.access_control.add_fortune_blocked_user(target_id)
        if success:
            yield event.plain_result(f"✅ 已将用户 `{target_id}` 加入运势功能黑名单。")
        else:
            yield event.plain_result("❌ 操作失败，请稍后再试。")

    async def handle_fortune_unblock_user(
        self, event: AstrMessageEvent, args: str = ""
    ):
        """处理 /解除运势拉黑 命令（AT某人从Fortune黑名单移除）。"""
        if not self._core:
            yield event.plain_result("插件尚未就绪，请稍后再试。")
            return

        if not self._check_admin(event):
            yield event.plain_result("❌ 权限不足：此命令仅限管理员或超级管理员使用。")
            return

        target_id = self._extract_target_id(event, args)
        if not target_id:
            yield event.plain_result(
                "❌ 请通过 AT (@) 指定要解除拉黑的用户。\n用法：/解除运势拉黑 @用户名"
            )
            return

        success = self._core.access_control.remove_fortune_blocked_user(target_id)
        if success:
            yield event.plain_result(
                f"✅ 已将用户 `{target_id}` 从运势功能黑名单移除。"
            )
        else:
            yield event.plain_result("❌ 操作失败，请稍后再试。")

    async def handle_setu_trust_user(self, event: AstrMessageEvent, args: str = ""):
        """处理 /信任色图用户 命令（AT某人加入Setu白名单）。"""
        if not self._core:
            yield event.plain_result("插件尚未就绪，请稍后再试。")
            return

        if not self._check_admin(event):
            yield event.plain_result("❌ 权限不足：此命令仅限管理员或超级管理员使用。")
            return

        target_id = self._extract_target_id(event, args)
        if not target_id:
            yield event.plain_result(
                "❌ 请通过 AT (@) 指定要信任的用户。\n用法：/信任色图用户 @用户名"
            )
            return

        success = self._core.access_control.add_setu_whitelist_user(target_id)
        if success:
            yield event.plain_result(f"✅ 已将用户 `{target_id}` 加入色图功能白名单。")
        else:
            yield event.plain_result("❌ 操作失败，请稍后再试。")

    async def handle_setu_untrust_user(self, event: AstrMessageEvent, args: str = ""):
        """处理 /取消色图信任 命令（AT某人从Setu白名单移除）。"""
        if not self._core:
            yield event.plain_result("插件尚未就绪，请稍后再试。")
            return

        if not self._check_admin(event):
            yield event.plain_result("❌ 权限不足：此命令仅限管理员或超级管理员使用。")
            return

        target_id = self._extract_target_id(event, args)
        if not target_id:
            yield event.plain_result(
                "❌ 请通过 AT (@) 指定要取消信任的用户。\n用法：/取消色图信任 @用户名"
            )
            return

        success = self._core.access_control.remove_setu_whitelist_user(target_id)
        if success:
            yield event.plain_result(
                f"✅ 已将用户 `{target_id}` 从色图功能白名单移除。"
            )
        else:
            yield event.plain_result("❌ 操作失败，请稍后再试。")

    async def handle_fortune_trust_user(self, event: AstrMessageEvent, args: str = ""):
        """处理 /信任运势用户 命令（AT某人加入Fortune白名单）。"""
        if not self._core:
            yield event.plain_result("插件尚未就绪，请稍后再试。")
            return

        if not self._check_admin(event):
            yield event.plain_result("❌ 权限不足：此命令仅限管理员或超级管理员使用。")
            return

        target_id = self._extract_target_id(event, args)
        if not target_id:
            yield event.plain_result(
                "❌ 请通过 AT (@) 指定要信任的用户。\n用法：/信任运势用户 @用户名"
            )
            return

        success = self._core.access_control.add_fortune_whitelist_user(target_id)
        if success:
            yield event.plain_result(f"✅ 已将用户 `{target_id}` 加入运势功能白名单。")
        else:
            yield event.plain_result("❌ 操作失败，请稍后再试。")

    async def handle_fortune_untrust_user(
        self, event: AstrMessageEvent, args: str = ""
    ):
        """处理 /取消运势信任 命令（AT某人从Fortune白名单移除）。"""
        if not self._core:
            yield event.plain_result("插件尚未就绪，请稍后再试。")
            return

        if not self._check_admin(event):
            yield event.plain_result("❌ 权限不足：此命令仅限管理员或超级管理员使用。")
            return

        target_id = self._extract_target_id(event, args)
        if not target_id:
            yield event.plain_result(
                "❌ 请通过 AT (@) 指定要取消信任的用户。\n用法：/取消运势信任 @用户名"
            )
            return

        success = self._core.access_control.remove_fortune_whitelist_user(target_id)
        if success:
            yield event.plain_result(
                f"✅ 已将用户 `{target_id}` 从运势功能白名单移除。"
            )
        else:
            yield event.plain_result("❌ 操作失败，请稍后再试。")

    async def handle_enable_setu_group(self, event: AstrMessageEvent, args: str = ""):
        """处理 /开启色图 命令（从色图黑名单移除当前群组）。"""
        if not self._core:
            yield event.plain_result("插件尚未就绪，请稍后再试。")
            return

        if not self._check_admin(event):
            yield event.plain_result("❌ 权限不足：此命令仅限管理员或超级管理员使用。")
            return

        group_id = event.get_group_id()
        if not group_id:
            yield event.plain_result("❌ 此命令只能在群聊中使用。")
            return

        gid = str(group_id)
        success = self._core.access_control.remove_setu_blocked_group(gid)
        if success:
            yield event.plain_result("✅ 已在本群开启色图功能。")
        else:
            yield event.plain_result("❌ 操作失败，请稍后再试。")

    async def handle_disable_setu_group(self, event: AstrMessageEvent, args: str = ""):
        """处理 /关闭色图 命令（将当前群组加入色图黑名单）。"""
        if not self._core:
            yield event.plain_result("插件尚未就绪，请稍后再试。")
            return

        if not self._check_admin(event):
            yield event.plain_result("❌ 权限不足：此命令仅限管理员或超级管理员使用。")
            return

        group_id = event.get_group_id()
        if not group_id:
            yield event.plain_result("❌ 此命令只能在群聊中使用。")
            return

        gid = str(group_id)
        success = self._core.access_control.add_setu_blocked_group(gid)
        if success:
            yield event.plain_result("✅ 已在本群关闭色图功能。")
        else:
            yield event.plain_result("❌ 操作失败，请稍后再试。")

    async def handle_enable_fortune_group(
        self, event: AstrMessageEvent, args: str = ""
    ):
        """处理 /开启运势 命令（从运势黑名单移除当前群组）。"""
        if not self._core:
            yield event.plain_result("插件尚未就绪，请稍后再试。")
            return

        if not self._check_admin(event):
            yield event.plain_result("❌ 权限不足：此命令仅限管理员或超级管理员使用。")
            return

        group_id = event.get_group_id()
        if not group_id:
            yield event.plain_result("❌ 此命令只能在群聊中使用。")
            return

        gid = str(group_id)
        success = self._core.access_control.remove_fortune_blocked_group(gid)
        if success:
            yield event.plain_result("✅ 已在本群开启运势功能。")
        else:
            yield event.plain_result("❌ 操作失败，请稍后再试。")

    async def handle_disable_fortune_group(
        self, event: AstrMessageEvent, args: str = ""
    ):
        """处理 /关闭运势 命令（将当前群组加入运势黑名单）。"""
        if not self._core:
            yield event.plain_result("插件尚未就绪，请稍后再试。")
            return

        if not self._check_admin(event):
            yield event.plain_result("❌ 权限不足：此命令仅限管理员或超级管理员使用。")
            return

        group_id = event.get_group_id()
        if not group_id:
            yield event.plain_result("❌ 此命令只能在群聊中使用。")
            return

        gid = str(group_id)
        success = self._core.access_control.add_fortune_blocked_group(gid)
        if success:
            yield event.plain_result("✅ 已在本群关闭运势功能。")
        else:
            yield event.plain_result("❌ 操作失败，请稍后再试。")

    def _extract_target_id(self, event: AstrMessageEvent, args: str) -> str | None:
        """从消息中提取目标用户 ID（仅支持 AT）。"""
        for comp in event.get_messages():
            if hasattr(comp, "qq") and comp.qq:
                target = str(comp.qq)
                if target not in ("all", "0"):
                    return target
        return None
