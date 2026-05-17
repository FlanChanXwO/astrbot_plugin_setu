"""图片提供商基类。"""

from __future__ import annotations

import asyncio
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import httpx

from ...domain.setu import SetuRequest
from ...shared import get_logger
from ...shared.send_cache import get_send_cache
from ..setu.dto import ImagePayload

logger = get_logger()


class SetuImageProvider:
    """色图图片提供商基类（策略模式）。"""

    async def fetch_image_urls(
        self,
        num: int,
        tags: list[str],
        r18: bool,
        exclude_ai: bool = True,
    ) -> list[str]:
        """从 API 获取图片 URL 列表。

        参数:
            num: 要获取的图片数量。
            tags: 搜索标签/关键词。
            r18: 是否请求 R18 内容。
            exclude_ai: 是否排除 AI 生成的作品。

        返回:
            图片 URL 列表。
        """
        raise NotImplementedError

    async def fetch_and_download(self, request: SetuRequest) -> ImagePayload:
        """Fetch image URLs and download them to local files for delivery."""
        provider_name = self._provider_name()
        logger.info(
            "[provider] fetch start: provider=%s, count=%d, r18=%s, tags=%s, exclude_ai=%s",
            provider_name,
            request.count,
            request.r18,
            ",".join(request.tags) or "-",
            request.exclude_ai,
        )
        urls = await self.fetch_image_urls(
            num=request.count,
            tags=list(request.tags),
            r18=request.r18,
            exclude_ai=request.exclude_ai,
        )
        if not urls:
            logger.warning(
                "[provider] no urls returned: provider=%s, count=%d, r18=%s, tags=%s",
                provider_name,
                request.count,
                request.r18,
                ",".join(request.tags) or "-",
            )
            return ImagePayload(
                urls=(), raw_bytes=(), file_paths=(), r18=request.r18, tags=request.tags
            )

        cache = get_send_cache()
        cache_enabled = bool(cache and cache.enabled)
        logger.info(
            "[provider] fetch result: provider=%s, urls=%d, cache_enabled=%s",
            provider_name,
            len(urls),
            cache_enabled,
        )

        async def download(client: httpx.AsyncClient, url: str) -> Path | bytes | None:
            try:
                if cache_enabled and cache:
                    cached = await cache.get(url)
                    if cached is not None:
                        logger.debug(
                            "[provider] cache hit: provider=%s, url=%s",
                            provider_name,
                            url,
                        )
                        return cached

                if cache is not None:
                    write = None
                    try:
                        async with client.stream("GET", url) as response:
                            response.raise_for_status()
                            write = await cache.reserve(
                                url, response.headers.get("content-type")
                            )
                            with write.temp_path.open("wb") as file:
                                async for chunk in response.aiter_bytes():
                                    if chunk:
                                        await asyncio.to_thread(file.write, chunk)
                        final_path = await cache.commit(write)
                        logger.debug(
                            "[provider] download cached: provider=%s, url=%s, path=%s",
                            provider_name,
                            url,
                            final_path,
                        )
                        return final_path
                    except Exception:
                        if write is not None:
                            await cache.discard(write)
                        raise

                response = await client.get(url)
                response.raise_for_status()
                logger.debug(
                    "[provider] download bytes: provider=%s, url=%s, bytes=%d",
                    provider_name,
                    url,
                    len(response.content),
                )
                return response.content
            except (httpx.HTTPError, asyncio.TimeoutError) as exc:
                logger.warning(
                    "[provider] download failed: provider=%s, url=%s, error=%s",
                    provider_name,
                    url,
                    exc,
                )
                return None

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            results = await asyncio.gather(*(download(client, url) for url in urls))

        items = tuple(item for item in results if item is not None)
        raw_bytes = tuple(item for item in items if isinstance(item, bytes))
        file_paths = tuple(item for item in items if isinstance(item, Path))
        logger.info(
            "[provider] download summary: provider=%s, requested=%d, succeeded=%d, failed=%d, bytes=%d, files=%d",
            provider_name,
            len(urls),
            len(items),
            len(urls) - len(items),
            len(raw_bytes),
            len(file_paths),
        )
        if not items:
            logger.error(
                "[provider] all downloads failed: provider=%s, requested=%d, tags=%s",
                provider_name,
                len(urls),
                ",".join(request.tags) or "-",
            )
        return ImagePayload(
            urls=tuple(urls),
            raw_bytes=raw_bytes,
            file_paths=file_paths,
            items=items,
            r18=request.r18,
            tags=request.tags,
        )

    def _provider_name(self) -> str:
        return self.__class__.__name__

    def _apply_proxy_to_url(self, url: str, proxy: str | None) -> str:
        """Rewrite Pixiv-style image URLs to the configured reverse proxy host."""
        proxy_host = (proxy or "").strip()
        if not proxy_host:
            return url

        try:
            parsed = urlsplit(url)
        except ValueError:
            return url

        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return url

        original_host = parsed.hostname or ""
        proxy_targets = {
            "i.pximg.net",
            "i.pixiv.re",
            "i.pixiv.cat",
            "proxy.pixivel.moe",
        }
        if original_host not in proxy_targets:
            return url

        if ":" in proxy_host:
            netloc = proxy_host
        else:
            netloc = proxy_host
        return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))

    def _apply_proxy_to_urls(
        self, urls: list[str], proxy: str | None, provider_name: str
    ) -> list[str]:
        if not proxy:
            return urls

        rewritten = [self._apply_proxy_to_url(url, proxy) for url in urls]
        changed = sum(1 for old, new in zip(urls, rewritten, strict=False) if old != new)
        if changed:
            logger.info(
                "[provider] proxy rewritten: provider=%s, proxy=%s, changed=%d",
                provider_name,
                proxy,
                changed,
            )
        else:
            logger.debug(
                "[provider] proxy rewrite skipped: provider=%s, proxy=%s, urls=%d",
                provider_name,
                proxy,
                len(urls),
            )
        return rewritten

    @staticmethod
    def _normalize_bool(value, default: bool = True) -> bool:
        """Normalize possibly-dirty boolean input from config/runtime sources."""
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "1", "yes", "on"}:
                return True
            if lowered in {"false", "0", "no", "off"}:
                return False
            if lowered in {"none", "null", ""}:
                return default
        return default


ImageProvider = SetuImageProvider
