"""Setu 插件核心逻辑。"""

from __future__ import annotations

import asyncio
import random
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import astrbot.api.message_components as Comp
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from ..config import SetuConfig
from ..services import DocxService, HtmlCardRenderer, ImageService, UrlImageDiskCache
from ..providers import get_provider
from ..session_config import SessionConfigManager
from .revoke_manager import RevokeManager
from .revoke_tasks import RevokeTaskMixin
from .send_revoke import SendWithRevokeMixin


class SetuCore(RevokeTaskMixin, SendWithRevokeMixin):
    """Setu 插件核心逻辑类。"""

    def __init__(self, plugin, config: SetuConfig, data_dir: Path):
        self.plugin = plugin
        self._config = config
        self.data_dir = data_dir
        self._revoke_manager = RevokeManager(data_dir)
        self._session_config = SessionConfigManager(data_dir)
        self._docx_service = DocxService()
        self._revoke_tasks: set[asyncio.Task] = set()
        self._cache: UrlImageDiskCache | None = None
        self._image_service: ImageService | None = None
        self._html_renderer: HtmlCardRenderer | None = None

    async def initialize(self) -> None:
        """初始化核心组件。"""
        await self._revoke_manager.initialize()
        await self._session_config.initialize()
        await self._docx_service.initialize()
        await self._restore_pending_revokes()

        if self._config.enable_html_card:
            self._ensure_html_renderer()

        try:
            if self._config.cache_enabled:
                cache_dir = self.data_dir / "image_cache"
                self._cache = UrlImageDiskCache(
                    cache_dir=cache_dir,
                    ttl_hours=self._config.cache_ttl_hours,
                    max_items=self._config.cache_max_items,
                )
                if self._config.cache_cleanup_on_start:
                    self._cache.cleanup_expired()
            self._image_service = ImageService(
                self._cache,
                concurrent_limit=self._config.download_concurrent_limit,
                timeout_seconds=self._config.download_timeout_seconds,
                tcp_connector_limit=self._config.tcp_connector_limit,
                tcp_connector_limit_per_host=self._config.tcp_connector_limit_per_host,
            )
        except (OSError, RuntimeError, ValueError):
            logger.exception(
                "SetuCore initialize failed, fallback to no-cache ImageService"
            )
            self._cache = None
            self._image_service = ImageService(
                None,
                concurrent_limit=self._config.download_concurrent_limit,
                timeout_seconds=self._config.download_timeout_seconds,
                tcp_connector_limit=self._config.tcp_connector_limit,
                tcp_connector_limit_per_host=self._config.tcp_connector_limit_per_host,
            )

    def terminate(self) -> None:
        """终止插件，取消所有后台任务。"""
        for task in list(self._revoke_tasks):
            if not task.done():
                task.cancel()
        self._revoke_tasks.clear()
        logger.info("[revoke] All revoke tasks cancelled")

    def _get_provider(self):
        cfg = self._config
        lolicon_config = None
        if cfg.api_type in ("lolicon", "all"):
            lolicon_config = {
                "image_size": cfg.image_size,
                "proxy": cfg.proxy,
                "aspect_ratio": cfg.aspect_ratio,
                "uid": cfg.uid,
                "keyword": cfg.keyword,
            }
        return get_provider(
            cfg.api_type,
            custom_config=cfg.custom_api if cfg.api_type == "custom" else None,
            parser_config=cfg.api_response_parser if cfg.api_type == "custom" else None,
            custom_api_configs=cfg.custom_api_configs
            if cfg.api_type in ("custom", "all")
            else None,
            multi_api_strategy=cfg.multi_api_strategy,
            lolicon_config=lolicon_config,
        )

    async def get_effective_content_mode(self, event: AstrMessageEvent) -> str:
        """获取生效的内容模式（优先会话配置）。"""
        session_id = event.get_session_id()
        is_group = bool(event.get_group_id())
        session_mode = await self._session_config.get_session_content_mode(
            session_id, is_group
        )
        if session_mode:
            return session_mode
        return self._config.content_mode

    async def get_effective_r18_docx_mode(self, event: AstrMessageEvent) -> bool:
        """获取生效的 R18 Docx 模式设置。"""
        session_id = event.get_session_id()
        is_group = bool(event.get_group_id())
        session_mode = await self._session_config.get_session_r18_docx_mode(
            session_id, is_group
        )
        if session_mode is not None:
            return session_mode
        return self._config.r18_docx_mode

    async def get_effective_auto_revoke_r18(self, event: AstrMessageEvent) -> bool:
        """获取生效的自动撤回 R18 设置。"""
        session_id = event.get_session_id()
        is_group = bool(event.get_group_id())
        session_mode = await self._session_config.get_session_auto_revoke_r18(
            session_id, is_group
        )
        if session_mode is not None:
            return session_mode
        return self._config.auto_revoke_r18

    def determine_r18(self, content_mode: str) -> bool:
        """根据内容模式确定是否为 R18。"""
        if content_mode == "r18":
            return True
        if content_mode == "mix":
            return random.random() > 0.5
        return False

    def _resolve_send_mode(self, send_mode: str, image_count: int) -> str:
        if send_mode == "auto":
            return "forward" if image_count > 1 else "image"
        return send_mode

    def _ensure_html_renderer(self) -> bool:
        if self._html_renderer is not None:
            return True
        try:
            template_path = Path(__file__).parent.parent / "templates" / "main.html"
            self._html_renderer = HtmlCardRenderer(template_path)
            return True
        except (OSError, ValueError):
            logger.exception("html renderer initialize failed")
            return False

    def is_group_blocked(self, event: AstrMessageEvent) -> bool:
        """检查群聊是否被屏蔽。"""
        try:
            group_id = event.message_obj.group_id
            if group_id and self._config.is_group_blocked(str(group_id)):
                return True
        except AttributeError:
            logger.debug("failed to inspect group id for blocked check")
        return False

    @property
    def session_config(self) -> SessionConfigManager:
        return self._session_config

    @property
    def config(self) -> SetuConfig:
        return self._config

    async def fetch_and_download_images(
        self, num: int, tags: list[str], is_r18: bool
    ) -> list[bytes]:
        """获取并下载图片。"""
        try:
            provider = self._get_provider()
        except (ValueError, RuntimeError):
            logger.exception("provider initialization failed")
            return []

        if not provider:
            logger.error("no provider available")
            return []

        exclude_ai = self._config.exclude_ai
        max_replenish = self._config.max_replenish_rounds

        try:
            img_urls = await provider.fetch_image_urls(
                num=num, tags=tags, r18=is_r18, exclude_ai=exclude_ai
            )
        except (RuntimeError, ConnectionError, TimeoutError) as exc:
            logger.error("provider fetch failed: %s", exc)
            return []

        if not img_urls or not self._image_service:
            return []

        downloaded = await self._image_service.download_parallel(img_urls)

        # 补充机制
        round_num = 0
        while len(downloaded) < num and round_num < max_replenish:
            missing = num - len(downloaded)
            if len(downloaded) == len(img_urls):
                break
            try:
                extra_urls = await provider.fetch_image_urls(
                    num=missing, tags=tags, r18=is_r18, exclude_ai=exclude_ai
                )
                if extra_urls:
                    extra_downloaded = await self._image_service.download_parallel(
                        extra_urls
                    )
                    downloaded.extend(extra_downloaded)
                    if len(extra_urls) < missing:
                        break
                else:
                    break
            except Exception as exc:
                logger.warning("replenish round %d failed: %s", round_num + 1, exc)
            round_num += 1
        return downloaded

    async def send_images(
        self,
        event: AstrMessageEvent,
        images: list[bytes],
        is_r18: bool,
        tags: list[str] | None = None,
    ) -> AsyncGenerator[Any, None]:
        """发送图片，失败时尝试 HTML 卡片降级发送（复用已下载的图片）。"""
        if not images:
            yield event.plain_result("运气不好，一张图都没拿到...")
            return

        cfg = self._config
        send_mode = cfg.send_mode
        actual_send_mode = self._resolve_send_mode(send_mode, len(images))

        effective_auto_revoke = await self.get_effective_auto_revoke_r18(event)
        effective_r18_docx = await self.get_effective_r18_docx_mode(event)
        auto_revoke = is_r18 and effective_auto_revoke

        # R18 Docx 模式
        if is_r18 and effective_r18_docx:
            docx_path = self._docx_service.create_docx_with_images(images, tags=tags)
            if docx_path:
                if auto_revoke:
                    message_id = await self._send_file_with_revoke(
                        event, str(docx_path), docx_path.name
                    )
                    if message_id:
                        await self._schedule_revoke(
                            event, message_id, cfg.auto_revoke_delay
                        )
                        if cfg.msg_found_enabled:
                            yield event.plain_result(
                                cfg.format_found_message(
                                    len(images), cfg.auto_revoke_delay
                                )
                            )
                        return
                if cfg.msg_found_enabled:
                    yield event.plain_result(cfg.format_found_message(len(images)))
                yield event.chain_result(
                    [Comp.File(file=str(docx_path), name=docx_path.name)]
                )
                return
            yield event.plain_result("R18 Docx 封装失败，请稍后再试或联系管理员。")
            return

        # 尝试普通发送
        found_message = (
            cfg.format_found_message(len(images)) if cfg.msg_found_enabled else None
        )

        send_success = False
        try:
            if actual_send_mode == "forward":
                nodes = []
                for img_data in images:
                    node = Comp.Node(
                        uin=event.get_self_id(),
                        name="色图",
                        content=[Comp.Image.fromBytes(img_data)],
                    )
                    nodes.append(node)

                if auto_revoke:
                    message_id = await self._send_nodes_with_revoke(event, nodes)
                    if message_id:
                        await self._schedule_revoke(
                            event, message_id, cfg.auto_revoke_delay
                        )
                        if cfg.msg_found_enabled:
                            yield event.plain_result(
                                cfg.format_found_message(
                                    len(images), cfg.auto_revoke_delay
                                )
                            )
                        send_success = True
                else:
                    if found_message:
                        yield event.plain_result(found_message)
                    yield event.chain_result([Comp.Nodes(nodes)])
                    send_success = True
            else:
                if auto_revoke:
                    chain = [Comp.Image.fromBytes(img) for img in images]
                    message_id = await self._send_with_revoke_support(
                        event,
                        chain,
                        bool(event.get_group_id()),
                        event.get_group_id() or event.get_sender_id(),
                    )
                    if message_id:
                        await self._schedule_revoke(
                            event, message_id, cfg.auto_revoke_delay
                        )
                        if cfg.msg_found_enabled:
                            yield event.plain_result(
                                cfg.format_found_message(
                                    len(images), cfg.auto_revoke_delay
                                )
                            )
                        send_success = True
                else:
                    if found_message:
                        yield event.plain_result(found_message)
                    for img_data in images:
                        yield event.chain_result([Comp.Image.fromBytes(img_data)])
                    send_success = True
        except Exception as exc:
            logger.warning("send_images failed: %s, will try HTML card fallback", exc)
            send_success = False

        # 如果普通发送失败，尝试 HTML 卡片降级（使用已下载的图片）
        if not send_success and cfg.enable_html_card:
            logger.info("Attempting HTML card fallback with existing images")
            if self._ensure_html_renderer():
                try:
                    async for result in self._send_with_html_card(
                        event, images, actual_send_mode, auto_revoke
                    ):
                        yield result
                    return
                except Exception as exc:
                    logger.exception("HTML card fallback failed: %s", exc)
                    yield event.plain_result("图片发送失败，HTML 卡片发送也失败了。")
            else:
                logger.warning("HTML renderer not available for fallback")
                yield event.plain_result("图片发送失败，请稍后再试。")
        elif not send_success:
            yield event.plain_result("图片发送失败，请稍后再试。")

    async def _send_with_html_card(
        self,
        event: AstrMessageEvent,
        images: list[bytes],
        send_mode: str,
        auto_revoke: bool = False,
    ) -> AsyncGenerator[Any, None]:
        """使用 HTML 卡片包装已下载的图片发送。"""
        cfg = self._config

        if not self._html_renderer or not self._image_service:
            yield event.plain_result("HTML 渲染器不可用")
            return

        render_style = {
            "card_padding": cfg.html_card_padding,
            "card_gap": cfg.html_card_gap,
        }

        # 渲染 HTML 卡片
        html_image_data: list[bytes] = []
        for img_data in images:
            image_url = await self._html_renderer.render_single_image(
                context=self.plugin,
                image=img_data,
                style_options=render_style,
            )
            if image_url:
                try:
                    downloaded = await self._image_service.download_parallel(
                        [image_url]
                    )
                    if downloaded:
                        html_image_data.extend(downloaded)
                except Exception as exc:
                    logger.warning(
                        "[html-card] failed to download rendered image: %s", exc
                    )

        if not html_image_data:
            yield event.plain_result("HTML 卡片渲染失败")
            return

        # 发送渲染后的 HTML 卡片图片
        found_message = (
            cfg.format_found_message(len(html_image_data))
            if cfg.msg_found_enabled
            else None
        )

        if send_mode == "forward":
            nodes = []
            for img_data in html_image_data:
                node = Comp.Node(
                    uin=event.get_self_id(),
                    name="色图",
                    content=[Comp.Image.fromBytes(img_data)],
                )
                nodes.append(node)

            if auto_revoke:
                message_id = await self._send_nodes_with_revoke(event, nodes)
                if message_id:
                    await self._schedule_revoke(
                        event, message_id, cfg.auto_revoke_delay
                    )
                    if cfg.msg_found_enabled:
                        yield event.plain_result(
                            cfg.format_found_message(
                                len(html_image_data), cfg.auto_revoke_delay
                            )
                        )
                    return

            if found_message:
                yield event.plain_result(found_message)
            yield event.chain_result([Comp.Nodes(nodes)])
        else:
            if auto_revoke:
                chain = [Comp.Image.fromBytes(img) for img in html_image_data]
                message_id = await self._send_with_revoke_support(
                    event,
                    chain,
                    bool(event.get_group_id()),
                    event.get_group_id() or event.get_sender_id(),
                )
                if message_id:
                    await self._schedule_revoke(
                        event, message_id, cfg.auto_revoke_delay
                    )
                    if cfg.msg_found_enabled:
                        yield event.plain_result(
                            cfg.format_found_message(
                                len(html_image_data), cfg.auto_revoke_delay
                            )
                        )
                    return

            if found_message:
                yield event.plain_result(found_message)
            for img_data in html_image_data:
                yield event.chain_result([Comp.Image.fromBytes(img_data)])

    async def handle_llm_tool(
        self, event: AstrMessageEvent, count: int, tags: list[str] | str | None
    ) -> tuple[bool, str]:
        """处理 LLM 工具调用。"""
        cfg = self._config
        if self.is_group_blocked(event):
            return False, "该群聊已禁用此功能。"

        try:
            num = max(1, min(int(count), cfg.max_count))
        except (ValueError, TypeError):
            num = 1

        if isinstance(tags, list):
            parsed_tags = []
            for tag in tags:
                parsed_tags.extend(cfg.resolve_tags(str(tag).strip()))
        else:
            parsed_tags = cfg.resolve_tags(str(tags or ""))

        effective_content_mode = await self.get_effective_content_mode(event)
        is_r18 = self.determine_r18(effective_content_mode)
        downloaded = await self.fetch_and_download_images(num, parsed_tags, is_r18)

        if not downloaded:
            return False, "未能获取到图片或图片下载失败。"

        async for _ in self.send_images(event, downloaded, is_r18, parsed_tags):
            pass
        return True, f"已成功发送 {len(downloaded)} 张图片"
