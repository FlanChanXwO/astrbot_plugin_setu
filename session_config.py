"""会话级别配置管理器。

提供会话级别的配置覆盖功能，允许管理员在特定会话中设置不同的内容模式。
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

import aiofiles

from astrbot.api import logger


class SessionConfigManager:
    """会话级别配置管理器。

    管理每个会话（群聊/私聊）的独立配置，支持内容模式覆盖。
    配置持久化存储在 plugin_data_dir/session_config.json 中。

    Attributes:
        config_file: 配置文件路径
        _data: 配置数据字典
        _lock: 异步锁，防止并发写入冲突
    """

    # 允许会话覆盖的配置项
    ALLOWED_KEYS = {"content_mode"}

    # 有效的内容模式值
    VALID_CONTENT_MODES = {"sfw", "r18", "mix"}

    def __init__(self, data_dir: Path):
        """初始化会话配置管理器。

        参数:
            data_dir: 插件数据目录
        """
        self.data_dir = data_dir
        self.config_file = data_dir / "session_config.json"
        self._data: dict[str, Any] = {"sessions": {}, "meta": {}}
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """初始化配置，从文件加载现有配置。"""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        async with self._lock:
            await self._load()
            self._data.setdefault("sessions", {})
            self._data.setdefault("meta", {"created_at": int(time.time())})
        logger.info("[session_config] SessionConfigManager initialized")

    async def _load(self) -> None:
        """从文件加载配置（调用方应确保锁保护）。"""
        if not self.config_file.exists():
            self._data = {"sessions": {}, "meta": {"created_at": int(time.time())}}
            await self._save()
            return

        try:
            async with aiofiles.open(self.config_file, encoding="utf-8") as f:
                content = await f.read()
                loaded = json.loads(content)
                self._data = {
                    "sessions": loaded.get("sessions", {}),
                    "meta": loaded.get("meta", {}),
                }
        except (OSError, json.JSONDecodeError):
            logger.exception(
                "[session_config] Failed to load session config, creating new"
            )
            self._data = {"sessions": {}, "meta": {"created_at": int(time.time())}}
            await self._save()

    async def _save(self) -> None:
        """保存配置到文件（应在锁保护下调用）。"""
        try:
            tmp_path = self.config_file.with_suffix(".tmp")
            async with aiofiles.open(tmp_path, "w", encoding="utf-8") as f:
                await f.write(json.dumps(self._data, ensure_ascii=False, indent=2))
            tmp_path.replace(self.config_file)
        except OSError:
            logger.exception("[session_config] Failed to save session config")

    def _get_session_key(self, session_id: str, is_group: bool) -> str:
        """生成会话键。

        参数:
            session_id: 会话ID
            is_group: 是否为群聊

        返回:
            格式化的会话键，如 "group:12345" 或 "private:67890"
        """
        prefix = "group" if is_group else "private"
        return f"{prefix}:{session_id}"

    async def set_config(
        self, session_id: str, is_group: bool, key: str, value: Any
    ) -> bool:
        """设置会话配置项。

        参数:
            session_id: 会话ID
            is_group: 是否为群聊
            key: 配置键
            value: 配置值

        返回:
            设置成功返回 True，否则返回 False
        """
        if key not in self.ALLOWED_KEYS:
            logger.warning("[session_config] Key %s is not allowed", key)
            return False

        # 验证 content_mode 值
        if key == "content_mode" and value not in self.VALID_CONTENT_MODES:
            logger.warning("[session_config] Invalid content_mode: %s", value)
            return False

        session_key = self._get_session_key(session_id, is_group)

        # 使用锁保护并发写入
        async with self._lock:
            if session_key not in self._data["sessions"]:
                self._data["sessions"][session_key] = {}

            self._data["sessions"][session_key][key] = value
            self._data["sessions"][session_key]["updated_at"] = int(time.time())
            await self._save()

        logger.info(
            "[session_config] Set %s=%s for session %s", key, value, session_key
        )
        return True

    async def get_config(
        self, session_id: str, is_group: bool, key: str, default: Any = None
    ) -> Any:
        """获取会话配置项。

        参数:
            session_id: 会话ID
            is_group: 是否为群聊
            key: 配置键
            default: 默认值

        返回:
            配置值，如果不存在则返回默认值
        """
        session_key = self._get_session_key(session_id, is_group)
        # 使用锁保护读操作，防止并发可见性问题
        async with self._lock:
            session_data = self._data["sessions"].get(session_key, {})
            return session_data.get(key, default)

    async def clear_config(self, session_id: str, is_group: bool, key: str) -> bool:
        """清除会话配置项。

        参数:
            session_id: 会话ID
            is_group: 是否为群聊
            key: 配置键

        返回:
            清除成功返回 True，否则返回 False
        """
        session_key = self._get_session_key(session_id, is_group)

        # 使用锁保护并发写入
        async with self._lock:
            if session_key in self._data["sessions"]:
                if key in self._data["sessions"][session_key]:
                    del self._data["sessions"][session_key][key]
                    await self._save()
                    logger.info(
                        "[session_config] Cleared %s for session %s", key, session_key
                    )
                    return True
        return False

    async def get_session_content_mode(
        self, session_id: str, is_group: bool
    ) -> str | None:
        """获取会话的内容模式。

        参数:
            session_id: 会话ID
            is_group: 是否为群聊

        返回:
            内容模式 (sfw/r18/mix)，如果未设置则返回 None
        """
        return await self.get_config(session_id, is_group, "content_mode")

    async def set_session_content_mode(
        self, session_id: str, is_group: bool, mode: str
    ) -> bool:
        """设置会话的内容模式。

        参数:
            session_id: 会话ID
            is_group: 是否为群聊
            mode: 内容模式 (sfw/r18/mix)

        返回:
            设置成功返回 True，否则返回 False
        """
        return await self.set_config(session_id, is_group, "content_mode", mode)

    async def clear_session_content_mode(self, session_id: str, is_group: bool) -> bool:
        """清除会话的内容模式设置。

        参数:
            session_id: 会话ID
            is_group: 是否为群聊

        返回:
            清除成功返回 True，否则返回 False
        """
        return await self.clear_config(session_id, is_group, "content_mode")

    async def cleanup_expired_sessions(self, max_age_days: int = 30) -> int:
        """清理超过指定天数的过期会话配置。

        参数:
            max_age_days: 最大保留天数

        返回:
            清理的会话数量
        """
        cutoff = int(time.time()) - (max_age_days * 24 * 3600)
        to_remove = []

        # 使用锁保护并发读写
        async with self._lock:
            for session_key, session_data in self._data["sessions"].items():
                updated_at = session_data.get("updated_at", 0)
                if updated_at < cutoff:
                    to_remove.append(session_key)

            for session_key in to_remove:
                del self._data["sessions"][session_key]

            if to_remove:
                await self._save()

        if to_remove:
            logger.info(
                "[session_config] Cleaned up %d expired sessions", len(to_remove)
            )

        return len(to_remove)
