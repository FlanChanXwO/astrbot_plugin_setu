"""图片缓存服务。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from pathlib import Path
from typing import Any

from astrbot.api import logger


class UrlImageDiskCache:
    """基于 URL 的简单图片磁盘缓存，支持 TTL 和数量限制。"""

    def __init__(
        self, cache_dir: Path, ttl_hours: int, max_items: int, enabled: bool = True
    ):
        self.enabled = enabled
        self.cache_dir = cache_dir
        self.index_path = cache_dir / "image_cache_index.json"
        self.ttl_seconds = max(1, int(ttl_hours) * 3600)
        self.max_items = max(1, int(max_items))
        self._index: dict[str, dict[str, Any]] = {"entries": {}, "meta": {}}
        self._lock = asyncio.Lock()

    async def initialize(self, cleanup_on_start: bool = True) -> None:
        """初始化缓存。"""
        if not self.enabled:
            logger.info("[setu.cache] cache disabled")
            return
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            await self._load_index()
            if cleanup_on_start:
                removed = await self.cleanup_expired()
                logger.info("[setu.cache] startup cleanup removed=%d", removed)
            # 检查并清理孤立缓存文件（索引中不存在的 .bin 文件）
            await self._cleanup_orphaned_files()
        except (OSError, json.JSONDecodeError) as exc:
            logger.exception("[setu.cache] initialize failed: %s", exc)

    async def _cleanup_orphaned_files(self) -> int:
        """清理孤立缓存文件（索引中不存在的 .bin 文件）。"""
        removed = 0
        try:
            async with self._lock:
                # 获取索引中记录的文件路径
                indexed_paths = {
                    entry.get("path", "")
                    for entry in self._index.get("entries", {}).values()
                }

                for file_path in self.cache_dir.iterdir():
                    if not file_path.is_file():
                        continue
                    # 处理旧的 .img 文件（迁移到 .bin）
                    if file_path.suffix == ".img":
                        try:
                            # 尝试迁移：读取旧文件，创建新文件，删除旧文件
                            new_path = file_path.with_suffix(".bin")
                            if not new_path.exists():
                                data = file_path.read_bytes()
                                new_path.write_bytes(data)
                                # 更新索引中对应的路径
                                for entry in self._index.get("entries", {}).values():
                                    if entry.get("path") == str(file_path):
                                        entry["path"] = str(new_path)
                                        break
                            file_path.unlink()
                            removed += 1
                            logger.debug("[setu.cache] migrated .img to .bin: %s", file_path.name)
                        except OSError as exc:
                            logger.warning("[setu.cache] failed to migrate .img file: %s", exc)
                        continue
                    # 只处理 .bin 文件（新的扩展名）
                    if file_path.suffix == ".bin":
                        str_path = str(file_path)
                        if str_path not in indexed_paths:
                            try:
                                file_path.unlink()
                                removed += 1
                                logger.debug("[setu.cache] removed orphaned file: %s", file_path.name)
                            except OSError:
                                pass
                # 如果有迁移，保存索引
                if removed > 0:
                    await self._save_index_locked()
        except OSError as exc:
            logger.warning("[setu.cache] failed to cleanup orphaned files: %s", exc)

        if removed > 0:
            logger.info("[setu.cache] cleaned up %d orphaned/migrated cache files", removed)
        return removed

    async def get(self, url: str) -> bytes | None:
        """获取缓存图片。"""
        if not self.enabled:
            return None
        key = self._url_key(url)
        async with self._lock:
            entry = self._index.get("entries", {}).get(key)
            if not entry:
                return None

            now = int(time.time())
            expires_at = int(entry.get("expires_at", 0))
            cached_path = Path(entry.get("path", ""))
            if expires_at <= now or not cached_path.is_file():
                self._remove_entry_locked(key, delete_file=True)
                await self._save_index_locked()
                return None

            try:
                data = cached_path.read_bytes()
            except OSError as exc:
                logger.exception(
                    "[setu.cache] failed to read cache file key=%s: %s", key, exc
                )
                self._remove_entry_locked(key, delete_file=True)
                await self._save_index_locked()
                return None

            entry["last_hit"] = now
            await self._save_index_locked()
            logger.debug("[setu.cache] hit key=%s path=%s", key, cached_path)
            return data

    async def put(self, url: str, data: bytes) -> None:
        """写入图片到缓存。"""
        if not self.enabled or not data:
            return
        key = self._url_key(url)
        now = int(time.time())
        expires_at = now + self.ttl_seconds
        file_path = self.cache_dir / f"{key}.bin"

        async with self._lock:
            try:
                file_path.write_bytes(data)
            except OSError as exc:
                logger.exception(
                    "[setu.cache] failed to write cache file=%s: %s", file_path, exc
                )
                return

            entries = self._index.setdefault("entries", {})
            entries[key] = {
                "url": url,
                "path": str(file_path),
                "created_at": now,
                "expires_at": expires_at,
                "last_hit": now,
                "size": len(data),
            }
            removed = self._prune_locked(now)
            self._index.setdefault("meta", {})["last_prune_removed"] = removed
            self._index["meta"]["last_update_at"] = now
            await self._save_index_locked()
            logger.debug(
                "[setu.cache] put key=%s size=%d removed=%d", key, len(data), removed
            )

    async def cleanup_expired(self) -> int:
        """清理过期缓存。"""
        if not self.enabled:
            return 0
        now = int(time.time())
        async with self._lock:
            removed = self._prune_locked(now)
            self._index.setdefault("meta", {})["last_cleanup_at"] = now
            self._index["meta"]["last_cleanup_removed"] = removed
            await self._save_index_locked()
            return removed

    async def _load_index(self) -> None:
        """加载缓存索引文件。"""
        if not self.index_path.is_file():
            self._index = {"entries": {}, "meta": {}}
            await self._save_index_locked()
            return
        try:
            raw = self.index_path.read_text(encoding="utf-8")
            loaded = json.loads(raw)
            entries = loaded.get("entries", {}) if isinstance(loaded, dict) else {}
            meta = loaded.get("meta", {}) if isinstance(loaded, dict) else {}
            self._index = {
                "entries": entries if isinstance(entries, dict) else {},
                "meta": meta if isinstance(meta, dict) else {},
            }
        except Exception as exc:
            logger.exception("[setu.cache] index parse failed, reset index: %s", exc)
            self._index = {"entries": {}, "meta": {}}
            await self._save_index_locked()

    async def _save_index_locked(self) -> None:
        """保存缓存索引（加锁）。"""
        tmp_path = self.index_path.with_suffix(".json.tmp")
        try:
            # 确保目录存在
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            tmp_path.write_text(
                json.dumps(self._index, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp_path.replace(self.index_path)
        except Exception as exc:
            logger.exception(
                "[setu.cache] failed to save index %s: %s", self.index_path, exc
            )
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except Exception as exc2:
                logger.debug("[setu.cache] failed to remove temp index file: %s", exc2)

    def _prune_locked(self, now: int) -> int:
        """清理过期和超出数量限制的缓存项。"""
        entries = self._index.setdefault("entries", {})
        removed = 0

        expired_keys = [
            k for k, v in entries.items() if int(v.get("expires_at", 0)) <= now
        ]
        for key in expired_keys:
            self._remove_entry_locked(key, delete_file=True)
            removed += 1

        if len(entries) > self.max_items:
            sorted_items = sorted(
                entries.items(),
                key=lambda item: int(
                    item[1].get("last_hit", item[1].get("created_at", 0))
                ),
            )
            overflow = len(entries) - self.max_items
            for key, _ in sorted_items[:overflow]:
                self._remove_entry_locked(key, delete_file=True)
                removed += 1
        return removed

    def _remove_entry_locked(self, key: str, delete_file: bool) -> None:
        """移除缓存项。"""
        entries = self._index.setdefault("entries", {})
        entry = entries.pop(key, None)
        if not entry or not delete_file:
            return
        cached_path = Path(entry.get("path", ""))
        try:
            if cached_path.is_file():
                cached_path.unlink()
        except Exception as exc:
            logger.warning(
                "[setu.cache] failed to remove cache file path=%s: %s", cached_path, exc
            )

    @staticmethod
    def _url_key(url: str) -> str:
        """生成 URL 的哈希 key。"""
        return hashlib.sha256(url.encode("utf-8", errors="ignore")).hexdigest()
