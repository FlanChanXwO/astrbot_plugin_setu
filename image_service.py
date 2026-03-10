"""Setu 插件图片下载/发送服务，支持基于 URL 的磁盘缓存。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from pathlib import Path
from typing import Any

import aiohttp

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.api.message_components import Image, Node, Nodes, Plain

from .constants import HTTP_TIMEOUT_SECONDS

# Image download headers.
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0"
    ),
    "Referer": "https://www.pixiv.net/",
}


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
        # 如果未启用缓存，直接返回
        if not self.enabled:
            logger.info("[setu.cache] cache disabled")
            return
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            await self._load_index()
            if cleanup_on_start:
                removed = await self.cleanup_expired()
                logger.info("[setu.cache] startup cleanup removed=%d", removed)
        except (OSError, json.JSONDecodeError) as exc:
            logger.exception("[setu.cache] initialize failed: %s", exc)

    async def get(self, url: str) -> bytes | None:
        # 获取缓存图片，如果不存在或已过期则返回 None
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
                logger.exception("[setu.cache] failed to read cache file key=%s: %s", key, exc)
                self._remove_entry_locked(key, delete_file=True)
                await self._save_index_locked()
                return None

            entry["last_hit"] = now
            await self._save_index_locked()
            logger.debug("[setu.cache] hit key=%s path=%s", key, cached_path)
            return data

    async def put(self, url: str, data: bytes) -> None:
        # 写入图片到缓存
        if not self.enabled or not data:
            return
        key = self._url_key(url)
        now = int(time.time())
        expires_at = now + self.ttl_seconds
        file_path = self.cache_dir / f"{key}.img"
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
        # 清理过期缓存
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
        # 加载缓存索引文件
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
        # 保存缓存索引（加锁）
        tmp_path = self.index_path.with_suffix(".json.tmp")
        try:
            tmp_path.write_text(
                json.dumps(self._index, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp_path.replace(self.index_path)
        except Exception as exc:
            logger.exception("[setu.cache] failed to save index %s: %s", self.index_path, exc)
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except Exception as exc2:
                logger.debug("[setu.cache] failed to remove temp index file: %s", exc2)

    def _prune_locked(self, now: int) -> int:
        # 清理过期和超出数量限制的缓存项
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
        # 移除缓存项（可选删除文件）
        entries = self._index.setdefault("entries", {})
        entry = entries.pop(key, None)
        if not entry:
            return
        if not delete_file:
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
        # 生成 URL 的哈希 key
        return hashlib.sha256(url.encode("utf-8", errors="ignore")).hexdigest()


class ImageService:
    """图片下载/发送服务，具备健壮的回退机制。"""

    def __init__(self, cache: UrlImageDiskCache | None = None):
        self._cache = cache

    async def download_single(
        self, session: aiohttp.ClientSession, url: str
    ) -> bytes | None:
        """下载单张图片，支持缓存。"""
        if not url:
            return None

        if self._cache:
            try:
                cached = await self._cache.get(url)
                if cached:
                    return cached
            except Exception as exc:
                logger.exception("[setu.cache] read failed url=%s : %s", url, exc)

        try:
            async with session.get(url, headers=DEFAULT_HEADERS) as resp:
                if resp.status == 404:
                    logger.warning("image 404: %s", url)
                    return None
                if not resp.ok:
                    logger.warning("image download failed (%d): %s", resp.status, url)
                    return None
                data = await resp.read()
                if not data:
                    return None
        except Exception as exc:
            logger.warning("image download error url=%s err=%s", url, exc)
            return None

        if self._cache:
            try:
                await self._cache.put(url, data)
            except Exception as exc:
                logger.exception("[setu.cache] write failed url=%s : %s", url, exc)
        return data

    async def download_parallel(self, urls: list[str]) -> list[bytes]:
        """并发下载多张图片，仅保留成功的图片数据。"""
        if not urls:
            return []
        timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                tasks = [self.download_single(session, url) for url in urls]
                results = await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as exc:
            logger.exception("download_parallel failed: %s",exc)
            return []

        downloaded: list[bytes] = []
        for result in results:
            if isinstance(result, bytes) and result:
                downloaded.append(result)
            elif isinstance(result, Exception):
                logger.warning("download task failed: %s", result)
        return downloaded

    async def send_images(
        self,
        event: AstrMessageEvent,
        images: list[bytes],
        found_message: str | None = None,
    ):
        """将所有图片一次性发送，失败时尝试混淆重发。"""
        try:
            message_chain = [Plain(found_message)] if found_message else []
            for img_data in images:
                message_chain.append(Image.fromBytes(img_data))
            yield event.chain_result(message_chain)
            return
        except Exception as exc:
            logger.warning("send_images direct failed, retry obfuscated: %s", exc)

        try:
            retry_text = f"{found_message} (混淆重发)" if found_message else ""
            message_chain = [Plain(retry_text)] if retry_text else []
            for img_data in images:
                obf_data = self._obfuscate_image_bytes(img_data)
                message_chain.append(Image.fromBytes(obf_data))
            yield event.chain_result(message_chain)
        except Exception as exc:
            logger.exception("send_images obfuscated retry failed: %s",exc)
            yield event.plain_result("图片发送失败，可能被平台审核拦截。")

    async def send_forward(
        self, event: AstrMessageEvent, images: list[bytes], bot_name: str = "Bot"
    ):
        """以合并转发节点方式发送图片。"""
        logger.info("[forward] building nodes total=%d", len(images))
        nodes = []
        for index, img_data in enumerate(images):
            try:
                node = Node(
                    uin=event.get_self_id(),
                    name=bot_name,
                    content=[Image.fromBytes(img_data)],
                )
                nodes.append(node)
            except Exception as exc:
                logger.exception("[forward] build node failed index=%d: %s", index, exc)
        if not nodes:
            yield event.plain_result("合并转发构建失败，未发送任何图片。")
            return
        yield event.chain_result([Nodes(nodes)])

    def _obfuscate_image_bytes(self, data: bytes) -> bytes:
        # 对图片字节流添加噪声以混淆
        import random

        noise = bytes(random.randint(0, 255) for _ in range(8))
        return data + noise
