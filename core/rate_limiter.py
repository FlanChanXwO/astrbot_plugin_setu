"""请求限流管理器 - 实现会话级用户并发控制。"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from astrbot.api import logger

if TYPE_CHECKING:
    from astrbot.api.event import AstrMessageEvent


class SessionRequestLimiter:
    """会话级请求限流器。

    确保每个用户在每个会话中同时只能有一个正在处理的请求。
    使用字典跟踪正在处理的请求，键格式为: "{session_id}:{user_id}"。

    Attributes:
        _locks: 存储每个用户的请求锁
        _global_lock: 用于保护 _locks 字典的锁
    """

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

    @staticmethod
    def _get_key(session_id: str, user_id: str) -> str:
        """生成唯一的请求键。"""
        return f"{session_id}:{user_id}"

    async def acquire(self, event: AstrMessageEvent) -> bool:
        """尝试获取请求锁。

        参数:
            event: 消息事件对象

        返回:
            如果成功获取锁返回 True，如果用户已有请求在处理返回 False
        """
        session_id = event.get_session_id()
        user_id = event.get_sender_id()
        key = self._get_key(session_id, user_id)

        async with self._global_lock:
            if key in self._locks:
                # 用户已有请求在处理中
                logger.debug(
                    "[rate_limit] Request rejected for user %s in session %s: "
                    "already has a pending request",
                    user_id,
                    session_id,
                )
                return False

            # 创建新锁并获取
            self._locks[key] = asyncio.Lock()

        # 在全局锁外获取用户锁，避免长时间持有全局锁
        await self._locks[key].acquire()
        logger.debug(
            "[rate_limit] Request acquired for user %s in session %s",
            user_id,
            session_id,
        )
        return True

    async def release(self, event: AstrMessageEvent) -> None:
        """释放请求锁。

        参数:
            event: 消息事件对象
        """
        session_id = event.get_session_id()
        user_id = event.get_sender_id()
        key = self._get_key(session_id, user_id)

        async with self._global_lock:
            if key in self._locks:
                try:
                    self._locks[key].release()
                except RuntimeError:
                    # 锁可能已被释放
                    pass
                del self._locks[key]
                logger.debug(
                    "[rate_limit] Request released for user %s in session %s",
                    user_id,
                    session_id,
                )

    async def is_pending(self, event: AstrMessageEvent) -> bool:
        """检查用户是否有请求在处理中。

        参数:
            event: 消息事件对象

        返回:
            如果有请求在处理中返回 True
        """
        session_id = event.get_session_id()
        user_id = event.get_sender_id()
        key = self._get_key(session_id, user_id)

        async with self._global_lock:
            return key in self._locks

    def get_pending_count(self) -> int:
        """获取当前正在处理的请求数量。"""
        return len(self._locks)
