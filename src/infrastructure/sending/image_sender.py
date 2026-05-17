"""Image sender service for adapter-level image delivery."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import astrbot.api.message_components as Comp
from astrbot.api.event import AstrMessageEvent

from ...application.session_config import SessionConfigService
from ...application.setu.dto import ImagePayload
from ...shared import get_logger
from ...shared.send_cache import schedule_send_cache_cleanup
from ..astrbot.config import get_config, get_plugin_context
from ..astrbot.session_identity import get_event_session_identity
from ..persistence import get_session_config_repo
from .dto import SendOptions
from .napcat_stream import upload_file_stream
from .send_strategies import (
    DirectSendStrategy,
    ForwardSendStrategy,
    HtmlCardFallbackStrategy,
    resolve_send_mode,
)

ImageItem = Path | bytes | Comp.Image
logger = get_logger()


class ImageSender:
    """Send images with send-mode, stream-upload, and fallback strategies."""

    def __init__(self, config: Any = None, log: Any = None) -> None:
        self._user_config = config
        self._log = log or logger
        self._html_renderer: Any = None
        self._forward_supported_cache: dict[str, bool] = {}

    @property
    def _config(self):
        return self._user_config or get_config()

    @property
    def _context(self):
        ctx = get_plugin_context()
        if ctx is None:
            raise RuntimeError("Plugin context not initialized")
        return ctx

    async def _build_options(
        self, event: AstrMessageEvent, is_r18: bool = False
    ) -> SendOptions:
        config = self._config
        if not config:
            return SendOptions(
                send_mode="image",
                use_html_card=False,
                auto_revoke=False,
                revoke_delay=30,
                r18_docx_mode=False,
                napcat_stream_mode="fallback",
            )

        send_mode = config.send_mode
        auto_revoke = config.auto_revoke_r18 if is_r18 else False
        r18_docx_mode = config.r18_docx_mode if is_r18 else False

        try:
            identity = get_event_session_identity(event)
            service = SessionConfigService(get_session_config_repo())
            snapshot = await service.get_snapshot(
                identity.session_id,
                identity.session_type,
                identity.display_name,
            )
            send_mode = str(snapshot.effective["setu.send_mode"])
            if is_r18:
                auto_revoke = bool(snapshot.effective["setu.auto_revoke"])
                r18_docx_mode = bool(snapshot.effective["setu.r18_docx"])
        except Exception as exc:
            self._log.debug(
                "[send] failed to apply session overrides: session=%s, error=%s",
                getattr(identity, "session_id", "unknown"),
                exc,
            )

        html_card_strategy = config.html_card_strategy
        return SendOptions(
            send_mode=send_mode,
            use_html_card=html_card_strategy != "never",
            auto_revoke=auto_revoke,
            revoke_delay=config.auto_revoke_delay,
            r18_docx_mode=r18_docx_mode,
            html_padding=config.html_card_padding,
            html_gap=config.html_card_gap,
            html_card_strategy=html_card_strategy,
            napcat_stream_mode=config.napcat_stream_mode,
        )

    def set_html_renderer(self, renderer: Any) -> None:
        """Set HTML card renderer."""
        self._html_renderer = renderer

    async def send_images(
        self,
        payload: ImagePayload,
        event: AstrMessageEvent,
    ) -> AsyncGenerator[Any, None]:
        """Send a fetched image payload to the current AstrBot event."""
        options = await self._build_options(event, payload.r18)
        items = self._payload_items(payload)
        self._log_send_summary(event, payload, items, options)
        if not items:
            self._log.warning(
                "[send] empty payload: session=%s, tags=%s, urls=%d",
                self._session_label(event),
                ",".join(payload.tags) or "-",
                len(payload.urls),
            )
            yield event.plain_result("运气不好，一张图都没拿到...")
            return

        if payload.r18 and options.r18_docx_mode:
            docx_images = await self._read_image_bytes(items)
            docx_yielded = False
            if docx_images:
                async for result in self._send_r18_docx(
                    event, docx_images, payload.tags, options
                ):
                    docx_yielded = True
                    yield result
            if docx_yielded:
                schedule_send_cache_cleanup()
                return

        found_message = self._format_found_message(
            payload.count,
            options.revoke_delay if options.auto_revoke else None,
        )
        chain = self._build_image_chain(items)

        if options.html_card_strategy == "always":
            self._log.info(
                "[send] html-card-only mode: session=%s, count=%d",
                self._session_label(event),
                payload.count,
            )
            if found_message:
                await self._send_plain_text(event, found_message)
            success = await self._try_html_card_fallback(
                event, chain, options, payload.r18
            )
            if not success:
                yield event.plain_result(self._send_failed_message())
            else:
                yield {"send_success": True, "image_count": payload.count}
            schedule_send_cache_cleanup()
            return

        if found_message:
            await self._send_plain_text(event, found_message)

        supports_forward = self._is_forward_supported(event)
        effective_mode = resolve_send_mode(
            options.send_mode, payload.count, supports_forward
        )
        self._log.info(
            "[send] dispatch start: session=%s, platform=%s, mode=%s, supports_forward=%s, napcat_stream=%s, html_fallback=%s",
            self._session_label(event),
            self._get_platform_name(event) or "unknown",
            effective_mode,
            supports_forward,
            options.napcat_stream_mode,
            options.use_html_card,
        )
        send_success = await self._send_chain(event, chain, effective_mode, options)

        if (
            not send_success
            and options.napcat_stream_mode == "fallback"
            and self._has_local_image_paths(chain)
        ):
            self._log.warning(
                "[send] primary send failed, trying NapCat stream fallback: session=%s, mode=%s",
                self._session_label(event),
                effective_mode,
            )
            stream_chain, changed = await self._stream_upload_chain(event, chain)
            if changed:
                self._log.info(
                    "[send] NapCat stream upload rebuilt chain: session=%s, count=%d",
                    self._session_label(event),
                    len(stream_chain),
                )
                send_success = await self._send_chain(
                    event,
                    stream_chain,
                    effective_mode,
                    self._without_stream_upload(options),
                )
            else:
                self._log.warning(
                    "[send] NapCat stream fallback skipped: session=%s, no files uploaded",
                    self._session_label(event),
                )

        if not send_success and options.use_html_card:
            self._log.warning(
                "[send] image send failed, attempting HTML card fallback: session=%s, mode=%s",
                self._session_label(event),
                effective_mode,
            )
            send_success = await self._try_html_card_fallback(
                event, chain, options, payload.r18
            )

        if not send_success:
            self._log.error(
                "[send] all send strategies failed: session=%s, count=%d, mode=%s, html_strategy=%s, napcat_stream=%s",
                self._session_label(event),
                payload.count,
                effective_mode,
                options.html_card_strategy,
                options.napcat_stream_mode,
            )
            yield event.plain_result(self._send_failed_message())
        else:
            self._log.info(
                "[send] completed: session=%s, count=%d, mode=%s",
                self._session_label(event),
                payload.count,
                effective_mode,
            )
            yield {"send_success": True, "image_count": payload.count}

        schedule_send_cache_cleanup()

    async def _send_chain(
        self,
        event: AstrMessageEvent,
        chain: list[Comp.Image],
        effective_mode: str,
        options: SendOptions,
    ) -> bool:
        """Send an already-built image chain."""
        if options.napcat_stream_mode == "always":
            self._log.info(
                "[send] pre-upload via NapCat stream: session=%s, count=%d",
                self._session_label(event),
                len(chain),
            )
            streamed_chain, changed = await self._stream_upload_chain(event, chain)
            if changed:
                chain = streamed_chain

        if effective_mode == "forward":
            return await ForwardSendStrategy(self._context).send(
                event, chain, options.auto_revoke
            )
        chain = await self._materialize_local_chain(chain)
        return await DirectSendStrategy(self._context).send(
            event, chain, options.auto_revoke
        )

    async def _materialize_local_chain(
        self, chain: list[Comp.Image]
    ) -> list[Comp.Image]:
        """Convert readable local-file images to in-memory payloads before send."""
        materialized: list[Comp.Image] = []
        for comp in chain:
            file_path = self._local_file_path(comp)
            if file_path is None:
                materialized.append(comp)
                continue
            try:
                data = await asyncio.to_thread(file_path.read_bytes)
            except OSError as exc:
                self._log.warning(
                    "[send] failed to read image before send: path=%s, error=%s",
                    file_path,
                    exc,
                )
                materialized.append(comp)
                continue
            self._log.debug("[send] materialized local image: path=%s", file_path)
            materialized.append(Comp.Image.fromBytes(data))
        return materialized

    def _without_stream_upload(self, options: SendOptions) -> SendOptions:
        """Return options for a retry after stream upload has already run."""
        return SendOptions(
            send_mode=options.send_mode,
            use_html_card=options.use_html_card,
            auto_revoke=options.auto_revoke,
            revoke_delay=options.revoke_delay,
            r18_docx_mode=options.r18_docx_mode,
            html_padding=options.html_padding,
            html_gap=options.html_gap,
            html_card_strategy=options.html_card_strategy,
            napcat_stream_mode="disabled",
        )

    async def _send_r18_docx(
        self,
        event: AstrMessageEvent,
        images: tuple[bytes, ...],
        tags: tuple[str, ...],
        options: SendOptions,
    ) -> AsyncGenerator[Any, None]:
        """Send R18 images packaged as DOCX when a docx service is available."""
        docx_service = getattr(self, "_docx_service", None)
        if not docx_service:
            self._log.debug("[send] docx service unavailable, fallback to image send")
            return

        docx_path = docx_service.create_docx_with_images(list(images), tags=list(tags))
        if docx_path:
            if options.auto_revoke:
                message_id = await self._send_file_with_revoke(
                    event, str(docx_path), docx_path.name
                )
                if message_id:
                    await self._schedule_revoke(event, message_id, options.revoke_delay)
                    found_msg = self._format_found_message(
                        len(images), options.revoke_delay
                    )
                    if found_msg:
                        yield event.plain_result(found_msg)
                    return

            found_msg = self._format_found_message(len(images))
            if found_msg:
                yield event.plain_result(found_msg)
            yield event.chain_result(
                [Comp.File(file=str(docx_path), name=docx_path.name)]
            )
        else:
            yield event.plain_result("R18 Docx 封装失败，请稍后再试或联系管理员。")

    async def _try_html_card_fallback(
        self,
        event: AstrMessageEvent,
        chain: list[Comp.Image],
        options: SendOptions,
        is_r18: bool,
    ) -> bool:
        """Try HTML card fallback."""
        if not self._html_renderer:
            return False

        strategy = HtmlCardFallbackStrategy(
            self._context,
            self._html_renderer,
            {
                "card_padding": options.html_padding,
                "card_gap": options.html_gap,
            },
        )
        return await strategy.send(event, chain, is_r18 and options.auto_revoke)

    def _payload_items(self, payload: ImagePayload) -> tuple[ImageItem, ...]:
        if payload.items:
            return tuple(payload.items)
        items: list[ImageItem] = []
        items.extend(payload.file_paths)
        items.extend(payload.raw_bytes)
        return tuple(items)

    def _build_image_chain(self, images: tuple[ImageItem, ...]) -> list[Comp.Image]:
        """Build image components from local paths or in-memory bytes."""
        chain: list[Comp.Image] = []
        for item in images:
            if isinstance(item, Comp.Image):
                chain.append(item)
            elif isinstance(item, bytes):
                chain.append(Comp.Image.fromBytes(item))
            elif isinstance(item, Path):
                chain.append(Comp.Image.fromFileSystem(str(item)))
        return chain

    async def _read_image_bytes(
        self, images: tuple[ImageItem, ...]
    ) -> tuple[bytes, ...]:
        """Materialize image items as bytes for DOCX/HTML-only paths."""
        result: list[bytes] = []
        for item in images:
            if isinstance(item, bytes):
                result.append(item)
            elif isinstance(item, Path):
                try:
                    result.append(await asyncio.to_thread(item.read_bytes))
                except OSError as exc:
                    self._log.warning(
                        "[send] failed to read cached image: path=%s, error=%s",
                        item,
                        exc,
                    )
            elif isinstance(item, Comp.Image):
                try:
                    file_path = await item.convert_to_file_path()
                    result.append(await asyncio.to_thread(Path(file_path).read_bytes))
                except Exception as exc:
                    self._log.warning(
                        "[send] failed to read image component: file=%s, error=%s",
                        getattr(item, "file", None),
                        exc,
                    )
        return tuple(result)

    async def _stream_upload_chain(
        self, event: AstrMessageEvent, chain: list[Comp.Image]
    ) -> tuple[list[Comp.Image], bool]:
        """Upload local image files through NapCat Stream API and rebuild the chain."""
        changed = False
        streamed: list[Comp.Image] = []
        for comp in chain:
            file_path = self._local_file_path(comp)
            if file_path is None:
                streamed.append(comp)
                continue

            uploaded_path = await upload_file_stream(event, file_path)
            if uploaded_path:
                self._log.debug(
                    "[send] stream upload success: local=%s, remote=%s",
                    file_path,
                    uploaded_path,
                )
                streamed.append(self._image_from_ref(uploaded_path))
                changed = True
            else:
                self._log.warning(
                    "[send] stream upload failed, keep original image: local=%s",
                    file_path,
                )
                streamed.append(comp)
        return streamed, changed

    def _has_local_image_paths(self, chain: list[Comp.Image]) -> bool:
        return any(self._local_file_path(comp) is not None for comp in chain)

    def _local_file_path(self, comp: Comp.Image) -> Path | None:
        path_value = getattr(comp, "path", None)
        if path_value:
            path = Path(str(path_value))
            if path.exists():
                return path

        file_value = getattr(comp, "file", None)
        if not isinstance(file_value, str) or not file_value:
            return None
        if file_value.startswith("file:///"):
            path = Path(file_value[8:])
        else:
            path = Path(file_value)
        return path if path.exists() else None

    def _image_from_ref(self, ref: str | Path) -> Comp.Image:
        text = str(ref)
        if text.startswith("file:///"):
            return Comp.Image(file=text)
        path = Path(text)
        if path.exists():
            return Comp.Image.fromFileSystem(str(path))
        return Comp.Image(file=text)

    async def _send_plain_text(self, event: AstrMessageEvent, text: str) -> bool:
        """Send plain text message."""
        try:
            result = event.plain_result(text)
            await self._context.send_message(event.unified_msg_origin, result)
            return True
        except Exception as exc:
            self._log.warning("[send] failed to send plain text: error=%s", exc)
            return False

    def _is_forward_supported(self, event: AstrMessageEvent) -> bool:
        """Check if platform supports forward messages (cached per platform)."""
        platform_name = self._get_platform_name(event)
        if platform_name in self._forward_supported_cache:
            return self._forward_supported_cache[platform_name]

        supported = self._check_forward_support(platform_name, event)
        self._forward_supported_cache[platform_name or ""] = supported
        return supported

    def _get_platform_name(self, event: AstrMessageEvent) -> str | None:
        """Extract platform name from event."""
        if hasattr(event, "platform") and event.platform:
            if hasattr(event.platform, "name"):
                return event.platform.name

        if hasattr(event, "get_platform_name"):
            try:
                return event.get_platform_name()
            except Exception:
                pass

        return None

    def _check_forward_support(
        self, platform_name: str | None, event: AstrMessageEvent
    ) -> bool:
        """Check forward support from platform info."""
        if not platform_name and hasattr(event, "bot") and event.bot:
            if hasattr(event.bot, "call_action"):
                return True

        if platform_name:
            supported = (
                "aiocqhttp",
                "onebot11",
                "onebot",
                "go-cqhttp",
                "napcat",
                "llonebot",
            )
            return any(p in platform_name.lower() for p in supported)

        return False

    async def _send_with_revoke_support(
        self,
        event: AstrMessageEvent,
        chain: list[Any],
        is_group: bool,
        target_id: str,
    ) -> str | None:
        """Send message with revoke support."""
        try:
            result = event.chain_result(chain)
            send_result = await self._context.send_message(
                event.unified_msg_origin, result
            )
            if isinstance(send_result, dict):
                return send_result.get("message_id")
            if isinstance(send_result, str):
                return send_result
            return None
        except Exception as exc:
            self._log.warning("[send] revoke-capable send failed: error=%s", exc)
            return None

    async def _send_file_with_revoke(
        self, event: AstrMessageEvent, file_path: str, file_name: str
    ) -> str | None:
        """Send a file and return its message id when available."""
        return await self._send_with_revoke_support(
            event,
            [Comp.File(file=file_path, name=file_name)],
            bool(event.get_group_id()),
            event.get_group_id() or event.get_sender_id(),
        )

    async def _schedule_revoke(
        self, event: AstrMessageEvent, message_id: str, delay: int
    ) -> None:
        """Schedule message revocation."""
        try:
            scheduler = getattr(self, "_revoke_scheduler", None)
            if scheduler:
                await scheduler.schedule_revoke(event, message_id, delay)
        except AttributeError:
            self._log.debug("[send] revoke scheduler missing schedule_revoke")

    def _format_found_message(
        self, count: int, revoke_delay: int | None = None
    ) -> str | None:
        """Format found message with optional revoke delay."""
        config = self._config
        if config and hasattr(config, "format_found_message"):
            return config.format_found_message(count, revoke_delay)
        if revoke_delay and revoke_delay > 0:
            return f"找到 {count} 张图，将在 {revoke_delay} 秒后撤回"
        return f"找到 {count} 张图"

    def _send_failed_message(self) -> str:
        config = self._config
        if config and getattr(config, "msg_send_failed_text", None):
            return str(config.msg_send_failed_text)
        return "图片发送失败，请稍后再试。"

    def _log_send_summary(
        self,
        event: AstrMessageEvent,
        payload: ImagePayload,
        items: tuple[ImageItem, ...],
        options: SendOptions,
    ) -> None:
        local_paths = sum(isinstance(item, Path) for item in items)
        raw_bytes = sum(isinstance(item, bytes) for item in items)
        image_components = sum(isinstance(item, Comp.Image) for item in items)
        self._log.info(
            "[send] payload ready: session=%s, platform=%s, count=%d, r18=%s, tags=%s, items=%d(paths=%d,bytes=%d,components=%d), config_mode=%s, html_strategy=%s, napcat_stream=%s",
            self._session_label(event),
            self._get_platform_name(event) or "unknown",
            payload.count,
            payload.r18,
            ",".join(payload.tags) or "-",
            len(items),
            local_paths,
            raw_bytes,
            image_components,
            options.send_mode,
            options.html_card_strategy,
            options.napcat_stream_mode,
        )

    def _session_label(self, event: AstrMessageEvent) -> str:
        group_id = event.get_group_id()
        sender_id = event.get_sender_id()
        if group_id:
            return f"group:{group_id}/user:{sender_id}"
        return f"user:{sender_id}"
