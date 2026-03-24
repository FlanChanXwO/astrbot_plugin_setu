"""今日运势 LLM 工具处理器。"""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING

import astrbot.api.message_components as Comp
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.core.message.message_event_result import MessageChain

if TYPE_CHECKING:
    from ..core import SetuCore
    from .core import FortuneCore
    from .session_config import FortuneSessionConfig


class FortuneLlmHandler:
    """今日运势 LLM 工具处理器。"""

    def __init__(
        self,
        setu_plugin,
        core: SetuCore,
        fortune_core: FortuneCore,
        session_config: FortuneSessionConfig,
    ):
        self._setu_plugin = setu_plugin
        self._core = core
        self._fortune_core = fortune_core
        self._session_config = session_config
        self._renderer = None

    @staticmethod
    async def _check_admin(event: AstrMessageEvent) -> bool:
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
        except AttributeError:
            pass
        return False

    @staticmethod
    async def _check_super_admin(event: AstrMessageEvent) -> bool:
        """检查用户是否为超级管理员。"""
        try:
            if hasattr(event, "is_super_user") and callable(
                getattr(event, "is_super_user")
            ):
                if event.is_super_user():
                    return True
        except AttributeError:
            pass
        return False

    async def _get_image_for_fortune(self, event: AstrMessageEvent) -> bytes | None:
        """获取今日运势的背景图片。

        使用 Setu 插件的图片供应商，根据配置获取图片。
        """
        session_id = event.get_session_id()
        is_group = bool(event.get_group_id())

        # 获取生效的配置

        config = self._setu_plugin.config
        fortune_cfg = getattr(config, "fortune", {})
        global_tags = (
            fortune_cfg.get("tags", "") if isinstance(fortune_cfg, dict) else ""
        )
        global_mode = (
            fortune_cfg.get("content_mode", "sfw")
            if isinstance(fortune_cfg, dict)
            else "sfw"
        )

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
            "[fortune_llm] Getting image: tags=%s, mode=%s, is_r18=%s",
            tags,
            content_mode,
            is_r18,
        )

        try:
            # 使用 SetuCore 的 provider 获取图片
            provider = self._core._get_provider()
            if not provider:
                logger.error("[fortune_llm] No provider available")
                return None

            # 获取图片
            downloaded = await self._core.fetch_and_download_images(1, tags, is_r18)

            if downloaded and len(downloaded) > 0:
                return downloaded[0]

        except Exception as exc:
            logger.exception("[fortune_llm] Failed to get image: %s", exc)

        return None

    async def _send_fortune_image(
        self, event: AstrMessageEvent, fortune: dict
    ) -> bool:
        """生成并发送运势图片给用户。

        参数:
            event: 消息事件
            fortune: 运势数据

        返回:
            是否成功发送图片
        """
        try:
            # 初始化 renderer
            if self._renderer is None:
                from .renderer import FortuneRenderer

                self._renderer = FortuneRenderer()

            # 获取 HTML 渲染器
            html_renderer = None
            if hasattr(self._setu_plugin, "html_render"):
                html_renderer = self._setu_plugin.html_render

            if not html_renderer:
                logger.warning("[fortune_llm] No HTML renderer available")
                return False

            # 获取背景图片
            image_data = await self._get_image_for_fortune(event)
            image_base64 = ""
            if image_data:
                image_base64 = base64.b64encode(image_data).decode("utf-8")

            # 渲染运势图片
            rendered_image = await self._renderer.render_to_image(
                fortune=fortune, image_base64=image_base64, html_renderer=html_renderer
            )

            if not rendered_image:
                logger.warning("[fortune_llm] Failed to render fortune image")
                return False

            # 发送图片
            message_chain = MessageChain([Comp.Image.fromBytes(rendered_image)])
            await self._setu_plugin.context.send_message(
                event.unified_msg_origin,
                message_chain,
            )
            return True

        except Exception as exc:
            logger.exception("[fortune_llm] Failed to send fortune image: %s", exc)
            return False

    async def llm_get_fortune(self, event: AstrMessageEvent, **kwargs) -> dict:
        """LLM 工具：获取今日运势。

        返回用户的今日运势信息，并发送运势图片给用户。
        """
        user_id = event.get_sender_id()
        username = event.get_sender_name() or user_id
        group_id = event.get_group_id()

        try:
            fortune = await self._fortune_core.get_today_fortune(
                user_id, username, group_id
            )

            if not fortune:
                return {
                    "success": False,
                    "message": "无法获取今日运势，请稍后重试。",
                }

            # 发送运势图片给用户
            await self._send_fortune_image(event, fortune)

            return {
                "success": True,
                "fortune": {
                    "title": fortune["title"],
                    "stars": fortune["star_count"],
                    "max_stars": fortune["max_stars"],
                    "description": fortune["description"],
                    "extra": fortune["extra_message"],
                    "date": fortune["date_str"],
                },
                "message": f"今日运势：{fortune['title']}（{fortune['star_count']}星）\n{fortune['description']}",
            }
        except Exception as exc:
            logger.exception("[fortune_llm] Failed to get fortune: %s", exc)
            return {
                "success": False,
                "message": "获取运势时出错，请稍后重试。",
            }

    async def llm_refresh_fortune(self, event: AstrMessageEvent, **kwargs) -> dict:
        """LLM 工具：刷新今日运势。

        刷新用户的今日运势（管理员或配置允许时）。
        """
        user_id = event.get_sender_id()
        username = event.get_sender_name() or user_id

        # 检查权限
        is_admin = await self._check_admin(event)
        if not is_admin:
            return {
                "success": False,
                "message": "只有管理员可以刷新运势。",
            }

        try:
            await self._fortune_core.refresh_fortune(user_id, username)
            return {
                "success": True,
                "message": "已成功刷新今日运势，可以重新获取查看。",
            }
        except Exception as exc:
            logger.exception("[fortune_llm] Failed to refresh fortune: %s", exc)
            return {
                "success": False,
                "message": "刷新运势时出错，请稍后重试。",
            }

    async def llm_refresh_group_fortune(
        self, event: AstrMessageEvent, **kwargs
    ) -> dict:
        """LLM 工具：刷新群组今日运势。

        刷新当前群组所有成员的今日运势（仅管理员）。
        """
        # 检查权限
        is_admin = await self._check_admin(event)
        if not is_admin:
            return {
                "success": False,
                "message": "只有管理员可以刷新群组运势。",
            }

        group_id = event.get_group_id()
        if not group_id:
            return {
                "success": False,
                "message": "此操作只能在群聊中进行。",
            }

        try:
            count = await self._fortune_core.refresh_group_fortune(str(group_id))
            return {
                "success": True,
                "message": f"已成功刷新本群今日运势，共 {count} 条记录将被重新生成。",
            }
        except Exception as exc:
            logger.exception("[fortune_llm] Failed to refresh group fortune: %s", exc)
            return {
                "success": False,
                "message": "刷新群组运势时出错，请稍后重试。",
            }

    async def llm_refresh_all_fortune(self, event: AstrMessageEvent, **kwargs) -> dict:
        """LLM 工具：刷新全局今日运势。

        刷新所有用户的今日运势（仅超级管理员）。
        """
        # 检查权限：仅允许超级管理员
        is_super_admin = await self._check_super_admin(event)
        if not is_super_admin:
            return {
                "success": False,
                "message": "只有超级管理员可以刷新全局运势。",
            }

        try:
            count = await self._fortune_core.refresh_all_fortune()
            return {
                "success": True,
                "message": f"已成功刷新全局今日运势，共 {count} 条记录将被重新生成。",
            }
        except Exception as exc:
            logger.exception("[fortune_llm] Failed to refresh all fortune: %s", exc)
            return {
                "success": False,
                "message": "刷新全局运势时出错，请稍后重试。",
            }

    async def llm_get_fortune_config(self, event: AstrMessageEvent, **kwargs) -> dict:
        """LLM 工具：获取今日运势配置。

        返回当前会话的今日运势配置信息。
        """
        session_id = event.get_session_id()
        is_group = bool(event.get_group_id())

        session_tags = await self._session_config.get_session_tags(session_id, is_group)
        session_mode = await self._session_config.get_session_content_mode(
            session_id, is_group
        )

        config = self._setu_plugin.config
        fortune_cfg = getattr(config, "fortune", {})
        global_tags = (
            fortune_cfg.get("tags", "未设置")
            if isinstance(fortune_cfg, dict)
            else "未设置"
        )
        global_mode = (
            fortune_cfg.get("content_mode", "sfw")
            if isinstance(fortune_cfg, dict)
            else "sfw"
        )

        effective_tags = session_tags if session_tags is not None else global_tags
        effective_mode = session_mode if session_mode else global_mode

        return {
            "success": True,
            "config": {
                "session_tags": session_tags,
                "global_tags": global_tags,
                "effective_tags": effective_tags,
                "session_mode": session_mode,
                "global_mode": global_mode,
                "effective_mode": effective_mode,
            },
            "message": (
                f"当前今日运势配置：\n"
                f"标签：{effective_tags}\n"
                f"内容模式：{effective_mode}"
            ),
        }

    async def llm_set_fortune_config(
        self,
        event: AstrMessageEvent,
        tags: str | None = None,
        mode: str | None = None,
        **kwargs,
    ) -> dict:
        """LLM 工具：设置今日运势配置。

        设置当前会话的今日运势标签或内容模式（仅管理员）。

        参数:
            tags: 标签字符串，如 "少女,可爱"
            mode: 内容模式，可选 sfw、r18、mix
        """
        # 检查权限
        is_admin = await self._check_admin(event)
        if not is_admin:
            return {
                "success": False,
                "message": "只有管理员可以配置今日运势。",
            }

        session_id = event.get_session_id()
        is_group = bool(event.get_group_id())

        results = []

        if tags is not None:
            if tags == "":
                # 清除标签
                await self._session_config.clear_session_tags(session_id, is_group)
                results.append("已清除标签设置")
            else:
                await self._session_config.set_session_tags(session_id, is_group, tags)
                results.append(f"已设置标签为：{tags}")

        if mode is not None:
            if mode in ("sfw", "r18", "mix"):
                await self._session_config.set_session_content_mode(
                    session_id, is_group, mode
                )
                results.append(f"已设置内容模式为：{mode}")
            else:
                return {
                    "success": False,
                    "message": f"无效的内容模式：{mode}，可选：sfw、r18、mix",
                }

        if not results:
            return {
                "success": False,
                "message": "请提供要设置的参数：tags 或 mode",
            }

        return {
            "success": True,
            "message": "；".join(results),
        }
