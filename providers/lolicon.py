"""Lolicon API V2 提供商。

文档: https://api.lolicon.app
"""

from __future__ import annotations

import asyncio
from urllib.parse import quote

import aiohttp

from astrbot.api import logger

from ..constants import HTTP_TIMEOUT_SECONDS
from .base import SetuImageProvider


class LoliconProvider(SetuImageProvider):
    """Lolicon API V2 提供商。

    文档: https://api.lolicon.app
    """

    API_URL = "https://api.lolicon.app/setu/v2"

    def __init__(
        self,
        image_size: str = "original",
        proxy: str = "i.pixiv.re",
        aspect_ratio: str = "",
        uid: list[int] | None = None,
        keyword: str = "",
    ):
        """初始化 Lolicon 提供商。

        参数:
            image_size: 图片规格 (original, regular, small, thumb, mini)
            proxy: 反代服务
            aspect_ratio: 图片长宽比
            uid: 指定作者 UID 列表
            keyword: 关键词搜索
        """
        self.image_size = image_size
        self.proxy = proxy
        self.aspect_ratio = aspect_ratio
        self.uid = uid or []
        self.keyword = keyword

    async def fetch_image_urls(
        self,
        num: int,
        tags: list[str],
        r18: bool,
        exclude_ai: bool = True,
    ) -> list[str]:
        params: dict[str, str | int | list] = {
            "r18": 1 if r18 else 0,
            "num": num,
            "excludeAI": str(exclude_ai).lower(),
            "size": self.image_size,
        }

        # 添加可选参数
        if self.proxy:
            params["proxy"] = self.proxy
        if self.aspect_ratio:
            params["aspectRatio"] = self.aspect_ratio
        if self.uid:
            params["uid"] = self.uid
        if self.keyword:
            params["keyword"] = self.keyword

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
                        logger.warning("Lolicon API 错误: %d %s", resp.status, url)
                        return []
                    data = await resp.json(content_type=None)
        except aiohttp.ClientResponseError as e:
            logger.warning("Lolicon API 响应错误: %s %s", e, url)
            return []
        except aiohttp.ClientError as e:
            logger.warning("Lolicon API 请求失败: %s %s", e, url)
            return []
        except asyncio.TimeoutError:
            logger.warning("Lolicon API 请求超时: %s", url)
            return []
        except Exception as e:
            logger.exception("Lolicon API 异常: %s", e)
            return []

        urls: list[str] = []
        for item in data.get("data", []):
            # 根据 size 参数返回对应的 URL
            urls_obj = item.get("urls", {})
            img_url = urls_obj.get(self.image_size)
            if img_url:
                urls.append(img_url)
        return urls
