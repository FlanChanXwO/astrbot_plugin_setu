"""SexNyanRun API 提供商。

文档: https://sex.nyan.run
"""

from __future__ import annotations

import asyncio
from urllib.parse import quote

import aiohttp

from astrbot.api import logger

from ..constants import HTTP_TIMEOUT_SECONDS
from .base import SetuImageProvider


class SexNyanRunProvider(SetuImageProvider):
    """SexNyanRun API 提供商。

    文档: https://sex.nyan.run
    """

    API_URL = "https://sex.nyan.run/api/v2/"

    def __init__(self):
        """初始化 SexNyanRun 提供商。"""
        pass

    async def fetch_image_urls(
        self,
        num: int,
        tags: list[str],
        r18: bool,
        exclude_ai: bool = True,
    ) -> list[str]:
        params: dict[str, str | int] = {
            "r18": str(r18).lower(),
            "num": num,
        }
        # 构建带多个 'tag' 参数的 URL（使用 URL 编码防止特殊字符问题）
        tag_params = "&".join(f"tag={quote(t, safe='')}" for t in tags) if tags else ""
        base_params = "&".join(
            f"{k}={quote(str(v), safe='')}" for k, v in params.items()
        )
        url = f"{self.API_URL}?{base_params}"
        if tag_params:
            url += f"&{tag_params}"

        try:
            timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as resp:
                    if not resp.ok:
                        logger.warning("SexNyanRun API 错误: %d %s", resp.status, url)
                        return []
                    data = await resp.json(content_type=None)
        except aiohttp.ClientResponseError as e:
            logger.warning("SexNyanRun API 响应错误: %s %s", e, url)
            return []
        except aiohttp.ClientError as e:
            logger.warning("SexNyanRun API 请求失败: %s %s", e, url)
            return []
        except asyncio.TimeoutError:
            logger.warning("SexNyanRun API 请求超时: %s", url)
            return []
        except Exception as e:
            logger.exception("SexNyanRun API 异常: %s", e)
            return []

        urls: list[str] = []
        for item in data.get("data", []):
            if isinstance(item, dict):
                img_url = item.get("url")
                if img_url:
                    urls.append(img_url)
        return urls
