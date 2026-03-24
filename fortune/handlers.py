"""今日运势命令处理器。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

if TYPE_CHECKING:
    from ..config import SetuConfig
    from ..core import SetuCore
    from .core import FortuneCore
    from .renderer import FortuneRenderer
    from .session_config import FortuneSessionConfig


class FortuneCommandHandler:
    """今日运势命令处理器。"""

    def __init__(
        self,
        core: SetuCore,
        config: SetuConfig,
        fortune_core: FortuneCore,
        fortune_renderer: FortuneRenderer,
        session_config: FortuneSessionConfig,
    ):
        self._core = core
        self._config = config
        self._fortune_core = fortune_core
        self._fortune_renderer = fortune_renderer
        self._session_config = session_config

    @staticmethod
    def _check_admin(event: AstrMessageEvent) -> bool:
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

    async def _get_image_for_fortune(
        self, event: AstrMessageEvent
    ) -> bytes | None:
        """获取今日运势的图片。

        使用 Setu 插件的图片供应商，根据配置获取图片。
        """
        session_id = event.get_session_id()
        is_group = bool(event.get_group_id())

        # 获取生效的配置
        fortune_cfg = getattr(self._config, "fortune", {})
        global_tags = fortune_cfg.get("tags", "") if isinstance(fortune_cfg, dict) else ""
        global_mode = fortune_cfg.get("content_mode", "sfw") if isinstance(fortune_cfg, dict) else "sfw"

        tags_str = await self._session_config.get_effective_tags(
            session_id, is_group, global_tags
        )
        content_mode = await self._session_config.get_effective_content_mode(
            session_id, is_group, global_mode
        )

        # 解析标签
        tags = [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str else []

        # 确定 R18
        import random

        is_r18 = False
        if content_mode == "r18":
            is_r18 = True
        elif content_mode == "mix":
            is_r18 = random.random() > 0.5

        logger.debug(
            "[fortune] Getting image: tags=%s, mode=%s, is_r18=%s",
            tags,
            content_mode,
            is_r18,
        )

        try:
            # 使用 SetuCore 的 provider 获取图片
            provider = self._core._get_provider()
            if not provider:
                logger.error("[fortune] No provider available")
                return None

            # 获取 1 张图片 URL
            img_urls = await provider.fetch_image_urls(
                num=1, tags=tags, r18=is_r18, exclude_ai=self._config.exclude_ai
            )

            if not img_urls:
                logger.warning("[fortune] No image URLs returned")
                return None

            # 下载图片
            downloaded = await self._core.fetch_and_download_images(1, tags, is_r18)

            if downloaded and len(downloaded) > 0:
                return downloaded[0]

        except Exception as exc:
            logger.exception("[fortune] Failed to get image: %s", exc)

        return None

    async def handle_fortune(self, event: AstrMessageEvent):
        """处理 /jrys 或 /今日运势 命令。"""
        user_id = event.get_sender_id()
        username = event.get_sender_name() or user_id

        # 获取今日运势数据
        fortune = await self._fortune_core.get_today_fortune(user_id, username)
        if not fortune:
            yield event.plain_result("运势获取失败，请稍后重试。")
            return

        # 检查是否已有缓存的渲染图片
        cached_image = await self._fortune_core.get_cached_image(
            user_id, fortune["date_str"]
        )

        if cached_image:
            # 使用缓存的图片
            logger.debug("[fortune] Using cached image for %s", user_id)
            import astrbot.api.message_components as Comp

            yield event.chain_result([Comp.Image.fromBytes(cached_image)])
            return

        try:
            # 获取图片
            image_data = await self._get_image_for_fortune(event)

            if not image_data:
                # 图片获取失败，发送文字版运势
                logger.warning("[fortune] Failed to get image, sending text version")
                stars = "★" * fortune["star_count"] + "☆" * (7 - fortune["star_count"])
                msg = (
                    f"【今日运势】\n"
                    f"用户：{fortune['username']}\n"
                    f"日期：{fortune['date_str']}\n"
                    f"运势：{fortune['title']}\n"
                    f"星级：{stars}\n"
                    f"\n{fortune['description']}"
                )
                yield event.plain_result(msg)
                return

            # 转换为 base64 用于渲染
            import base64

            image_base64 = base64.b64encode(image_data).decode("utf-8")

            # 获取 AstrBot 的 html_render 方法
            html_renderer = None
            if (
                hasattr(self._core, "plugin")
                and self._core.plugin
                and hasattr(self._core.plugin, "html_render")
            ):
                html_renderer = self._core.plugin.html_render

            if not html_renderer:
                # 没有 HTML 渲染器，发送文字版运势
                logger.warning("[fortune] No HTML renderer available, sending text version")
                stars = "★" * fortune["star_count"] + "☆" * (7 - fortune["star_count"])
                msg = (
                    f"【今日运势】\n"
                    f"用户：{fortune['username']}\n"
                    f"日期：{fortune['date_str']}\n"
                    f"运势：{fortune['title']}\n"
                    f"星级：{stars}\n"
                    f"\n{fortune['description']}"
                )
                yield event.plain_result(msg)
                return

            # 渲染为图片（使用 Jinja2 模板引擎）
            logger.debug("[fortune] Rendering image with html_renderer...")
            rendered_image = await self._fortune_renderer.render_to_image(
                fortune=fortune, image_base64=image_base64, html_renderer=html_renderer
            )

            if not rendered_image:
                logger.warning("[fortune] Image render returned None/empty, sending text version")
                stars = "★" * fortune["star_count"] + "☆" * (7 - fortune["star_count"])
                msg = (
                    f"【今日运势】\n"
                    f"用户：{fortune['username']}\n"
                    f"日期：{fortune['date_str']}\n"
                    f"运势：{fortune['title']}\n"
                    f"星级：{stars}\n"
                    f"\n{fortune['description']}"
                )
                yield event.plain_result(msg)
                return

            logger.debug("[fortune] Image rendered successfully: %d bytes", len(rendered_image))

            # 保存到缓存
            await self._fortune_core.update_fortune_image_cache(
                user_id, fortune["date_str"], rendered_image
            )

            # 发送图片
            import astrbot.api.message_components as Comp

            yield event.chain_result([Comp.Image.fromBytes(rendered_image)])

        except Exception as exc:
            logger.exception("[fortune] Failed to process fortune: %s", exc)
            yield event.plain_result("今日运势生成失败，请稍后重试。")

    async def handle_refresh_fortune(self, event: AstrMessageEvent):
        """处理 /刷新今日运势 命令（个人）。"""
        if not self._check_admin(event):
            # 检查配置是否允许非管理员刷新
            fortune_cfg = getattr(self._config, "fortune", {})
            allow_refresh = fortune_cfg.get("allow_user_refresh", False) if isinstance(fortune_cfg, dict) else False
            if not allow_refresh:
                yield event.plain_result("只有管理员可以刷新运势。")
                return

        user_id = event.get_sender_id()
        username = event.get_sender_name() or user_id

        try:
            # 刷新运势
            await self._fortune_core.refresh_fortune(user_id, username)
            yield event.plain_result("已刷新你的今日运势，发送 今日运势 或 jrys 查看新的运势。")
        except Exception as exc:
            logger.exception("[fortune] Failed to refresh fortune: %s", exc)
            yield event.plain_result("刷新失败，请稍后重试。")

    async def handle_refresh_group_fortune(self, event: AstrMessageEvent):
        """处理 /刷新本群今日运势 命令（仅管理员）。"""
        if not self._check_admin(event):
            yield event.plain_result("只有管理员可以刷新群组运势。")
            return

        group_id = event.get_group_id()
        if not group_id:
            yield event.plain_result("此命令只能在群聊中使用。")
            return

        try:
            # 刷新群组运势（删除该群所有今天的记录）
            count = await self._fortune_core.refresh_group_fortune(str(group_id))
            yield event.plain_result(f"已刷新本群今日运势，共 {count} 条记录将被重新生成。")
        except Exception as exc:
            logger.exception("[fortune] Failed to refresh group fortune: %s", exc)
            yield event.plain_result("刷新失败，请稍后重试。")

    async def handle_refresh_all_fortune(self, event: AstrMessageEvent):
        """处理 /刷新全局今日运势 命令（仅管理员）。"""
        if not self._check_admin(event):
            yield event.plain_result("只有管理员可以刷新全局运势。")
            return

        try:
            count = await self._fortune_core.refresh_all_fortune()
            yield event.plain_result(f"已刷新全局今日运势，共 {count} 条记录将被重新生成。")
        except Exception as exc:
            logger.exception("[fortune] Failed to refresh all fortune: %s", exc)
            yield event.plain_result("刷新失败，请稍后重试。")

    async def handle_fortune_config(self, event: AstrMessageEvent, args: str = ""):
        """处理 /jrys_config 命令（配置今日运势）。"""
        if not self._check_admin(event):
            yield event.plain_result("只有管理员可以配置今日运势。")
            return

        session_id = event.get_session_id()
        is_group = bool(event.get_group_id())

        args = args.strip().lower()
        if not args:
            # 显示当前配置
            self._show_fortune_config(event)
            return

        # 解析命令
        parts = args.split(maxsplit=1)
        cmd = parts[0]
        value = parts[1] if len(parts) > 1 else ""

        if cmd == "tags":
            # 设置标签
            if value:
                success = await self._session_config.set_session_tags(
                    session_id, is_group, value
                )
                if success:
                    yield event.plain_result(f"✅ 已设置今日运势标签为：{value}")
                else:
                    yield event.plain_result("❌ 设置失败。")
            else:
                # 清除标签
                success = await self._session_config.clear_session_tags(
                    session_id, is_group
                )
                if success:
                    yield event.plain_result("✅ 已清除今日运势标签设置。")
                else:
                    yield event.plain_result("ℹ️ 当前没有标签设置。")

        elif cmd == "mode":
            # 设置内容模式
            if value in ("sfw", "r18", "mix"):
                success = await self._session_config.set_session_content_mode(
                    session_id, is_group, value
                )
                if success:
                    yield event.plain_result(f"✅ 已设置今日运势内容模式为：{value}")
                else:
                    yield event.plain_result("❌ 设置失败。")
            elif value == "clear":
                success = await self._session_config.clear_session_content_mode(
                    session_id, is_group
                )
                if success:
                    yield event.plain_result("✅ 已清除今日运势内容模式设置。")
                else:
                    yield event.plain_result("ℹ️ 当前没有内容模式设置。")
            else:
                yield event.plain_result(
                    "❌ 无效的模式。可用：sfw（全年龄）、r18（成人）、mix（混合）、clear（清除）"
                )
        else:
            yield event.plain_result(
                "用法：/jrys_config tags <标签> | /jrys_config mode <sfw|r18|mix|clear>"
            )

    async def _show_fortune_config(self, event: AstrMessageEvent):
        """显示当前今日运势配置。"""
        session_id = event.get_session_id()
        is_group = bool(event.get_group_id())

        session_tags = await self._session_config.get_session_tags(session_id, is_group)
        session_mode = await self._session_config.get_session_content_mode(
            session_id, is_group
        )

        fortune_cfg = getattr(self._config, "fortune", {})
        global_tags = fortune_cfg.get("tags", "未设置") if isinstance(fortune_cfg, dict) else "未设置"
        global_mode = fortune_cfg.get("content_mode", "sfw") if isinstance(fortune_cfg, dict) else "sfw"

        effective_tags = session_tags if session_tags is not None else global_tags
        effective_mode = session_mode if session_mode else global_mode

        session_type = "群聊" if is_group else "私聊"

        msg = (
            f"📋 今日运势配置（{session_type}）\n\n"
            f"标签设置：\n"
            f"  会话覆盖：{session_tags if session_tags is not None else '未设置'}\n"
            f"  全局配置：{global_tags}\n"
            f"  生效标签：{effective_tags}\n\n"
            f"内容模式：\n"
            f"  会话覆盖：{session_mode if session_mode else '未设置'}\n"
            f"  全局配置：{global_mode}\n"
            f"  生效模式：{effective_mode}\n\n"
            f"命令：\n"
            f"  /jrys_config tags <标签> - 设置标签\n"
            f"  /jrys_config mode <sfw|r18|mix|clear> - 设置内容模式"
        )
        yield event.plain_result(msg)
