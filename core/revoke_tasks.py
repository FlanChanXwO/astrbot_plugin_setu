"""撤回任务处理混入类。"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

import astrbot.api.message_components as Comp
from astrbot.api import logger

if TYPE_CHECKING:
    from astrbot.api.event import AstrMessageEvent

    from .revoke_manager import RevokeManager


class RevokeTaskMixin:
    """撤回任务处理混入类。"""

    _revoke_manager: RevokeManager
    _revoke_tasks: set[asyncio.Task]

    async def _delayed_revoke(
        self,
        message_id: str,
        delay: int,
        _platform: str,
        _session_id: str,
        _is_group: bool,
        bot_id: int | None,
        bot: Any | None,
    ) -> None:
        """后台任务：在 delay 秒后撤回消息。"""
        await asyncio.sleep(delay)

        success = False
        if bot and bot_id:
            try:
                params_list = [
                    {"message_id": message_id},
                    {
                        "message_id": int(message_id)
                        if str(message_id).isdigit()
                        else message_id
                    },
                ]
                for params in params_list:
                    try:
                        await bot.call_action("delete_msg", **params)
                        success = True
                        break
                    except (RuntimeError, ConnectionError, TimeoutError):
                        continue
            except (RuntimeError, ConnectionError, TimeoutError) as exc:
                logger.warning("[revoke] Background revoke failed: %s", exc)

        if success:
            await self._revoke_manager.mark_revoked(message_id)
            logger.info("[revoke] Successfully revoked message %s", message_id)
        else:
            await self._revoke_manager.mark_revoked(message_id)
            logger.warning("[revoke] Failed to revoke message %s, marked as revoked", message_id)

    async def _schedule_revoke(
        self, event: AstrMessageEvent, message_id: str | int, delay: int
    ) -> None:
        """调度消息在 delay 秒后撤回。"""
        if not message_id:
            return

        platform = event.get_platform_name()
        session_id = event.get_session_id()
        is_group = bool(event.get_group_id())
        revoke_time = int(time.time()) + delay

        bot = getattr(event, "bot", None)
        bot_id = id(bot) if bot else None

        await self._revoke_manager.add_entry(
            str(message_id), platform, session_id, is_group, revoke_time
        )

        task = asyncio.create_task(
            self._delayed_revoke(
                str(message_id), delay, platform, session_id, is_group, bot_id, bot
            )
        )
        self._revoke_tasks.add(task)
        task.add_done_callback(self._revoke_tasks.discard)

    async def _restore_pending_revokes(self) -> None:
        """恢复未处理的撤回任务（插件重启后）。"""
        try:
            pending = self._revoke_manager.get_pending_entries()
            if not pending:
                return
            logger.info("[revoke] Restoring %d pending revoke tasks", len(pending))
            now = int(time.time())
            for entry in pending:
                message_id = entry.get("message_id")
                revoke_time = entry.get("revoke_time", 0)
                if revoke_time <= now:
                    await self._revoke_manager.mark_revoked(message_id)
                    logger.debug("[revoke] Expired entry marked as revoked: %s", message_id)
                else:
                    delay = revoke_time - now
                    task = asyncio.create_task(
                        self._delayed_revoke(
                            message_id, delay,
                            entry.get("platform", ""),
                            entry.get("session_id", ""),
                            entry.get("is_group", False),
                            None, None
                        )
                    )
                    self._revoke_tasks.add(task)
                    task.add_done_callback(self._revoke_tasks.discard)
        except Exception as exc:
            logger.exception("[revoke] Failed to restore pending revokes: %s", exc)
