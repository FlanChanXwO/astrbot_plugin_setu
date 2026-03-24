"""Setu 插件核心逻辑。"""

from __future__ import annotations

import asyncio
import random
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import httpx

import astrbot.api.message_components as Comp
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from ..config import SetuConfig
from ..providers import get_provider
from ..services import DocxService, HtmlCardRenderer, ImageService, UrlImageDiskCache
from ..session_config import SessionConfigManager
from .rate_limiter import SessionRequestLimiter
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
        self._rate_limiter = SessionRequestLimiter()
        self._docx_service = DocxService()
        self._revoke_tasks: set[asyncio.Task] = set()
        self._cache: UrlImageDiskCache | None = None
        self._image_service: ImageService | None = None
        self._html_renderer: HtmlCardRenderer | None = None

    async def initialize(self) -> None:
        """初始化核心组件。"""
        await self._revoke_manager.initialize()
        await self._session_config.initialize()
        await self._restore_pending_revokes()

        if (
            self._config.html_card_strategy in ("fallback", "always")
            or self._config.auto_handle_send_failure
        ):
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
                    await self._cache.cleanup_expired()
            self._image_service = ImageService(
                self._cache,
                concurrent_limit=self._config.download_concurrent_limit,
                timeout_seconds=self._config.download_timeout_seconds,
                enable_range_download=self._config.enable_range_download,
                range_segments=self._config.range_segments,
                range_threshold=self._config.range_threshold,
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

        # 调试日志
        logger.debug(
            "[content_mode] session_id=%s, is_group=%s, session_mode=%s, global_mode=%s",
            session_id,
            is_group,
            session_mode,
            self._config.content_mode,
        )

        if session_mode:
            logger.debug("[content_mode] Using session mode: %s", session_mode)
            return session_mode
        logger.debug("[content_mode] Using global mode: %s", self._config.content_mode)
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

    @staticmethod
    def determine_r18(content_mode: str) -> bool:
        """根据内容模式确定是否为 R18。"""
        if content_mode == "r18":
            return True
        if content_mode == "mix":
            return random.random() > 0.5
        return False

    @staticmethod
    def _resolve_send_mode(send_mode: str, image_count: int) -> str:
        if send_mode == "auto":
            return "forward" if image_count > 1 else "image"
        return send_mode

    def _ensure_html_renderer(self) -> bool:
        if self._html_renderer is not None:
            return True
        try:
            template_path = Path(__file__).parent.parent / "templates" / "setu.html"
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

    def _is_forward_supported(self, event: AstrMessageEvent) -> bool:
        """检查当前平台是否支持合并转发消息。

        目前支持的平台：OneBot v11 (aiocqhttp)
        """
        # 获取平台信息（多种方式）
        platform_name = None
        try:
            platform_type_name = "Unknown"
            # 方式1：通过 event.platform.name
            if hasattr(event, "platform") and event.platform:
                platform_obj = event.platform
                platform_type_name = type(platform_obj).__name__
                if hasattr(platform_obj, "name"):
                    platform_name = platform_obj.name

            # 方式2：通过 event.get_platform_name()
            if not platform_name and hasattr(event, "get_platform_name"):
                try:
                    platform_name = event.get_platform_name()
                except Exception:
                    pass

            # 方式3：通过 context 获取
            if not platform_name and hasattr(self, "plugin") and self.plugin:
                try:
                    ctx = getattr(self.plugin, "context", None)
                    if ctx and hasattr(ctx, "get_platform"):
                        platform = ctx.get_platform()
                        if platform and hasattr(platform, "name"):
                            platform_name = platform.name
                            platform_type_name = type(platform).__name__
                except Exception:
                    pass

            # 调试日志
            logger.debug(
                "[platform] Checking forward support: platform_name=%s, platform_type=%s",
                platform_name,
                platform_type_name,
            )

            # 支持的平台列表（检查名称）
            supported_platforms = (
                "aiocqhttp",
                "onebot11",
                "onebot",
                "go-cqhttp",
                "napcat",
                "llonebot",
            )
            if platform_name:
                platform_name_lower = platform_name.lower()
                for p in supported_platforms:
                    if p in platform_name_lower:
                        logger.debug("[platform] Forward supported: name match '%s'", p)
                        return True

            # 检查 platform 对象类型名
            if platform_type_name and any(
                p in platform_type_name.lower() for p in ("cqhttp", "onebot", "gocq")
            ):
                logger.debug(
                    "[platform] Forward supported: type match '%s'", platform_type_name
                )
                return True

            # 检查 event 是否有 bot 属性且看起来是 OneBot（有 call_action 方法）
            if hasattr(event, "bot") and event.bot:
                bot = event.bot
                if hasattr(bot, "call_action"):
                    logger.debug("[platform] Forward supported: bot has call_action")
                    return True

            # 检查 unified_msg_origin 格式
            if hasattr(event, "unified_msg_origin"):
                umo = event.unified_msg_origin
                if umo and isinstance(umo, str):
                    if any(p in umo.lower() for p in ("aiocqhttp", "onebot", "gocq")):
                        logger.debug(
                            "[platform] Forward supported: unified_msg_origin match"
                        )
                        return True

        except Exception as exc:
            logger.debug("[platform] Error checking forward support: %s", exc)

        logger.debug("[platform] Forward not supported for platform=%s", platform_name)
        return False

    @property
    def session_config(self) -> SessionConfigManager:
        return self._session_config

    @property
    def rate_limiter(self) -> SessionRequestLimiter:
        return self._rate_limiter

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

    async def _direct_send(self, event: AstrMessageEvent, chain: list) -> bool:
        """通过 context.send_message 直接发送消息，返回是否成功。"""
        try:
            result = event.chain_result(chain)

            # 检查图片大小，Telegram 等平台有 10MB 或 20MB 限制
            for comp in chain:
                if hasattr(comp, "file") and isinstance(comp.file, bytes):
                    size_mb = len(comp.file) / (1024 * 1024)
                    if size_mb > 10:  # Telegram 通常限制 10-20MB
                        logger.warning(
                            "[send] Image size %.2f MB may exceed platform limit",
                            size_mb,
                        )

            send_result = await self.plugin.context.send_message(
                event.unified_msg_origin, result
            )

            # 获取平台名称
            platform_name = getattr(event.platform, "name", "unknown")

            # 检查发送结果
            # 注意：某些平台（如 Telegram）send_message 可能返回 None 但实际发送成功
            # 只对特定平台严格检查返回值
            if send_result is None and platform_name == "aiocqhttp":
                # OneBot v11 平台应该返回消息 ID，如果没有可能是失败了
                logger.warning(
                    "[send] send_message returned None on %s, "
                    "platform may not support this message type",
                    platform_name,
                )
                return False

            # 对于其他平台（Telegram 等），不严格检查返回值
            logger.debug("[send] Direct send completed on %s", platform_name)
            return True
        except TimeoutError:
            logger.warning(
                "[send] Direct send timed out on %s",
                getattr(event.platform, "name", "unknown"),
            )
            return False
        except Exception as exc:
            logger.warning("[send] Direct send failed: %s", exc, exc_info=True)
            return False

    async def _direct_send_plain(self, event: AstrMessageEvent, text: str) -> bool:
        """直接发送纯文本消息，返回是否成功。"""
        try:
            result = event.plain_result(text)
            await self.plugin.context.send_message(event.unified_msg_origin, result)
            return True
        except Exception as exc:
            logger.warning("direct send plain failed: %s", exc)
            return False

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

        # 准备提示消息
        found_message = (
            cfg.format_found_message(len(images)) if cfg.msg_found_enabled else None
        )

        # 判断 HTML 卡片策略
        html_strategy = cfg.html_card_strategy
        use_html_always = html_strategy == "always"
        use_html_fallback = html_strategy == "fallback" or cfg.auto_handle_send_failure

        # 如果策略是 always，直接使用 HTML 卡片发送
        if use_html_always:
            if found_message:
                await self._direct_send_plain(event, found_message)
            send_success = await self._try_html_card_fallback(
                event, images, actual_send_mode, auto_revoke
            )
            if not send_success:
                yield event.plain_result("HTML 卡片发送失败，请检查网络或联系管理员。")
            return

        # 尝试普通发送（使用直接发送以捕获异常）
        send_success = False

        # 检测平台是否支持合并转发
        forward_supported = self._is_forward_supported(event)
        if actual_send_mode == "forward" and not forward_supported:
            logger.debug(
                "[send] Platform %s does not support forward messages, "
                "falling back to normal image send",
                getattr(event.platform, "name", "unknown"),
            )
            actual_send_mode = "image"

        if actual_send_mode == "forward":
            import time

            build_start = time.monotonic()
            nodes = []
            for img_data in images:
                node = Comp.Node(
                    uin=event.get_self_id(),
                    name="色图",
                    content=[Comp.Image.fromBytes(img_data)],
                )
                nodes.append(node)
            build_end = time.monotonic()
            logger.debug(
                "[forward] Built %d nodes in %.3fs", len(nodes), build_end - build_start
            )

            if auto_revoke:
                message_id = await self._send_nodes_with_revoke(event, nodes)
                if message_id:
                    await self._schedule_revoke(
                        event, message_id, cfg.auto_revoke_delay
                    )
                    if cfg.msg_found_enabled:
                        yield event.plain_result(
                            cfg.format_found_message(len(images), cfg.auto_revoke_delay)
                        )
                    send_success = True
            else:
                if found_message:
                    await self._direct_send_plain(event, found_message)
                # 使用优化的合并转发发送（绕过 AstrBot 内部处理）
                send_start = time.monotonic()
                send_success = await self._send_nodes_direct(event, nodes)
                logger.debug(
                    "[forward] Send nodes completed in %.3fs",
                    time.monotonic() - send_start,
                )
                # 如果合并转发失败（平台不支持），降级为普通图片发送
                if not send_success:
                    logger.info(
                        "[forward] Forward message not supported or failed, "
                        "falling back to normal image send"
                    )
                    chain = [Comp.Image.fromBytes(img) for img in images]
                    send_success = await self._direct_send(event, chain)
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
                            cfg.format_found_message(len(images), cfg.auto_revoke_delay)
                        )
                    send_success = True
            else:
                if found_message:
                    await self._direct_send_plain(event, found_message)
                # 将所有图片放在一条消息链中发送，提高速度和可靠性
                chain = [Comp.Image.fromBytes(img) for img in images]
                send_success = await self._direct_send(event, chain)

        # 如果普通发送失败，尝试 HTML 卡片降级（使用已下载的图片）
        if not send_success and use_html_fallback:
            logger.debug("Image send failed, attempting HTML card fallback")
            send_success = await self._try_html_card_fallback(
                event, images, actual_send_mode, auto_revoke
            )
            logger.debug("HTML card fallback result: %s", send_success)

        if not send_success:
            if use_html_fallback:
                yield event.plain_result(
                    "图片发送失败，HTML 卡片降级发送也失败了，请检查网络或联系管理员。"
                )
            else:
                yield event.plain_result(
                    "图片发送失败，可尝试在插件配置中启用 HTML 卡片模式作为备选方案。"
                )
        else:
            # 发送成功，yield 一个标记供调用者识别
            logger.debug("Images sent successfully: count=%d", len(images))
            yield {"send_success": True, "image_count": len(images)}

    async def _try_html_card_fallback(
        self,
        event: AstrMessageEvent,
        images: list[bytes],
        send_mode: str,
        auto_revoke: bool = False,
    ) -> bool:
        """使用 HTML 卡片包装已下载的图片发送，返回是否成功。"""
        cfg = self._config

        if not self._ensure_html_renderer() or not self._html_renderer:
            logger.warning("HTML renderer not available for fallback")
            return False

        render_style = {
            "card_padding": cfg.html_card_padding,
            "card_gap": cfg.html_card_gap,
        }

        # 渲染 HTML 卡片（现在直接返回字节数据）
        html_image_data: list[bytes] = []
        for i, img_data in enumerate(images):
            logger.debug("[html_fallback] Rendering image %d/%d", i + 1, len(images))
            rendered = await self._html_renderer.render_single_image(
                context=self.plugin,
                image=img_data,
                style_options=render_style,
            )
            if rendered:
                html_image_data.append(rendered)
                logger.debug(
                    "[html_fallback] Image %d rendered, size=%d", i + 1, len(rendered)
                )
            else:
                logger.warning("[html_fallback] Failed to render image %d", i + 1)

        if not html_image_data:
            logger.warning("HTML card rendering produced no images")
            return False

        logger.debug(
            "[html_fallback] Successfully rendered %d HTML cards", len(html_image_data)
        )

        # 发送渲染后的 HTML 卡片图片
        if send_mode == "forward" and self._is_forward_supported(event):
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
                        await self._direct_send_plain(
                            event,
                            cfg.format_found_message(
                                len(html_image_data), cfg.auto_revoke_delay
                            ),
                        )
                    return True
                return False

            send_success = await self._send_nodes_direct(event, nodes)
            # 如果合并转发失败，降级为普通发送
            if not send_success:
                logger.debug(
                    "[forward] HTML card forward send failed, falling back to normal send"
                )
                chain = [Comp.Image.fromBytes(img) for img in html_image_data]
                return await self._direct_send(event, chain)
            return True
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
                        await self._direct_send_plain(
                            event,
                            cfg.format_found_message(
                                len(html_image_data), cfg.auto_revoke_delay
                            ),
                        )
                    return True
                return False

            # 所有 HTML 卡片图片放在一条消息链中发送
            chain = [Comp.Image.fromBytes(img) for img in html_image_data]
            logger.debug(
                "[html_fallback] Sending %d HTML card images via direct send",
                len(chain),
            )
            result = await self._direct_send(event, chain)
            logger.info("[html_fallback] Direct send result: %s", result)
            return result

    async def verify_image_urls(self, urls: list[str]) -> list[str]:
        """验证图片 URL 是否可访问。

        使用 HEAD 请求快速验证 URL 是否返回 200。
        支持并发请求以提高性能。

        参数:
            urls: 图片 URL 列表

        返回:
            验证通过的 URL 列表
        """
        if not urls:
            return []

        valid_urls = []
        semaphore = asyncio.Semaphore(8)  # 限制并发数为8

        async def _check_single_url(client: httpx.AsyncClient, url: str) -> str | None:
            async with semaphore:
                try:
                    response = await client.head(url, follow_redirects=True)
                    if response.status_code == 200:
                        logger.debug("[url_verify] URL valid: %s", url)
                        return url
                    else:
                        logger.warning(
                            "[url_verify] URL returned %d: %s",
                            response.status_code,
                            url,
                        )
                except httpx.HTTPError as exc:
                    logger.warning(
                        "[url_verify] URL verification failed: %s - %s", url, exc
                    )
            return None

        async with httpx.AsyncClient(timeout=self._config.url_send_timeout) as client:
            tasks = [_check_single_url(client, url) for url in urls]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, str):
                valid_urls.append(result)

        return valid_urls

    async def send_images_by_url(
        self,
        event: AstrMessageEvent,
        urls: list[str],
        is_r18: bool,
        tags: list[str] | None = None,
    ):
        """通过 URL 直接发送图片（不下载）。

        参数:
            event: 消息事件
            urls: 图片 URL 列表
            is_r18: 是否为 R18 内容
            tags: 标签列表（保留用于接口一致性）
        """
        # tags 参数保留用于接口一致性，当前实现不使用
        _ = tags
        if not urls:
            yield event.plain_result("运气不好，没有获取到图片链接...")
            return

        cfg = self._config

        # 验证 URL（如果启用）
        if cfg.url_send_verify:
            valid_urls = await self.verify_image_urls(urls)
            if not valid_urls:
                yield event.plain_result("获取的图片链接均无法访问，请稍后再试。")
                return
            if len(valid_urls) < len(urls):
                logger.warning(
                    "[url_send] %d/%d URLs invalid, using valid ones",
                    len(urls) - len(valid_urls),
                    len(urls),
                )
        else:
            valid_urls = urls

        # 准备提示消息
        found_message = (
            cfg.format_found_message(len(valid_urls)) if cfg.msg_found_enabled else None
        )

        # 发送图片 URL
        if found_message:
            await self._direct_send_plain(event, found_message)

        # 构建消息链 - 使用 Comp.Image.fromURL
        chain = [Comp.Image.fromURL(url) for url in valid_urls]

        effective_auto_revoke = await self.get_effective_auto_revoke_r18(event)
        auto_revoke = is_r18 and effective_auto_revoke

        if auto_revoke:
            message_id = await self._send_with_revoke_support(
                event,
                chain,
                bool(event.get_group_id()),
                event.get_group_id() or event.get_sender_id(),
            )
            if message_id:
                await self._schedule_revoke(event, message_id, cfg.auto_revoke_delay)
                if cfg.msg_found_enabled:
                    yield event.plain_result(
                        cfg.format_found_message(len(valid_urls), cfg.auto_revoke_delay)
                    )
        else:
            await self._direct_send(event, chain)
            yield {"send_success": True, "image_count": len(valid_urls)}
