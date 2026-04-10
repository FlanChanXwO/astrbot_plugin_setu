"""图片提供商基类。"""

from __future__ import annotations


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
