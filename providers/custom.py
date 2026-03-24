"""自定义 API 提供商。

支持用户配置任意 API 地址，并提供灵活的响应解析方式。
"""

from __future__ import annotations

from typing import Any

import httpx

from astrbot.api import logger

from ..constants import HTTP_TIMEOUT_SECONDS
from .base import SetuImageProvider


class CustomApiProvider(SetuImageProvider):
    """自定义 API 提供商。

    支持用户配置任意 API 地址，并提供灵活的响应解析方式。
    """

    def __init__(
        self,
        api_config: dict[str, Any] | None = None,
        parser_config: dict[str, Any] | None = None,
    ):
        """初始化自定义 API 提供商。

        参数:
            api_config: API 配置（url, method, timeout, headers）。
            parser_config: 响应解析配置（type, json_path）。
        """
        self.api_config = api_config or {}
        self.parser_config = parser_config or {}

    def _build_url(
        self, num: int, tags: list[str], r18: bool, exclude_ai: bool
    ) -> tuple[str, dict[str, Any] | None]:
        """构建请求 URL 和请求体。"""
        url_template = self.api_config.get("url", "")
        method = self.api_config.get("method", "GET").upper()

        # 替换 URL 中的占位符
        tags_str = ",".join(tags) if tags else ""
        url = url_template.replace("{num}", str(num))
        url = url.replace("{r18}", "1" if r18 else "0")
        url = url.replace("{tags}", tags_str)

        if method == "POST":
            # POST 请求，参数放 body
            body = {
                "num": num,
                "r18": r18,
                "tags": tags,
                "exclude_ai": exclude_ai,
            }
            return url, body
        else:
            # GET 请求
            return url, None

    def _parse_response(self, data: Any) -> list[str]:
        """解析 API 响应，提取图片 URL 列表。"""
        parser_type = self.parser_config.get("type", "auto")

        if parser_type == "json":
            return self._parse_json_response(data)
        else:
            return self._parse_auto_response(data)

    def _parse_json_response(self, data: Any) -> list[str]:
        """使用 JSON 路径表达式解析响应。"""
        json_path = self.parser_config.get("json_path", "")

        if not json_path or not isinstance(data, (dict, list)):
            return []

        try:
            # 简单的 JSON 路径解析
            # 支持 $.data[*].url 或 $.images 等形式
            result = self._get_value_by_path(data, json_path)

            if isinstance(result, str):
                return [result]
            elif isinstance(result, list):
                urls = []
                for item in result:
                    if isinstance(item, str):
                        urls.append(item)
                    elif isinstance(item, dict):
                        # 尝试从字典中提取 URL
                        url = item.get("url") or item.get("image") or item.get("link")
                        if url:
                            urls.append(url)
                return urls
            elif isinstance(result, dict):
                url = result.get("url") or result.get("image") or result.get("link")
                return [url] if url else []

        except Exception as e:
            logger.error("JSON 路径解析失败: %s", e)

        return []

    def _get_value_by_path(self, data: Any, path: str) -> Any:
        """根据路径表达式获取值。

        支持：
        - $.data.url (单级)
        - $.data[*].url (数组遍历)
        - $.data[0].url (指定索引)
        """
        # 移除开头的 $.
        path = path.lstrip("$.").strip()
        if not path:
            return data

        parts = path.split(".")
        current = data

        # 使用索引遍历，避免重复字段名导致的解析错误
        for idx, part in enumerate(parts):
            if current is None:
                return None

            # 处理数组索引 [*] 或 [n]
            if "[" in part and "]" in part:
                arr_name = part[: part.index("[")]
                idx_str = part[part.index("[") + 1 : part.index("]")]

                if arr_name:
                    current = (
                        current.get(arr_name) if isinstance(current, dict) else None
                    )

                if not isinstance(current, list):
                    return None

                if idx_str == "*":
                    # 遍历数组，获取下一级
                    # 使用 idx+1 代替 parts.index(part) 避免重复字段名问题
                    next_part = ".".join(parts[idx + 1 :])
                    if next_part:
                        results = []
                        for item in current:
                            val = self._get_value_by_path(item, next_part)
                            if val is not None:
                                if isinstance(val, list):
                                    results.extend(val)
                                else:
                                    results.append(val)
                        return results
                    else:
                        return current
                else:
                    try:
                        arr_idx = int(idx_str)
                        current = (
                            current[arr_idx] if 0 <= arr_idx < len(current) else None
                        )
                    except (ValueError, IndexError):
                        return None
            else:
                current = current.get(part) if isinstance(current, dict) else None

        return current

    def _parse_auto_response(self, data: Any) -> list[str]:
        """自动从响应中提取所有图片 URL。"""
        urls: list[str] = []

        def extract_urls(obj: Any) -> None:
            if isinstance(obj, str):
                # 检查是否是 URL
                if self._is_image_url(obj):
                    urls.append(obj)
            elif isinstance(obj, list):
                for item in obj:
                    extract_urls(item)
            elif isinstance(obj, dict):
                for key, value in obj.items():
                    # 优先检查可能的 URL 键
                    if key.lower() in (
                        "url",
                        "link",
                        "src",
                        "image",
                        "img",
                        "original",
                        "regular",
                    ):
                        if isinstance(value, str) and self._is_image_url(value):
                            urls.append(value)
                    else:
                        extract_urls(value)

        extract_urls(data)
        return list(dict.fromkeys(urls))  # 去重保持顺序

    def _is_image_url(self, url: str) -> bool:
        """检查字符串是否是图片 URL。"""
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            return False

        # 检查是否包含图片扩展名或常见图片域名
        image_exts = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp")
        image_hosts = ("pixiv", "img", "image", "pic", "photo", "cdn")

        url_lower = url.lower()
        has_ext = any(url_lower.endswith(ext) for ext in image_exts)
        has_host = any(host in url_lower for host in image_hosts)

        # URL 中包含图片相关特征
        return has_ext or has_host or "/img" in url_lower or "/image" in url_lower

    async def fetch_image_urls(
        self,
        num: int,
        tags: list[str],
        r18: bool,
        exclude_ai: bool = True,
    ) -> list[str]:
        """从自定义 API 获取图片 URL 列表。"""
        url, body = self._build_url(num, tags, r18, exclude_ai)

        if not url:
            logger.error("自定义 API URL 未配置")
            return []

        timeout = self.api_config.get("timeout", HTTP_TIMEOUT_SECONDS)
        headers = self.api_config.get("headers", {})

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                if body:
                    resp = await client.post(url, json=body, headers=headers)
                else:
                    resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()

                urls = self._parse_response(data)
                return urls[:num]  # 限制数量

        except Exception as e:
            logger.error("自定义 API 请求失败: %s", e)
            return []
