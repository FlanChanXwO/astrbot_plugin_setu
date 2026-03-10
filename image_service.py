"""Setu 插件的图片下载和发送服务。"""

from __future__ import annotations

import asyncio
import base64

import aiohttp
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.api.message_components import Node, Plain, Image

from .constants import HTTP_TIMEOUT_SECONDS

# 图片下载的默认请求头
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0"
    ),
    "Referer": "https://www.pixiv.net/",
}


class ImageService:
    """图片下载和发送服务。"""

    async def download_single(
        self, session: aiohttp.ClientSession, url: str
    ) -> bytes | None:
        """下载单张图片。成功返回字节数据，失败返回 None。"""
        try:
            async with session.get(url, headers=DEFAULT_HEADERS) as resp:
                if resp.status == 404:
                    logger.warning("图片 404: %s", url)
                    return None
                if not resp.ok:
                    logger.warning("图片下载失败 (%d): %s", resp.status, url)
                    return None
                data = await resp.read()
                if not data:
                    return None
                return data
        except Exception as exc:
            logger.warning("图片下载错误: %s %s", url, exc)
            return None

    async def download_parallel(self, urls: list[str]) -> list[bytes]:
        """并发下载多张图片。

        参数:
            urls: 图片 URL 列表。

        返回:
            成功下载的图片字节数据列表。
        """
        timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            tasks = [self.download_single(session, url) for url in urls]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        downloaded: list[bytes] = []
        for r in results:
            if isinstance(r, bytes) and r:
                downloaded.append(r)
        return downloaded

    async def send_images(
        self, event: AstrMessageEvent, images: list[bytes]
    ):
        """直接发送图片。发送失败时尝试使用混淆重试。"""
        result_text = f"找到 {len(images)} 张符合要求的图片~"

        # 尝试在一个消息链中发送所有图片
        try:
            message_chain = [Plain(result_text)]
            for img_data in images:
                message_chain.append(Image.fromBytes(img_data))
            yield event.chain_result(message_chain)
            return
        except Exception as exc:
            logger.warning("直接发送图片失败，尝试混淆重发: %s", exc)

        # 使用混淆图片重试
        try:
            message_chain = [Plain(result_text + " (混淆重发)")]
            for img_data in images:
                obf_data = self._obfuscate_image_bytes(img_data)
                message_chain.append(Image.fromBytes(obf_data))
            yield event.chain_result(message_chain)
        except Exception as exc:
            logger.error("混淆后发送仍然失败: %s", exc)
            yield event.plain_result("图片发送失败，可能被平台审核拦截。")

    async def send_forward(
        self, event: AstrMessageEvent, images: list[bytes], bot_name: str = "Bot"
    ):
        """以合并转发方式发送图片。

        使用 Node 组件构造合并转发消息。
        """
        logger.info("[forward 模式] 开始构造合并转发消息，共 %d 张图片", len(images))

        nodes = []
        for i, img_data in enumerate(images):
            # 构造 Node 节点
            node = Node(
                uin=event.get_self_id(),
                name=bot_name,
                content=[Image.fromBytes(img_data)]
            )
            nodes.append(node)
            logger.debug("[forward 模式] 构造第 %d 张图片节点", i + 1)

        # 发送合并转发消息
        logger.info("[forward 模式] 发送合并转发消息，共 %d 个节点", len(nodes))
        yield event.chain_result(nodes)

    def _obfuscate_image_bytes(self, data: bytes) -> bytes:
        """对图片数据进行最小程度的混淆以绕过图片哈希检查。

        在图片数据末尾添加随机字节来改变其哈希值，同时保持图片视觉内容不变。
        """
        import random
        noise = bytes(random.randint(0, 255) for _ in range(8))
        return data + noise
