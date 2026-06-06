"""图片提供商基类。"""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from ...domain.setu import SetuRequest
from ...shared import get_logger
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
        """Fetch and materialize image data for delivery."""
        raise NotImplementedError

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
        return urlunsplit(
            (parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment)
        )

    def _apply_proxy_to_urls(
        self, urls: list[str], proxy: str | None, provider_name: str
    ) -> list[str]:
        if not proxy:
            return urls

        rewritten = [self._apply_proxy_to_url(url, proxy) for url in urls]
        changed = sum(
            1 for old, new in zip(urls, rewritten, strict=False) if old != new
        )
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
