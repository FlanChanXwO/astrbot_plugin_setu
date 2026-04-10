"""Atri API 提供商。

文档: https://api.atri.rodeo
"""

from __future__ import annotations

import asyncio
from urllib.parse import quote

import httpx

from astrbot.api import logger

from ..constants import HTTP_TIMEOUT_SECONDS
from .base import SetuImageProvider


class AtriProvider(SetuImageProvider):
    """Atri API 提供商。

    文档: https://api.atri.rodeo
    """

    API_URL = "https://api.atri.rodeo/setu"

    def __init__(
        self,
        image_size: str = "original",
        proxy: str = "i.pixiv.re",
        aspect_ratio: str = "",
        uid: list[int] | None = None,
        keyword: str = "",
    ):
        """初始化 Atri 提供商。

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
        params: dict[str, str | int] = {
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
        if self.keyword:
            params["keyword"] = self.keyword

        # 构建重复参数：tag=...&tag=... 与 uid=...&uid=...
        tag_params = (
            "&".join(f"tag={quote(str(t), safe='')}" for t in tags) if tags else ""
        )
        uid_params = (
            "&".join(f"uid={quote(str(u), safe='')}" for u in self.uid if u is not None)
            if self.uid
            else ""
        )
        base_params = "&".join(
            f"{k}={quote(str(v), safe='')}" for k, v in params.items()
        )
        url = f"{self.API_URL}?{base_params}"
        if uid_params:
            url += f"&{uid_params}"
        if tag_params:
            url += f"&{tag_params}"

        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as e:
            logger.warning("Atri API 响应错误: %s %s", e, url)
            return []
        except httpx.HTTPError as e:
            logger.warning("Atri API 请求失败: %s %s", e, url)
            return []
        except asyncio.TimeoutError:
            logger.warning("Atri API 请求超时: %s", url)
            return []
        except Exception as e:
            logger.exception("Atri API 异常: %s", e)
            return []

        urls: list[str] = []
        for item in data.get("data", []):
            # 根据 size 参数返回对应的 URL
            urls_obj = item.get("urls", {})
            img_url = urls_obj.get(self.image_size)
            if img_url:
                urls.append(img_url)
        return urls
