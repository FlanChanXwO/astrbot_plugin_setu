"""今日运势会话配置管理。

支持会话级别的独立配置，包括标签和内容模式。
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

from astrbot.api import logger


class FortuneSessionConfig:
    """今日运势会话配置管理器。"""

    # 允许会话覆盖的配置项
    ALLOWED_KEYS = {"tags", "content_mode"}

    # 有效的内容模式值
    VALID_CONTENT_MODES = {"sfw", "r18", "mix"}

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.config_file = data_dir / "fortune_session_config.json"
        self._data: dict[str, Any] = {"sessions": {}, "meta": {}}
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """初始化配置。"""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        async with self._lock:
            await self._load()
            self._data.setdefault("sessions", {})
            self._data.setdefault("meta", {"created_at": int(time.time())})
        logger.info("[fortune_session] Session config initialized")

    async def _load(self) -> None:
        """从文件加载配置。"""
        if not self.config_file.exists():
            self._data = {"sessions": {}, "meta": {"created_at": int(time.time())}}
            await self._save()
            return

        try:
            content = await asyncio.to_thread(
                self.config_file.read_text, encoding="utf-8"
            )
            loaded = json.loads(content)
            self._data = {
                "sessions": loaded.get("sessions", {}),
                "meta": loaded.get("meta", {}),
            }
        except (OSError, json.JSONDecodeError):
            logger.exception("[fortune_session] Failed to load config")
            self._data = {"sessions": {}, "meta": {"created_at": int(time.time())}}
            await self._save()

    async def _save(self) -> None:
        """保存配置到文件。"""
        try:
            tmp_path = self.config_file.with_suffix(".tmp")
            content = json.dumps(self._data, ensure_ascii=False, indent=2)
            await asyncio.to_thread(tmp_path.write_text, content, encoding="utf-8")
            await asyncio.to_thread(tmp_path.replace, self.config_file)
        except OSError:
            logger.exception("[fortune_session] Failed to save config")

    def _get_session_key(self, session_id: str, is_group: bool) -> str:
        """生成会话键。"""
        prefix = "group" if is_group else "private"
        return f"{prefix}:{session_id}"

    async def set_config(
        self, session_id: str, is_group: bool, key: str, value: Any
    ) -> bool:
        """设置会话配置项。"""
        if key not in self.ALLOWED_KEYS:
            logger.warning("[fortune_session] Key %s is not allowed", key)
            return False

        if key == "content_mode" and value not in self.VALID_CONTENT_MODES:
            logger.warning("[fortune_session] Invalid content_mode: %s", value)
            return False

        session_key = self._get_session_key(session_id, is_group)

        async with self._lock:
            if session_key not in self._data["sessions"]:
                self._data["sessions"][session_key] = {}

            self._data["sessions"][session_key][key] = value
            self._data["sessions"][session_key]["updated_at"] = int(time.time())
            await self._save()

        logger.info("[fortune_session] Set %s=%s for %s", key, value, session_key)
        return True

    async def get_config(
        self, session_id: str, is_group: bool, key: str, default: Any = None
    ) -> Any:
        """获取会话配置项。"""
        session_key = self._get_session_key(session_id, is_group)
        async with self._lock:
            session_data = self._data["sessions"].get(session_key, {})
            return session_data.get(key, default)

    async def clear_config(self, session_id: str, is_group: bool, key: str) -> bool:
        """清除会话配置项。"""
        session_key = self._get_session_key(session_id, is_group)

        async with self._lock:
            if session_key in self._data["sessions"]:
                if key in self._data["sessions"][session_key]:
                    del self._data["sessions"][session_key][key]
                    await self._save()
                    logger.info("[fortune_session] Cleared %s for %s", key, session_key)
                    return True
        return False

    async def get_session_tags(self, session_id: str, is_group: bool) -> str | None:
        """获取会话的标签配置。"""
        return await self.get_config(session_id, is_group, "tags")

    async def set_session_tags(
        self, session_id: str, is_group: bool, tags: str
    ) -> bool:
        """设置会话的标签配置。"""
        return await self.set_config(session_id, is_group, "tags", tags)

    async def clear_session_tags(self, session_id: str, is_group: bool) -> bool:
        """清除会话的标签配置。"""
        return await self.clear_config(session_id, is_group, "tags")

    async def get_session_content_mode(self, session_id: str, is_group: bool) -> str | None:
        """获取会话的内容模式配置。"""
        return await self.get_config(session_id, is_group, "content_mode")

    async def set_session_content_mode(
        self, session_id: str, is_group: bool, mode: str
    ) -> bool:
        """设置会话的内容模式配置。"""
        return await self.set_config(session_id, is_group, "content_mode", mode)

    async def clear_session_content_mode(self, session_id: str, is_group: bool) -> bool:
        """清除会话的内容模式配置。"""
        return await self.clear_config(session_id, is_group, "content_mode")

    async def get_effective_tags(
        self, session_id: str, is_group: bool, global_tags: str
    ) -> str:
        """获取生效的标签（优先会话配置）。"""
        session_tags = await self.get_session_tags(session_id, is_group)
        if session_tags is not None:
            return session_tags
        return global_tags

    async def get_effective_content_mode(
        self, session_id: str, is_group: bool, global_mode: str
    ) -> str:
        """获取生效的内容模式（优先会话配置）。"""
        session_mode = await self.get_session_content_mode(session_id, is_group)
        if session_mode:
            return session_mode
        return global_mode
