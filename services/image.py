"""图片下载/发送服务，支持 httpx 和 range 分段下载。"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import httpx

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.api.message_components import Image, Node, Nodes, Plain

from ..utils import obfuscate_image_bytes

if TYPE_CHECKING:
    from .cache import UrlImageDiskCache

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://www.pixiv.net/",
}

MAX_DOWNLOAD_SIZE_BYTES = 50 * 1024 * 1024
CHUNK_SIZE = 65536


class ImageService:
    """图片下载/发送服务，支持 httpx 和 range 分段下载。"""

    def __init__(
        self,
        cache: UrlImageDiskCache | None = None,
        concurrent_limit: int = 10,
        timeout_seconds: int = 30,
        tcp_connector_limit: int = 100,
        tcp_connector_limit_per_host: int = 30,
        enable_range_download: bool = False,
        range_segments: int = 3,
        range_threshold: int = 512,  # KB
    ):
        self._cache = cache
        self._download_semaphore = asyncio.Semaphore(max(1, concurrent_limit))
        self._timeout_seconds = max(10, timeout_seconds)
        self._tcp_connector_limit = max(50, tcp_connector_limit)
        self._tcp_connector_limit_per_host = max(20, tcp_connector_limit_per_host)
        self._enable_range_download = enable_range_download
        self._range_segments = max(2, min(8, range_segments))
        self._range_threshold = range_threshold * 1024  # Convert to bytes

        # httpx client (will be initialized lazily)
        self._httpx_client: httpx.AsyncClient | None = None

    def _get_headers_for_url(self, url: str) -> dict[str, str]:
        """根据 URL 获取合适的 headers。"""
        headers = dict(DEFAULT_HEADERS)
        if "i.pixiv.re" in url:
            headers["Referer"] = "https://www.pixiv.net/"
        return headers

    async def _get_httpx_client(self) -> httpx.AsyncClient:
        """获取或创建 httpx 客户端。"""
        if self._httpx_client is None:
            limits = httpx.Limits(
                max_connections=self._tcp_connector_limit,
                max_keepalive_connections=self._tcp_connector_limit_per_host,
            )
            timeout = httpx.Timeout(
                connect=10.0,
                read=self._timeout_seconds,
                write=10.0,
                pool=5.0,
            )
            self._httpx_client = httpx.AsyncClient(
                limits=limits,
                timeout=timeout,
                headers=DEFAULT_HEADERS,
                http2=True,
                follow_redirects=True,
            )
        return self._httpx_client

    async def close(self):
        """关闭所有客户端连接。"""
        if self._httpx_client:
            await self._httpx_client.aclose()
            self._httpx_client = None

    async def _download_with_httpx(self, url: str, retry: int = 1) -> bytes | None:
        """使用 httpx 下载单张图片，使用流式下载并强制大小限制。"""
        client = await self._get_httpx_client()
        headers = self._get_headers_for_url(url)

        for attempt in range(retry + 1):
            try:
                async with self._download_semaphore:
                    async with client.stream("GET", url, headers=headers) as response:
                        if response.status_code == 404:
                            logger.warning("image 404: %s", url)
                            return None
                        if response.status_code in (403, 401):
                            logger.warning(
                                "image access denied (%d): %s",
                                response.status_code,
                                url,
                            )
                            return None
                        if response.status_code == 429:
                            logger.warning("rate limited: %s", url)
                            if attempt < retry:
                                await asyncio.sleep(1)
                                continue
                            return None
                        if response.status_code < 200 or response.status_code >= 300:
                            logger.warning(
                                "image download failed (%d): %s",
                                response.status_code,
                                url,
                            )
                            if attempt < retry:
                                await asyncio.sleep(0.5)
                                continue
                            return None

                        # Check Content-Length header if available
                        content_length = response.headers.get("content-length")
                        if content_length:
                            try:
                                total_size = int(content_length)
                                if total_size > MAX_DOWNLOAD_SIZE_BYTES:
                                    logger.warning(
                                        "image too large (%d > %d): %s",
                                        total_size,
                                        MAX_DOWNLOAD_SIZE_BYTES,
                                        url,
                                    )
                                    return None
                            except (ValueError, TypeError):
                                pass

                        # Stream download with size enforcement
                        chunks: list[bytes] = []
                        total_read = 0
                        async for chunk in response.aiter_bytes(CHUNK_SIZE):
                            total_read += len(chunk)
                            if total_read > MAX_DOWNLOAD_SIZE_BYTES:
                                logger.warning(
                                    "image download exceeds size limit: %s", url
                                )
                                return None
                            chunks.append(chunk)

                        data = b"".join(chunks) if chunks else b""
                        if not data:
                            logger.warning("image download empty: %s", url)
                            return None

                        return data

            except httpx.TimeoutException as exc:
                logger.warning(
                    "httpx timeout (attempt %d/%d) url=%s: %s",
                    attempt + 1,
                    retry + 1,
                    url,
                    exc,
                )
                if attempt < retry:
                    await asyncio.sleep(0.5)
                    continue
                return None
            except httpx.ConnectError as exc:
                logger.warning(
                    "httpx connection error (attempt %d/%d) url=%s: %s",
                    attempt + 1,
                    retry + 1,
                    url,
                    exc,
                )
                if attempt < retry:
                    await asyncio.sleep(0.5)
                    continue
                return None
            except Exception as exc:
                logger.warning(
                    "httpx download error (attempt %d/%d) url=%s: %s",
                    attempt + 1,
                    retry + 1,
                    url,
                    exc,
                    exc_info=True,
                )
                if attempt < retry:
                    await asyncio.sleep(0.5)
                    continue
                return None

        return None

    async def _get_content_length(self, url: str) -> int | None:
        """通过 HEAD 请求获取 Content-Length。"""
        client = await self._get_httpx_client()
        headers = self._get_headers_for_url(url)

        try:
            async with self._download_semaphore:
                response = await client.head(
                    url, headers=headers, follow_redirects=True
                )
                if response.status_code >= 200 and response.status_code < 300:
                    content_length = response.headers.get("content-length")
                    if content_length:
                        return int(content_length)
        except Exception as exc:
            logger.debug("HEAD request failed for %s: %s", url, exc)

        return None

    async def _download_range_httpx(
        self, url: str, start: int, end: int
    ) -> bytes | None:
        """使用 httpx 下载指定 range，并验证返回数据大小。"""
        client = await self._get_httpx_client()
        headers = self._get_headers_for_url(url)
        headers["Range"] = f"bytes={start}-{end}"
        expected_length = end - start + 1

        try:
            async with self._download_semaphore:
                async with client.stream("GET", url, headers=headers) as response:
                    if response.status_code not in (200, 206):
                        logger.warning(
                            "range download failed (%d): %s", response.status_code, url
                        )
                        return None

                    # Stream the response and validate size
                    chunks: list[bytes] = []
                    total_read = 0
                    async for chunk in response.aiter_bytes(CHUNK_SIZE):
                        total_read += len(chunk)
                        # Each range segment should not exceed expected length by much
                        if total_read > expected_length + CHUNK_SIZE:
                            logger.warning(
                                "range download exceeded expected size for %s: expected %d, got >%d",
                                url,
                                expected_length,
                                total_read,
                            )
                            return None
                        chunks.append(chunk)

                    data = b"".join(chunks) if chunks else b""
                    if not data:
                        logger.warning("range download returned empty body: %s", url)
                        return None

                    actual_length = len(data)
                    # Allow some tolerance for servers that return slightly different sizes
                    if (
                        actual_length != expected_length
                        and abs(actual_length - expected_length) > 1
                    ):
                        logger.warning(
                            "range download size mismatch for %s: expected %d bytes, got %d",
                            url,
                            expected_length,
                            actual_length,
                        )
                        return None

                    return data

        except Exception as exc:
            logger.warning("range download error for %s: %s", url, exc)
            return None

    async def _download_single_with_range(
        self, url: str, retry: int = 1
    ) -> bytes | None:
        """使用 range 分段下载单张图片。"""
        # 先尝试获取 Content-Length
        total_size = await self._get_content_length(url)

        if total_size is None:
            # 服务器不支持 HEAD 或没有 Content-Length，使用普通下载
            logger.debug("Content-Length not available, using normal download: %s", url)
            return await self._download_with_httpx(url, retry)

        if total_size > MAX_DOWNLOAD_SIZE_BYTES:
            logger.warning(
                "image too large (%d > %d): %s",
                total_size,
                MAX_DOWNLOAD_SIZE_BYTES,
                url,
            )
            return None

        if total_size < self._range_threshold:
            # 图片太小，不需要分段
            logger.debug(
                "Image too small (%d bytes), using normal download: %s", total_size, url
            )
            return await self._download_with_httpx(url, retry)

        # 计算每段大小
        segment_size = total_size // self._range_segments
        ranges = []

        for i in range(self._range_segments):
            start = i * segment_size
            if i == self._range_segments - 1:
                end = total_size - 1
            else:
                end = start + segment_size - 1
            ranges.append((start, end))

        logger.debug("Downloading %s with %d ranges: %s", url, len(ranges), ranges)

        # 并行下载所有段
        tasks = [self._download_range_httpx(url, start, end) for start, end in ranges]
        results = await asyncio.gather(*tasks)

        # 检查是否有失败的段
        if any(r is None for r in results):
            logger.warning(
                "Some range segments failed for %s, retrying normal download", url
            )
            return await self._download_with_httpx(url, retry)

        # 合并所有段
        data = b"".join(results)

        if len(data) != total_size:
            logger.warning(
                "Range download size mismatch (%d vs %d) for %s",
                len(data),
                total_size,
                url,
            )
            return await self._download_with_httpx(url, retry)

        return data

    async def download_single(self, url: str, retry: int = 1) -> bytes | None:
        """下载单张图片，带缓存和重试机制。"""
        if not url:
            return None

        # 检查缓存
        if self._cache:
            try:
                cached = await self._cache.get(url)
                if cached:
                    return cached
            except Exception as exc:
                logger.exception("[setu.cache] read failed url=%s : %s", url, exc)

        # 选择下载方式
        data: bytes | None = None

        if self._enable_range_download:
            # 使用 httpx + range 下载
            data = await self._download_single_with_range(url, retry)
        else:
            # 使用 httpx 普通下载
            data = await self._download_with_httpx(url, retry)

        # 写入缓存
        if data and self._cache:
            try:
                await self._cache.put(url, data)
            except Exception as exc:
                logger.exception("[setu.cache] write failed url=%s : %s", url, exc)

        return data

    async def download_parallel(self, urls: list[str]) -> list[bytes]:
        """并发下载多张图片。"""
        if not urls:
            return []

        tasks = [self.download_single(url, retry=2) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        downloaded: list[bytes] = []
        for i, result in enumerate(results):
            if isinstance(result, bytes) and result:
                downloaded.append(result)
            elif isinstance(result, Exception):
                logger.warning(
                    "download task failed for %s: %s",
                    urls[i] if i < len(urls) else "unknown",
                    result,
                )

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
                obf_data = obfuscate_image_bytes(img_data)
                message_chain.append(Image.fromBytes(obf_data))
            yield event.chain_result(message_chain)
        except Exception as exc:
            logger.exception("send_images obfuscated retry failed: %s", exc)
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
