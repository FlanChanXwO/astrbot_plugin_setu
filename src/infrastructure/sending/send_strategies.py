"""Send strategy pattern for image delivery.

Defines the strategy interface and implementations for different send modes:
- Direct send: send images directly in message chain
- Forward send: use merge forward (OneBot v11 feature)
- HTML card fallback: wrap images in HTML cards to bypass censorship
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import astrbot.api.message_components as Comp
from astrbot.api.event import AstrMessageEvent

from ...shared import get_logger

logger = get_logger()


class SendStrategy(ABC):
    """Abstract base class for send strategies."""

    @abstractmethod
    async def send(
        self,
        event: AstrMessageEvent,
        chain: list[Any],
        auto_revoke: bool = False,
    ) -> bool:
        """Send message chain using this strategy.

        Args:
            event: Message event
            chain: Message chain (list of components)
            auto_revoke: Whether to schedule auto-revoke after send

        Returns:
            True if send succeeded, False otherwise
        """
        ...


class DirectSendStrategy(SendStrategy):
    """Direct send strategy — sends images in a single message chain."""

    def __init__(self, plugin_context: Any) -> None:
        """Initialize direct send strategy.

        Args:
            plugin_context: Plugin context for sending messages
        """
        self._context = plugin_context

    async def send(
        self,
        event: AstrMessageEvent,
        chain: list[Any],
        auto_revoke: bool = False,
    ) -> bool:
        """Send images directly in message chain.

        Args:
            event: Message event
            chain: Message chain
            auto_revoke: Not supported for direct send (ignored)

        Returns:
            True if send succeeded
        """
        try:
            send_result = await self._send_message(event, chain)

            platform_name = getattr(event.platform, "name", "unknown")

            # Only strict-check return value for OneBot platforms
            if send_result is None and platform_name == "aiocqhttp":
                logger.warning(
                    "[send] direct send returned None: platform=%s, chain=%d",
                    platform_name,
                    len(chain),
                )
                return False

            logger.info(
                "[send] direct send completed: platform=%s, chain=%d",
                platform_name,
                len(chain),
            )
            return True
        except TimeoutError:
            logger.warning(
                "[send] direct send timed out: platform=%s, chain=%d",
                getattr(event.platform, "name", "unknown"),
                len(chain),
            )
            return False
        except Exception as exc:
            logger.exception(
                "[send] direct send failed: platform=%s, chain=%d, error=%s",
                getattr(event.platform, "name", "unknown"),
                len(chain),
                exc,
            )
            return False

    async def _send_message(self, event: AstrMessageEvent, chain: list[Any]) -> Any:
        if self._requires_onebot_passthrough(event, chain):
            send_result = await self._send_onebot_image_chain(event, chain)
            if send_result is not None:
                return send_result
        result = event.chain_result(chain)
        return await self._context.send_message(event.unified_msg_origin, result)

    def _requires_onebot_passthrough(
        self, event: AstrMessageEvent, chain: list[Any]
    ) -> bool:
        platform_name = getattr(getattr(event, "platform", None), "name", "") or ""
        return "aiocqhttp" in platform_name.lower() and any(
            self._is_onebot_image_ref(comp)
            for comp in chain
            if isinstance(comp, Comp.Image)
        )

    def _is_onebot_image_ref(self, comp: Comp.Image) -> bool:
        file_value = getattr(comp, "file", None)
        return (
            isinstance(file_value, str)
            and "://" in file_value
            and not (
                file_value.startswith("file:///")
                or file_value.startswith("http://")
                or file_value.startswith("https://")
                or file_value.startswith("base64://")
            )
        )

    async def _send_onebot_image_chain(
        self, event: AstrMessageEvent, chain: list[Any]
    ) -> Any | None:
        bot = getattr(event, "bot", None)
        if bot is None:
            return None

        message: list[dict[str, Any]] = []
        for comp in chain:
            if isinstance(comp, Comp.Image):
                message.append(
                    {
                        "type": "image",
                        "data": {"file": str(getattr(comp, "file", ""))},
                    }
                )
            else:
                message.append(comp.toDict())

        is_group = bool(event.get_group_id())
        session_id = event.get_group_id() if is_group else event.get_sender_id()
        if not session_id or not str(session_id).isdigit():
            logger.debug(
                "[send] skip OneBot passthrough: invalid session_id=%s",
                session_id,
            )
            return None

        if is_group:
            return await bot.send_group_msg(group_id=int(session_id), message=message)
        return await bot.send_private_msg(user_id=int(session_id), message=message)


class ForwardSendStrategy(SendStrategy):
    """Forward send strategy — uses merge forward (OneBot v11)."""

    def __init__(self, plugin_context: Any) -> None:
        """Initialize forward send strategy.

        Args:
            plugin_context: Plugin context for sending messages
        """
        self._context = plugin_context

    async def send(
        self,
        event: AstrMessageEvent,
        chain: list[Any],
        auto_revoke: bool = False,
    ) -> bool:
        """Send images using merge forward.

        Args:
            event: Message event
            chain: Message chain (list of image components)
            auto_revoke: Not supported (handled by caller)

        Returns:
            True if send succeeded
        """
        import time

        build_start = time.monotonic()
        nodes = []
        for comp in chain:
            if isinstance(comp, Comp.Image):
                node = Comp.Node(
                    uin=event.get_self_id(),
                    name="色图",
                    content=[comp],
                )
                nodes.append(node)

        build_end = time.monotonic()
        logger.debug(
            "[forward] built nodes: count=%d, elapsed=%.3fs",
            len(nodes),
            build_end - build_start,
        )

        return await self._send_nodes_direct(event, nodes)

    async def _send_nodes_direct(
        self, event: AstrMessageEvent, nodes: list[Comp.Node]
    ) -> bool:
        """Send forward nodes directly.

        Args:
            event: Message event
            nodes: Forward nodes

        Returns:
            True if send succeeded
        """
        try:
            forward_chain = [Comp.Forward(node) for node in nodes]
            result = event.chain_result(forward_chain)
            await self._context.send_message(event.unified_msg_origin, result)

            logger.info("[forward] send completed: nodes=%d", len(nodes))
            return True
        except Exception as exc:
            logger.exception(
                "[forward] send failed: nodes=%d, error=%s",
                len(nodes),
                exc,
            )
            return False


class HtmlCardFallbackStrategy(SendStrategy):
    """HTML card fallback strategy — wraps images in HTML cards."""

    def __init__(
        self,
        plugin_context: Any,
        html_renderer: Any,
        style_options: dict[str, int] | None = None,
    ) -> None:
        """Initialize HTML card fallback strategy.

        Args:
            plugin_context: Plugin context
            html_renderer: HtmlCardRenderer instance
            style_options: Style options (card_padding, card_gap)
        """
        self._context = plugin_context
        self._renderer = html_renderer
        self._style_options = style_options or {}

    async def send(
        self,
        event: AstrMessageEvent,
        chain: list[Any],
        auto_revoke: bool = False,
    ) -> bool:
        """Send images wrapped in HTML cards.

        Args:
            event: Message event
            chain: Message chain (list of image components)
            auto_revoke: Not supported (ignored)

        Returns:
            True if send succeeded
        """
        if not self._renderer:
            logger.warning("[html_fallback] renderer unavailable")
            return False

        images: list[bytes] = []
        for comp in chain:
            if not isinstance(comp, Comp.Image):
                continue
            if isinstance(comp.file, bytes):
                images.append(comp.file)
                continue

            path_value = getattr(comp, "path", None) or getattr(comp, "file", None)
            if isinstance(path_value, str):
                candidate = (
                    Path(path_value[8:])
                    if path_value.startswith("file:///")
                    else Path(path_value)
                )
                if candidate.exists():
                    try:
                        import asyncio

                        data = await asyncio.to_thread(candidate.read_bytes)
                        images.append(data)
                    except OSError:
                        logger.warning(
                            "[html_fallback] failed to read image path=%s",
                            candidate,
                        )

        if not images:
            logger.warning("[html_fallback] no images available after materialization")
            return False

        rendered_images = []
        for i, img_data in enumerate(images):
            logger.debug("[html_fallback] Rendering image %d/%d", i + 1, len(images))
            rendered = await self._renderer.render_single_image(
                context=self._context,
                image=img_data,
                style_options=self._style_options,
            )
            if rendered:
                rendered_images.append(rendered)
            else:
                logger.warning("[html_fallback] failed to render image index=%d", i + 1)

        if not rendered_images:
            logger.warning("[html_fallback] renderer produced no images")
            return False

        # Send rendered images
        chain = [Comp.Image.fromBytes(img) for img in rendered_images]
        logger.info("[html_fallback] rendered images: count=%d", len(rendered_images))
        return await DirectSendStrategy(self._context).send(event, chain, False)


def resolve_send_mode(
    send_mode: str,
    image_count: int,
    supports_forward: bool = True,
) -> str:
    """Resolve effective send mode.

    Args:
        send_mode: Configured send mode (image/forward/auto)
        image_count: Number of images to send
        supports_forward: Whether platform supports forward

    Returns:
        Effective send mode (image or forward)
    """
    if send_mode == "auto":
        return "forward" if image_count > 1 else "image"
    if send_mode == "forward" and not supports_forward:
        return "image"
    return send_mode
