"""图片下载/发送服务。"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import aiohttp

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.api.message_components import Image, Node, Nodes, Plain

from ..utils import obfuscate_image_bytes

if TYPE_CHECKING:
    from .cache import UrlImageDiskCache

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0"
    ),
    "Referer": "https://www.pixiv.net/",
}

MAX_CONCURRENT_DOWNLOADS = 10
MAX_DOWNLOAD_SIZE_BYTES = 50 * 1024 * 1024


class ImageService:
    """图片下载/发送服务，具备健壮的回退机制。"""

    def __init__(
        self,
        cache: UrlImageDiskCache | None = None,
        concurrent_limit: int = 10,
        timeout_seconds: int = 30,
        tcp_connector_limit: int = 100,
        tcp_connector_limit_per_host: int = 30,
        enable_http2: bool = True,
    ):
        self._cache = cache
        # 增加并发限制，提高下载速度
        self._download_semaphore = asyncio.Semaphore(max(1, concurrent_limit))
        self._timeout_seconds = max(10, timeout_seconds)
        # 增加连接池限制以提高高并发下载性能
        self._tcp_connector_limit = max(50, tcp_connector_limit)
        self._tcp_connector_limit_per_host = max(20, tcp_connector_limit_per_host)
        self._enable_http2 = enable_http2

    async def download_single(
        self, session: aiohttp.ClientSession, url: str
    ) -> bytes | None:
        """下载单张图片。"""
        if not url:
            return None

        if self._cache:
            try:
                cached = await self._cache.get(url)
                if cached:
                    return cached
            except Exception as exc:
                logger.exception("[setu.cache] read failed url=%s : %s", url, exc)

        async with self._download_semaphore:
            try:
                async with session.get(url) as resp:
                    if resp.status == 404:
                        logger.warning("image 404: %s", url)
                        return None
                    if not resp.ok:
                        logger.warning(
                            "image download failed (%d): %s", resp.status, url
                        )
                        return None

                    content_length = resp.headers.get("Content-Length")
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

                    chunks: list[bytes] = []
                    total_read = 0
                    async for chunk in resp.content.iter_chunked(8192):
                        total_read += len(chunk)
                        if total_read > MAX_DOWNLOAD_SIZE_BYTES:
                            logger.warning(
                                "image download exceeds size limit (%d > %d): %s",
                                total_read,
                                MAX_DOWNLOAD_SIZE_BYTES,
                                url,
                            )
                            return None
                        chunks.append(chunk)

                    data = b"".join(chunks) if chunks else b""
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
        """并发下载多张图片，优化版本。"""
        if not urls:
            return []

        # 使用更激进的超时设置
        timeout = aiohttp.ClientTimeout(
            total=self._timeout_seconds,
            connect=5,  # 减少连接超时时间
            sock_read=10,  # 减少读取超时时间
        )

        # 优化 TCP 连接器配置
        connector = aiohttp.TCPConnector(
            limit=self._tcp_connector_limit,
            limit_per_host=self._tcp_connector_limit_per_host,
            enable_cleanup_closed=True,
            force_close=False,
            ttl_dns_cache=300,  # DNS 缓存 5 分钟
            use_dns_cache=True,
            family=0,  # 允许 IPv4 和 IPv6
        )

        try:
            async with aiohttp.ClientSession(
                timeout=timeout,
                connector=connector,
                headers=DEFAULT_HEADERS,
            ) as session:
                # 使用 asyncio.wait 配合 return_when=ALL_COMPLETED 可能会更快
                tasks = [self.download_single(session, url) for url in urls]
                results = await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as exc:
            logger.exception("download_parallel failed: %s", exc)
            return []
        finally:
            await connector.close()

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
