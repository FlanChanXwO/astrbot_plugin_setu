"""撤回管理器模块。"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

from astrbot.api import logger


class RevokeManager:
    """管理 revoke.json，用于追踪被撤回的 R18 消息。"""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.revoke_file = data_dir / "revoke.json"
        self._lock = asyncio.Lock()
        self._data: dict[str, Any] = {"entries": {}, "meta": {}}

    async def initialize(self) -> None:
        """初始化 revoke.json 文件。"""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        await self._load()

    async def _load(self) -> None:
        """从文件加载撤回数据。"""
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
        except (json.JSONDecodeError, OSError):
            logger.exception("Failed to load revoke.json")
            self._data = {"entries": {}, "meta": {"created_at": int(time.time())}}
            await self._save()

    async def _save(self) -> None:
        """保存撤回数据到文件。"""
        try:
            self.revoke_file.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            logger.exception("Failed to save revoke.json")

    async def add_entry(
        self,
        message_id: str,
        platform: str,
        session_id: str,
        is_group: bool,
        revoke_time: int,
    ) -> None:
        """添加撤回条目。"""
        async with self._lock:
            self._data["entries"][message_id] = {
                "platform": platform,
                "session_id": session_id,
                "is_group": is_group,
                "revoke_time": revoke_time,
                "revoked": False,
                "created_at": int(time.time()),
            }
            await self._save()

    async def mark_revoked(self, message_id: str) -> None:
        """标记消息为已撤回，并清理旧记录。"""
        async with self._lock:
            if message_id in self._data["entries"]:
                self._data["entries"][message_id]["revoked"] = True
                self._data["entries"][message_id]["revoked_at"] = int(time.time())
                # 清理已撤销的过期记录（保留最近7天的）
                await self._cleanup_revoked_entries()
                await self._save()

    async def _cleanup_revoked_entries(self, max_age_days: int = 7) -> int:
        """清理已撤销的旧记录。

        参数:
            max_age_days: 已撤销记录保留天数

        返回:
            清理的记录数量
        """
        cutoff = int(time.time()) - (max_age_days * 24 * 3600)
        to_remove = []

        for message_id, entry in self._data["entries"].items():
            # 只清理已撤销的过期记录
            if entry.get("revoked", False):
                revoked_at = entry.get("revoked_at", entry.get("created_at", 0))
                if revoked_at < cutoff:
                    to_remove.append(message_id)

        for message_id in to_remove:
            del self._data["entries"][message_id]

        if to_remove:
            logger.debug("[revoke] Cleaned up %d old revoked entries", len(to_remove))

        return len(to_remove)

    def get_pending_entries(self) -> list[dict[str, Any]]:
        """获取待撤回的条目列表。"""
        entries = []
        for message_id, entry in self._data["entries"].items():
            if not entry.get("revoked", False):
                entry["message_id"] = message_id
                entries.append(entry)
        return entries
