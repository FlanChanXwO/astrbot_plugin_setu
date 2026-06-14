"""Delayed OneBot message revocation for Setu sends."""

from __future__ import annotations

import asyncio
import inspect
from typing import Any
from unittest.mock import Mock

from astrbot.api.event import AstrMessageEvent

from ...shared import get_logger
from .platform_capabilities import is_onebot_like_platform

logger = get_logger()


class RevokeScheduler:
    """Track delayed delete_msg tasks so plugin shutdown can cancel them."""

    def __init__(self) -> None:
        self._tasks: set[asyncio.Task[None]] = set()

    async def schedule_revoke(
        self,
        event: AstrMessageEvent,
        message_id: str,
        delay: int,
    ) -> bool:
        """Schedule one message revoke task and return whether it was accepted."""
        normalized_id = str(message_id or "").strip()
        if not normalized_id:
            logger.warning("[revoke] skip scheduling: empty message_id")
            return False

        platform_name = _platform_name(event)
        if not is_onebot_like_platform(platform_name):
            logger.warning(
                "[revoke] skip scheduling: platform=%s is not OneBot-like, message_id=%s",
                platform_name or "unknown",
                normalized_id,
            )
            return False

        bot_client = _get_bot_client(event)
        if bot_client is None or not _supports_delete_msg(bot_client):
            logger.warning(
                "[revoke] skip scheduling: delete_msg unsupported, platform=%s, message_id=%s",
                platform_name or "unknown",
                normalized_id,
            )
            return False

        task = asyncio.create_task(
            self._delete_after_delay(bot_client, platform_name, normalized_id, delay),
            name=f"setu_revoke_{normalized_id}",
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        logger.info(
            "[revoke] scheduled: platform=%s, message_id=%s, delay=%ss",
            platform_name or "unknown",
            normalized_id,
            delay,
        )
        return True

    async def cancel_all(self) -> None:
        """Cancel every pending revoke task."""
        if not self._tasks:
            return
        tasks = tuple(self._tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()

    async def _delete_after_delay(
        self,
        bot_client: Any,
        platform_name: str | None,
        message_id: str,
        delay: int,
    ) -> None:
        try:
            await asyncio.sleep(max(0, int(delay)))
            await _call_delete_msg(bot_client, message_id)
            logger.info(
                "[revoke] deleted: platform=%s, message_id=%s",
                platform_name or "unknown",
                message_id,
            )
        except asyncio.CancelledError:
            logger.debug("[revoke] cancelled: message_id=%s", message_id)
            raise
        except Exception as exc:
            logger.warning(
                "[revoke] delete_msg failed: platform=%s, message_id=%s, error=%s",
                platform_name or "unknown",
                message_id,
                exc,
            )


_scheduler: RevokeScheduler | None = None


def get_revoke_scheduler() -> RevokeScheduler:
    """Return the process-local Setu revoke scheduler."""
    global _scheduler
    if _scheduler is None:
        _scheduler = RevokeScheduler()
    return _scheduler


async def schedule_revoke(
    event: AstrMessageEvent,
    message_id: str,
    delay: int,
) -> bool:
    """Schedule one message revoke through the shared scheduler."""
    return await get_revoke_scheduler().schedule_revoke(event, message_id, delay)


async def clear_revoke_scheduler() -> None:
    """Cancel and drop pending revoke tasks."""
    global _scheduler
    if _scheduler is None:
        return
    await _scheduler.cancel_all()
    _scheduler = None


def _platform_name(event: AstrMessageEvent) -> str | None:
    platform = getattr(event, "platform", None)
    name = getattr(platform, "name", None)
    if name:
        return str(name)
    getter = getattr(event, "get_platform_name", None)
    if callable(getter):
        try:
            return str(getter())
        except Exception:
            return None
    return None


def _get_bot_client(event: AstrMessageEvent) -> Any | None:
    return getattr(event, "bot", None) or getattr(event, "_bot", None)


def _supports_delete_msg(bot_client: Any) -> bool:
    return (
        _callable_attr(bot_client, "delete_msg") is not None
        or _callable_attr(getattr(bot_client, "api", None), "call_action") is not None
        or _callable_attr(bot_client, "call_action") is not None
    )


async def _call_delete_msg(bot_client: Any, message_id: str) -> Any:
    method = _callable_attr(bot_client, "delete_msg")
    if method is not None:
        return await _maybe_await(method(message_id=message_id))
    call_action = _callable_attr(getattr(bot_client, "api", None), "call_action")
    if call_action is not None:
        return await _maybe_await(call_action("delete_msg", message_id=message_id))
    call_action = _callable_attr(bot_client, "call_action")
    if call_action is not None:
        return await _maybe_await(call_action("delete_msg", message_id=message_id))
    raise RuntimeError("delete_msg unsupported")


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _callable_attr(obj: Any, name: str) -> Any | None:
    if obj is None:
        return None
    if isinstance(obj, Mock) and name not in vars(obj):
        return None
    attr = getattr(obj, name, None)
    return attr if callable(attr) else None
