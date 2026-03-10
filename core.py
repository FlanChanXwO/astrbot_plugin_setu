"""Setu plugin core logic."""

from __future__ import annotations

import asyncio
import json
import random
import time
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import astrbot.api.message_components as Comp
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from .config import SetuConfig
from .docx_service import DocxService
from .html_renderer import HtmlCardRenderer
from .image_service import ImageService, UrlImageDiskCache
from .providers import get_provider


class RevokeManager:
    """Manages revoke.json for tracking revoked R18 messages."""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.revoke_file = data_dir / "revoke.json"
        self._lock = asyncio.Lock()
        self._data: dict[str, Any] = {"entries": {}, "meta": {}}

    async def initialize(self) -> None:
        """Initialize the revoke.json file."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        await self._load()

    async def _load(self) -> None:
        """Load revoke data from file."""
        if not self.revoke_file.exists():
            self._data = {"entries": {}, "meta": {"created_at": int(time.time())}}
            await self._save()
            return
        try:
            async with self._lock:
                content = self.revoke_file.read_text(encoding="utf-8")
                loaded = json.loads(content)
                self._data = {
                    "entries": loaded.get("entries", {}),
                    "meta": loaded.get("meta", {}),
                }
        except Exception:
            logger.exception("[revoke] Failed to load revoke.json, creating new")
            self._data = {"entries": {}, "meta": {"created_at": int(time.time())}}
            await self._save()

    async def _save(self) -> None:
        """Save revoke data to file."""
        try:
            tmp_path = self.revoke_file.with_suffix(".tmp")
            tmp_path.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp_path.replace(self.revoke_file)
        except Exception:
            logger.exception("[revoke] Failed to save revoke.json")

    async def add_entry(
        self,
        message_id: str,
        platform: str,
        session_id: str,
        is_group: bool,
        revoke_time: int,
    ) -> None:
        """Add a new entry to be revoked."""
        async with self._lock:
            self._data["entries"][message_id] = {
                "message_id": message_id,
                "platform": platform,
                "session_id": session_id,
                "is_group": is_group,
                "revoke_time": revoke_time,
                "created_at": int(time.time()),
                "revoked": False,
            }
            await self._save()
            logger.debug("[revoke] Added entry message_id=%s revoke_time=%d", message_id, revoke_time)

    async def mark_revoked(self, message_id: str) -> None:
        """Mark an entry as revoked."""
        async with self._lock:
            if message_id in self._data["entries"]:
                self._data["entries"][message_id]["revoked"] = True
                self._data["entries"][message_id]["revoked_at"] = int(time.time())
                await self._save()
                logger.debug("[revoke] Marked as revoked message_id=%s", message_id)

    def get_pending_entries(self) -> list[dict[str, Any]]:
        """Get all pending entries that need to be revoked."""
        now = int(time.time())
        pending = []
        for entry in self._data["entries"].values():
            if not entry.get("revoked", False) and entry.get("revoke_time", 0) <= now:
                pending.append(entry)
        return pending

    async def cleanup_old_entries(self, max_age_days: int = 7) -> int:
        """Remove old entries older than max_age_days."""
        cutoff = int(time.time()) - (max_age_days * 86400)
        async with self._lock:
            to_remove = [
                msg_id
                for msg_id, entry in self._data["entries"].items()
                if entry.get("revoked", False) and entry.get("revoked_at", 0) < cutoff
            ]
            for msg_id in to_remove:
                del self._data["entries"][msg_id]
            if to_remove:
                await self._save()
            return len(to_remove)


class SetuCore:
    """Business logic handler for Setu plugin."""

    def __init__(self, plugin, config: SetuConfig, plugin_data_dir: Path):
        self.plugin = plugin
        self.config = config
        self.plugin_data_dir = plugin_data_dir
        self._cache: UrlImageDiskCache | None = None
        self._image_service: ImageService | None = None
        self._docx_service = DocxService()
        self._html_renderer: HtmlCardRenderer | None = None
        self._revoke_manager = RevokeManager(plugin_data_dir)

        if config.enable_html_card:
            template_path = Path(__file__).parent / "templates" / "main.html"
            self._html_renderer = HtmlCardRenderer(template_path)

    async def initialize(self) -> None:
        """Initialize cache and dependent services."""
        # Initialize revoke manager
        try:
            await self._revoke_manager.initialize()
            logger.info("[revoke] RevokeManager initialized")
        except Exception:
            logger.exception("[revoke] Failed to initialize RevokeManager")

        try:
            if self.config.cache_enabled:
                cache_dir = self.plugin_data_dir / "cache"
                self._cache = UrlImageDiskCache(
                    cache_dir=cache_dir,
                    ttl_hours=self.config.cache_ttl_hours,
                    max_items=self.config.cache_max_items,
                    enabled=True,
                )
                await self._cache.initialize(
                    cleanup_on_start=self.config.cache_cleanup_on_start
                )
                logger.info(
                    "[setu.cache] enabled dir=%s ttl_hours=%d max_items=%d",
                    cache_dir,
                    self.config.cache_ttl_hours,
                    self.config.cache_max_items,
                )
            self._image_service = ImageService(self._cache)
        except Exception:
            logger.exception(
                "SetuCore initialize failed, fallback to no-cache ImageService"
            )
            self._cache = None
            self._image_service = ImageService(None)

    def _get_provider(self):
        cfg = self.config
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

    def _determine_r18(self, content_mode: str) -> bool:
        if content_mode == "r18":
            return True
        if content_mode == "mix":
            return random.random() > 0.5
        return False

    def _resolve_send_mode(self, send_mode: str, image_count: int) -> str:
        if send_mode == "auto":
            actual_send_mode = "forward" if image_count > 1 else "image"
            logger.info("[auto-send] count=%d mode=%s", image_count, actual_send_mode)
            return actual_send_mode
        return send_mode

    def _ensure_html_renderer(self) -> bool:
        if self._html_renderer is not None:
            return True
        try:
            template_path = Path(__file__).parent / "templates" / "main.html"
            self._html_renderer = HtmlCardRenderer(template_path)
            return True
        except Exception:
            logger.exception("html renderer initialize failed")
            return False

    def _is_group_blocked(self, event: AstrMessageEvent) -> bool:
        try:
            group_id = event.message_obj.group_id
            if group_id and self.config.is_group_blocked(str(group_id)):
                return True
        except Exception:
            logger.debug("failed to inspect group id for blocked check")
        return False

    def _get_bot_api(self, event: AstrMessageEvent) -> Any | None:
        """Get the underlying bot API client from event."""
        return getattr(event, "bot", None)

    async def _revoke_message(
        self, event: AstrMessageEvent, message_id: str | int
    ) -> bool:
        """Revoke a message by its ID."""
        try:
            bot = self._get_bot_api(event)
            if not bot:
                logger.warning("[revoke] No bot instance available")
                return False

            # Try different parameter formats for different platforms
            params_list = [
                {"message_id": message_id},
                {"message_id": int(message_id) if str(message_id).isdigit() else message_id},
            ]

            for params in params_list:
                try:
                    await bot.call_action("delete_msg", **params)
                    logger.info("[revoke] Successfully revoked message %s", message_id)
                    return True
                except Exception as exc:
                    logger.debug("[revoke] Failed with params %s: %s", params, exc)
                    continue

            logger.warning("[revoke] All attempts failed for message %s", message_id)
            return False
        except Exception:
            logger.exception("[revoke] Error revoking message %s", message_id)
            return False

    async def _schedule_revoke(
        self, event: AstrMessageEvent, message_id: str | int, delay: int
    ) -> None:
        """Schedule a message to be revoked after delay seconds."""
        if not message_id:
            return

        platform = event.get_platform_name()
        session_id = event.get_session_id()
        is_group = bool(event.get_group_id())
        revoke_time = int(time.time()) + delay

        # Get bot reference for later use
        bot = self._get_bot_api(event)
        bot_id = id(bot) if bot else None

        await self._revoke_manager.add_entry(
            str(message_id), platform, session_id, is_group, revoke_time
        )

        # Start a background task to revoke after delay
        # Store necessary info instead of event reference
        asyncio.create_task(
            self._delayed_revoke(
                str(message_id), delay, platform, session_id, is_group, bot_id, bot
            )
        )

    async def _delayed_revoke(
        self,
        message_id: str,
        delay: int,
        platform: str,
        session_id: str,
        is_group: bool,
        bot_id: int | None,
        bot: Any | None,
    ) -> None:
        """Background task to revoke message after delay."""
        await asyncio.sleep(delay)

        # Try to revoke using stored bot reference
        success = False
        if bot and bot_id:
            try:
                params_list = [
                    {"message_id": message_id},
                    {"message_id": int(message_id) if str(message_id).isdigit() else message_id},
                ]
                for params in params_list:
                    try:
                        await bot.call_action("delete_msg", **params)
                        success = True
                        break
                    except Exception:
                        continue
            except Exception as exc:
                logger.warning("[revoke] Background revoke failed: %s", exc)

        if success:
            await self._revoke_manager.mark_revoked(message_id)
            logger.info("[revoke] Successfully revoked message %s", message_id)
        else:
            logger.warning("[revoke] Failed to revoke message %s", message_id)

    async def _send_with_revoke_support(
        self,
        event: AstrMessageEvent,
        chain: list[Any],
        is_group: bool,
        session_id: str,
    ) -> str | None:
        """Send message and return message_id for revoke support.

        Returns the message_id if successful, None otherwise.
        """
        try:
            bot = self._get_bot_api(event)
            if not bot:
                return None

            # Parse chain to OneBot format if possible
            messages = []
            for comp in chain:
                if isinstance(comp, Comp.Plain):
                    if comp.text.strip():
                        messages.append({"type": "text", "data": {"text": comp.text}})
                elif isinstance(comp, Comp.Image):
                    # Handle image - convert to base64 if needed
                    if comp.file and comp.file.startswith("base64://"):
                        messages.append({"type": "image", "data": {"file": comp.file}})
                    elif comp.file:
                        messages.append({"type": "image", "data": {"file": comp.file}})
                    elif comp.url:
                        messages.append({"type": "image", "data": {"file": comp.url}})
                elif isinstance(comp, Comp.File):
                    if comp.file:
                        messages.append({"type": "file", "data": {"file": comp.file}})

            if not messages:
                return None

            # Call send API based on message type
            if is_group:
                result = await bot.call_action(
                    "send_group_msg",
                    group_id=int(session_id) if session_id.isdigit() else session_id,
                    message=messages,
                )
            else:
                result = await bot.call_action(
                    "send_private_msg",
                    user_id=int(session_id) if session_id.isdigit() else session_id,
                    message=messages,
                )

            # Extract message_id from result
            if isinstance(result, dict):
                data = result.get("data", result)
                message_id = data.get("message_id") if isinstance(data, dict) else None
                if message_id:
                    return str(message_id)
            return None
        except Exception:
            logger.exception("[revoke] Failed to send with revoke support")
            return None

    async def _send_file_with_revoke(
        self,
        event: AstrMessageEvent,
        file_path: str,
        file_name: str,
    ) -> str | None:
        """Send file as message and return message_id for revoke support.

        Note: Uses send_group_msg/send_private_msg with file segment instead of
        upload_group_file, so we can get message_id for revoke.
        Falls back to normal file send if file is too large (>5MB).
        """
        try:
            bot = self._get_bot_api(event)
            if not bot:
                return None

            is_group = bool(event.get_group_id())
            session_id = event.get_group_id() or event.get_sender_id()

            # Check file size
            path_obj = Path(file_path)
            file_size = path_obj.stat().st_size
            max_size = 5 * 1024 * 1024  # 5MB limit for base64

            if file_size > max_size:
                logger.warning(
                    "[revoke] File too large (%d bytes > %d), cannot use revoke support",
                    file_size,
                    max_size,
                )
                return None

            # Convert file to base64 for sending as message
            import base64

            file_data = path_obj.read_bytes()
            file_b64 = base64.b64encode(file_data).decode()

            messages = [
                {"type": "file", "data": {"file": f"base64://{file_b64}", "name": file_name}}
            ]

            if is_group:
                result = await bot.call_action(
                    "send_group_msg",
                    group_id=int(session_id) if str(session_id).isdigit() else session_id,
                    message=messages,
                )
            else:
                result = await bot.call_action(
                    "send_private_msg",
                    user_id=int(session_id) if str(session_id).isdigit() else session_id,
                    message=messages,
                )

            # Extract message_id from result
            if isinstance(result, dict):
                data = result.get("data", result)
                message_id = data.get("message_id") if isinstance(data, dict) else None
                if message_id:
                    return str(message_id)
            return None
        except Exception:
            logger.exception("[revoke] Failed to send file with revoke support")
            return None

    async def _send_nodes_with_revoke(
        self,
        event: AstrMessageEvent,
        nodes: list[Comp.Node],
    ) -> str | None:
        """Send forward nodes and return message_id for revoke support."""
        try:
            bot = self._get_bot_api(event)
            if not bot:
                return None

            is_group = bool(event.get_group_id())
            session_id = event.get_group_id() or event.get_sender_id()

            # Convert nodes to dict format
            messages = []
            for node in nodes:
                node_dict = await node.to_dict()
                messages.append(node_dict)

            if is_group:
                result = await bot.call_action(
                    "send_group_forward_msg",
                    group_id=int(session_id) if str(session_id).isdigit() else session_id,
                    messages=messages,
                )
            else:
                result = await bot.call_action(
                    "send_private_forward_msg",
                    user_id=int(session_id) if str(session_id).isdigit() else session_id,
                    messages=messages,
                )

            # Extract message_id from result
            if isinstance(result, dict):
                data = result.get("data", result)
                message_id = data.get("message_id") if isinstance(data, dict) else None
                if message_id:
                    return str(message_id)
            return None
        except Exception:
            logger.exception("[revoke] Failed to send nodes with revoke support")
            return None

    async def fetch_and_download_images(
        self, num: int, tags: list[str], is_r18: bool
    ) -> list[bytes]:
        provider = None
        try:
            provider = self._get_provider()
        except Exception:
            logger.exception("provider initialization failed")
            return []

        if not provider:
            logger.error("no provider available")
            return []

        exclude_ai = self.config.exclude_ai
        max_replenish = self.config.max_replenish_rounds

        try:
            img_urls = await provider.fetch_image_urls(
                num=num,
                tags=tags,
                r18=is_r18,
                exclude_ai=exclude_ai,
            )
        except Exception as exc:
            logger.error("provider fetch failed: %s", exc)
            return []

        if not img_urls:
            logger.info("provider returned empty urls")
            return []

        if not self._image_service:
            logger.error("image service unavailable")
            return []

        downloaded = await self._image_service.download_parallel(img_urls)
        logger.info(
            "initial download target=%d success=%d failed=%d",
            num,
            len(downloaded),
            max(0, num - len(downloaded)),
        )

        round_num = 0
        while len(downloaded) < num and round_num < max_replenish:
            missing = num - len(downloaded)
            logger.info(
                "replenish round %d/%d missing=%d",
                round_num + 1,
                max_replenish,
                missing,
            )
            try:
                extra_urls = await provider.fetch_image_urls(
                    num=missing,
                    tags=tags,
                    r18=is_r18,
                    exclude_ai=exclude_ai,
                )
                if extra_urls:
                    extra_downloaded = await self._image_service.download_parallel(
                        extra_urls
                    )
                    downloaded.extend(extra_downloaded)
            except Exception as exc:
                logger.warning("replenish round %d failed: %s", round_num + 1, exc)
            round_num += 1
        return downloaded

    async def send_images(
        self,
        event: AstrMessageEvent,
        images: list[bytes],
        is_r18: bool,
    ) -> AsyncGenerator[Any, None]:
        if not images:
            yield event.plain_result("运气不好，一张图都没拿到...")
            return

        cfg = self.config
        send_mode = cfg.send_mode
        enable_html_card = cfg.enable_html_card and self._html_renderer is not None
        auto_revoke = is_r18 and cfg.auto_revoke_r18

        actual_send_mode = self._resolve_send_mode(send_mode, len(images))

        # Handle R18 docx mode with auto-revoke support
        if is_r18 and cfg.r18_docx_mode:
            logger.info("[r18] use docx wrapper")
            docx_path = self._docx_service.create_docx_with_images(images)
            if docx_path:
                if auto_revoke:
                    # Send file directly to get message_id
                    message_id = await self._send_file_with_revoke(
                        event, str(docx_path), "setu.docx"
                    )
                    if message_id:
                        await self._schedule_revoke(
                            event, message_id, cfg.auto_revoke_delay
                        )
                        if cfg.msg_found_enabled:
                            yield event.plain_result(
                                f"{cfg.format_found_message(len(images))}（已封装，将在 {cfg.auto_revoke_delay} 秒后自动撤回）"
                            )
                        logger.info(
                            "[r18] Scheduled docx revoke in %ds, message_id=%s",
                            cfg.auto_revoke_delay,
                            message_id,
                        )
                    else:
                        # Fallback to normal file send if revoke setup failed (e.g., file too large)
                        if cfg.msg_found_enabled:
                            yield event.plain_result(
                                cfg.format_found_message(len(images)) + "（已封装，文件过大无法自动撤回）"
                            )
                        yield event.file_result(str(docx_path), "setu.docx")
                else:
                    if cfg.msg_found_enabled:
                        yield event.plain_result(
                            cfg.format_found_message(len(images)) + "（已封装）"
                        )
                    yield event.file_result(str(docx_path), "setu.docx")
                return
            logger.warning("docx wrapping failed, fallback to regular send")

        if enable_html_card:
            try:
                async for result in self._send_with_html_card(
                    event, images, actual_send_mode, auto_revoke
                ):
                    yield result
                return
            except Exception:
                logger.exception("html card send failed, fallback to regular send")

        async for result in self._send_images_fallback(
            event, images, actual_send_mode, auto_revoke
        ):
            yield result

    async def _send_with_html_card(
        self,
        event: AstrMessageEvent,
        images: list[bytes],
        send_mode: str,
        auto_revoke: bool = False,
    ) -> AsyncGenerator[Any, None]:
        cfg = self.config
        html_card_mode = cfg.html_card_mode
        logger.info("[html-card] mode=%s auto_revoke=%s", html_card_mode, auto_revoke)

        if not self._html_renderer:
            logger.warning("html renderer unavailable")
            async for result in self._send_images_fallback(
                event, images, send_mode, auto_revoke
            ):
                yield result
            return

        render_style = {
            "card_padding": cfg.html_card_padding,
            "card_gap": cfg.html_card_gap,
        }

        if html_card_mode == "multiple":
            html_image_urls: list[str] = []
            for img_data in images:
                image_url = await self._html_renderer.render_single_image(
                    context=self.plugin,
                    image=img_data,
                    style_options=render_style,
                )
                if image_url:
                    html_image_urls.append(image_url)

            if html_image_urls:
                nodes = []
                for img_url in html_image_urls:
                    node = Comp.Node(
                        uin=event.get_self_id(),
                        name="色图",
                        content=[Comp.Image.fromURL(img_url)],
                    )
                    nodes.append(node)

                if auto_revoke:
                    # For forward messages, we need to send and get message_id
                    message_id = await self._send_nodes_with_revoke(event, nodes)
                    if message_id:
                        await self._schedule_revoke(
                            event, message_id, cfg.auto_revoke_delay
                        )
                        # Send combined notice with found message
                        if cfg.msg_found_enabled:
                            notice = f"{cfg.format_found_message(len(html_image_urls))}\n将在 {cfg.auto_revoke_delay} 秒后自动撤回~"
                            yield event.plain_result(notice)
                        logger.info(
                            "[r18] Scheduled forward revoke in %ds, message_id=%s",
                            cfg.auto_revoke_delay,
                            message_id,
                        )
                    else:
                        # Fallback to normal yield
                        if cfg.msg_found_enabled:
                            yield event.plain_result(
                                cfg.format_found_message(len(html_image_urls))
                            )
                        yield event.chain_result([Comp.Nodes(nodes)])
                else:
                    if cfg.msg_found_enabled:
                        yield event.plain_result(
                            cfg.format_found_message(len(html_image_urls))
                        )
                    yield event.chain_result([Comp.Nodes(nodes)])
                return

            yield event.plain_result("图片包装失败，尝试直接发送...")
            async for result in self._send_images_fallback(
                event, images, send_mode, auto_revoke
            ):
                yield result
            return

        image_url = await self._html_renderer.render_images(
            context=self.plugin,
            images=images,
            style_options=render_style,
        )
        if image_url:
            if auto_revoke:
                # Send directly to get message_id
                chain = [Comp.Image.fromURL(image_url)]
                if send_mode == "forward":
                    node = Comp.Node(
                        uin=event.get_self_id(),
                        name="色图",
                        content=chain,
                    )
                    message_id = await self._send_nodes_with_revoke(event, [node])
                else:
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
                    # Send combined notice with found message
                    if cfg.msg_found_enabled:
                        notice = f"{cfg.format_found_message(len(images))}\n将在 {cfg.auto_revoke_delay} 秒后自动撤回~"
                        yield event.plain_result(notice)
                    logger.info(
                        "[r18] Scheduled html-card revoke in %ds, message_id=%s",
                        cfg.auto_revoke_delay,
                        message_id,
                    )
                else:
                    # Fallback: use normal yield
                    if cfg.msg_found_enabled:
                        yield event.plain_result(cfg.format_found_message(len(images)))
                    if send_mode == "forward":
                        node = Comp.Node(
                            uin=event.get_self_id(),
                            name="色图",
                            content=[Comp.Image.fromURL(image_url)],
                        )
                        yield event.chain_result([node])
                    else:
                        yield event.image_result(image_url)
            else:
                if cfg.msg_found_enabled:
                    yield event.plain_result(cfg.format_found_message(len(images)))
                if send_mode == "forward":
                    node = Comp.Node(
                        uin=event.get_self_id(),
                        name="色图",
                        content=[Comp.Image.fromURL(image_url)],
                    )
                    yield event.chain_result([node])
                else:
                    yield event.image_result(image_url)
            return

        yield event.plain_result("图片包装失败，尝试直接发送...")
        async for result in self._send_images_fallback(
            event, images, send_mode, auto_revoke
        ):
            yield result

    async def _send_images_fallback(
        self,
        event: AstrMessageEvent,
        images: list[bytes],
        send_mode: str,
        auto_revoke: bool = False,
    ) -> AsyncGenerator[Any, None]:
        if not self._image_service:
            logger.error("image service unavailable in fallback")
            yield event.plain_result("插件内部错误：图片服务不可用。")
            return
        cfg = self.config
        found_message = (
            cfg.format_found_message(len(images)) if cfg.msg_found_enabled else None
        )

        if auto_revoke:
            # For auto-revoke, we need to send directly to get message_id
            if send_mode == "forward":
                nodes = []
                for img_data in images:
                    node = Comp.Node(
                        uin=event.get_self_id(),
                        name="色图",
                        content=[Comp.Image.fromBytes(img_data)],
                    )
                    nodes.append(node)
                message_id = await self._send_nodes_with_revoke(event, nodes)
            else:
                # Send images with found message
                chain: list[Any] = []
                if found_message:
                    chain.append(Comp.Plain(found_message))
                for img_data in images:
                    chain.append(Comp.Image.fromBytes(img_data))
                message_id = await self._send_with_revoke_support(
                    event,
                    chain,
                    bool(event.get_group_id()),
                    event.get_group_id() or event.get_sender_id(),
                )

            if message_id:
                await self._schedule_revoke(event, message_id, cfg.auto_revoke_delay)
                # Send revoke notice
                notice = f"R18 内容已发送，将在 {cfg.auto_revoke_delay} 秒后自动撤回~"
                yield event.plain_result(notice)
                logger.info(
                    "[r18] Scheduled fallback revoke in %ds, message_id=%s",
                    cfg.auto_revoke_delay,
                    message_id,
                )
            else:
                logger.warning("[r18] Failed to get message_id for revoke, using yield")
                if send_mode == "forward":
                    async for result in self._image_service.send_forward(
                        event, images, "色图"
                    ):
                        yield result
                else:
                    async for result in self._image_service.send_images(
                        event, images, found_message
                    ):
                        yield result
        else:
            if send_mode == "forward":
                async for result in self._image_service.send_forward(event, images, "色图"):
                    yield result
            else:
                async for result in self._image_service.send_images(
                    event, images, found_message
                ):
                    yield result

    async def _send_event_result_to_origin(
        self, event: AstrMessageEvent, result: Any
    ) -> None:
        from astrbot.api.event import MessageChain

        chain = getattr(result, "chain", None) or []
        await self.plugin.context.send_message(
            event.unified_msg_origin, MessageChain(chain)
        )

    async def _send_generator_results_to_origin(
        self, event: AstrMessageEvent, generator: AsyncGenerator[Any, None]
    ) -> tuple[int, int]:
        sent_count = 0
        media_count = 0
        async for result in generator:
            chain = getattr(result, "chain", None) or []
            await self._send_event_result_to_origin(event, result)
            sent_count += 1
            if any(
                isinstance(
                    comp,
                    (Comp.Image, Comp.File, Comp.Node, Comp.Nodes),
                )
                for comp in chain
            ):
                media_count += 1
        return sent_count, media_count

    async def _send_llm_error_message(self, event: AstrMessageEvent) -> None:
        from astrbot.api.event import MessageChain

        await self.plugin.context.send_message(
            event.unified_msg_origin,
            MessageChain([Comp.Plain(self.config.msg_send_failed_text)]),
        )

    async def _try_llm_html_fallback_send(
        self, event: AstrMessageEvent, images: list[bytes], send_mode: str
    ) -> bool:
        if not self._ensure_html_renderer():
            return False
        try:
            _, media_count = await self._send_generator_results_to_origin(
                event, self._send_with_html_card(event, images, send_mode)
            )
            return media_count > 0
        except Exception as exc:
            logger.warning("llm html fallback send failed: %s", exc)
            return False

    async def handle_llm_tool(
        self, event: AstrMessageEvent, count: int, tags: list[str] | str | None
    ) -> tuple[bool, str]:
        cfg = self.config
        if self._is_group_blocked(event):
            return False, "该群聊已禁用此功能。"

        try:
            num = max(1, min(int(count), cfg.max_count))
        except Exception:
            num = 1
        if isinstance(tags, list):
            normalized_tags = [str(t).strip() for t in tags if str(t).strip()]
            parsed_tags: list[str] = []
            for tag in normalized_tags:
                parsed_tags.extend(cfg.resolve_tags(tag))
        else:
            parsed_tags = cfg.resolve_tags(str(tags or ""))

        is_r18 = self._determine_r18(cfg.content_mode)
        downloaded = await self.fetch_and_download_images(num, parsed_tags, is_r18)
        if not downloaded:
            return False, "未能获取到图片或图片下载失败。"

        actual_send_mode = self._resolve_send_mode(cfg.send_mode, len(downloaded))
        try:
            _, media_count = await self._send_generator_results_to_origin(
                event, self.send_images(event, downloaded, is_r18)
            )
            if media_count > 0:
                return True, f"已成功发送 {len(downloaded)} 张图片"
        except Exception as exc:
            logger.warning("llm primary send failed: %s", exc)

        if cfg.auto_handle_send_failure:
            html_sent = await self._try_llm_html_fallback_send(
                event, downloaded, actual_send_mode
            )
            if html_sent:
                return True, f"已发送 {len(downloaded)} 张图片（自动HTML降级）"

        try:
            await self._send_llm_error_message(event)
        except Exception as notify_exc:
            logger.warning("llm send-failed notice failed: %s", notify_exc)
        return False, cfg.msg_send_failed_text
