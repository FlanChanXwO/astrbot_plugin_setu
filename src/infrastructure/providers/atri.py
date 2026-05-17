"""Atri API 提供商。

文档: https://api.atri.rodeo
"""

from __future__ import annotations

import asyncio

import httpx

from ...application.ports import SetuImageProvider
from ...domain import HTTP_TIMEOUT_SECONDS
from ...shared import get_logger

logger = get_logger()


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
        logger.info(
            "[provider] Atri request: count=%d, r18=%s, tags=%s, size=%s, proxy=%s, exclude_ai=%s",
            num,
            r18,
            ",".join(tags) or "-",
            self.image_size,
            self.proxy or "-",
            exclude_ai,
        )
        exclude_ai_flag = self._normalize_bool(exclude_ai, default=True)
        query_params: list[tuple[str, str | int]] = [
            ("r18", 1 if r18 else 0),
            ("num", num),
            ("excludeAI", str(exclude_ai_flag).lower()),
            ("size", self.image_size),
        ]

        # 添加可选参数
        if self.proxy:
            query_params.append(("proxy", self.proxy))
        if self.aspect_ratio:
            query_params.append(("aspectRatio", self.aspect_ratio))
        if self.keyword:
            query_params.append(("keyword", self.keyword))

        # 重复参数由 httpx 统一编码处理
        for uid in self.uid:
            if uid is not None:
                query_params.append(("uid", uid))
        for tag in tags:
            if tag:
                query_params.append(("tag", tag))

        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
                resp = await client.get(self.API_URL, params=query_params)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as e:
            logger.warning("Atri API 响应错误: %s %s", e, e.request.url)
            return []
        except httpx.HTTPError as e:
            request_url = getattr(getattr(e, "request", None), "url", self.API_URL)
            logger.warning("Atri API 请求失败: %s %s", e, request_url)
            return []
        except asyncio.TimeoutError:
            logger.warning("Atri API 请求超时: %s", self.API_URL)
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
        urls = self._apply_proxy_to_urls(urls, self.proxy, "AtriProvider")
        logger.info(
            "[provider] Atri response: requested=%d, returned=%d",
            num,
            len(urls),
        )
        return urls
