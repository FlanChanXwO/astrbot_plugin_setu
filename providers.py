"""图片提供商实现，使用策略模式。"""

from __future__ import annotations

import asyncio
import random
from typing import Any
from urllib.parse import quote

import aiohttp

from astrbot.api import logger

from .constants import HTTP_TIMEOUT_SECONDS


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


class MultiApiProvider(SetuImageProvider):
    """多 API 提供商，支持轮询、随机和故障转移策略。"""

    def __init__(
        self, providers: list[SetuImageProvider], strategy: str = "round_robin"
    ):
        """初始化多 API 提供商。

        参数:
            providers: 提供商实例列表。
            strategy: 策略类型（'round_robin'、'random'、'failover'）。
        """
        self.providers = providers
        self.strategy = strategy
        self._current_index = 0
        self._last_working_index = 0

    def _get_next_provider(self) -> SetuImageProvider:
        """根据策略获取下一个提供商。"""
        if self.strategy == "random":
            return random.choice(self.providers)
        elif self.strategy == "failover":
            # 故障转移：从上次成功的开始
            return self.providers[self._last_working_index]
        else:
            # 轮询
            provider = self.providers[self._current_index % len(self.providers)]
            self._current_index += 1
            return provider

    async def fetch_image_urls(
        self,
        num: int,
        tags: list[str],
        r18: bool,
        exclude_ai: bool = True,
    ) -> list[str]:
        """从多个 API 获取图片 URL 列表。"""
        if self.strategy == "failover":
            # 故障转移模式：逐个尝试直到成功
            for i in range(len(self.providers)):
                idx = (self._last_working_index + i) % len(self.providers)
                provider = self.providers[idx]
                try:
                    urls = await provider.fetch_image_urls(num, tags, r18, exclude_ai)
                    if urls:
                        self._last_working_index = idx
                        return urls
                except Exception as e:
                    logger.warning("API %d 失败: %s，尝试下一个", idx, e)
                    continue
            return []
        elif self.strategy == "random":
            # 随机模式：逐个随机选择，失败时继续尝试其他
            tried_indices = set()
            while len(tried_indices) < len(self.providers):
                idx = random.randrange(len(self.providers))
                if idx in tried_indices:
                    continue
                tried_indices.add(idx)
                provider = self.providers[idx]
                try:
                    urls = await provider.fetch_image_urls(num, tags, r18, exclude_ai)
                    if urls:
                        return urls
                except Exception as e:
                    logger.warning("API %d 失败: %s，尝试下一个", idx, e)
                    continue
            return []
        else:
            # 轮询模式：逐个尝试，失败时继续尝试其他
            for i in range(len(self.providers)):
                idx = (self._current_index + i) % len(self.providers)
                provider = self.providers[idx]
                try:
                    urls = await provider.fetch_image_urls(num, tags, r18, exclude_ai)
                    self._current_index = (idx + 1) % len(self.providers)
                    if urls:
                        return urls
                except Exception as e:
                    logger.warning("API %d 失败: %s，尝试下一个", idx, e)
                    continue
            return []


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
        base_params = "&".join(f"{k}={quote(str(v), safe='')}" for k, v in params.items())
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
        base_params = "&".join(f"{k}={quote(str(v), safe='')}" for k, v in params.items())
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
                        current = current[arr_idx] if 0 <= arr_idx < len(current) else None
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

        timeout = aiohttp.ClientTimeout(
            total=self.api_config.get("timeout", HTTP_TIMEOUT_SECONDS)
        )
        headers = self.api_config.get("headers", {})

        async with aiohttp.ClientSession(timeout=timeout) as session:
            try:
                if body:
                    async with session.post(url, json=body, headers=headers) as resp:
                        resp.raise_for_status()
                        data = await resp.json(content_type=None)
                else:
                    async with session.get(url, headers=headers) as resp:
                        resp.raise_for_status()
                        data = await resp.json(content_type=None)

                urls = self._parse_response(data)
                return urls[:num]  # 限制数量

            except Exception as e:
                logger.error("自定义 API 请求失败: %s", e)
                return []


# 提供商注册表
PROVIDERS: dict[str, type[SetuImageProvider]] = {
    "lolicon": LoliconProvider,
    "sexnyan": SexNyanRunProvider,
}

# 多API策略下的内置提供商列表
BUILTIN_PROVIDERS = ["lolicon", "sexnyan"]


def get_provider(
    api_type: str,
    custom_config: dict[str, Any] | None = None,
    parser_config: dict[str, Any] | None = None,
    custom_api_configs: list[dict[str, Any]] | None = None,
    multi_api_strategy: str = "round_robin",
    lolicon_config: dict[str, Any] | None = None,
) -> SetuImageProvider | MultiApiProvider:
    """根据类型名称获取提供商实例。

    参数:
        api_type: 提供商类型（'lolicon'、'sexnyan'、'custom' 或 'all'）。
        custom_config: 自定义 API 配置（当 api_type 为 custom 时使用）。
        parser_config: API 响应解析配置（当 api_type 为 custom 时使用）。
        custom_api_configs: 自定义 API 配置列表（template_list 格式）。
        multi_api_strategy: 多 API 策略（'round_robin'、'random'、'failover'）。
        lolicon_config: Lolicon 专属配置参数。

    返回:
        提供商实例（如果类型未知则默认返回 lolicon）。
    """
    if api_type == "all":
        # 创建多API提供商（内置API）
        providers = []
        for name in BUILTIN_PROVIDERS:
            if name == "lolicon" and lolicon_config:
                provider = LoliconProvider(**lolicon_config)
            else:
                provider = PROVIDERS[name]()
            providers.append(provider)
        return MultiApiProvider(providers, strategy=multi_api_strategy)

    if api_type == "custom":
        # 优先使用新的 template_list 配置格式
        if (
            custom_api_configs
            and isinstance(custom_api_configs, list)
            and len(custom_api_configs) > 0
        ):
            if len(custom_api_configs) == 1:
                # 只有一个配置，直接使用
                cfg = custom_api_configs[0]
                api_config = {
                    "url": cfg.get("url", ""),
                    "method": cfg.get("method", "GET"),
                    "timeout": cfg.get("timeout", 30),
                }
                parser_cfg = {
                    "type": cfg.get("parser_type", "auto"),
                    "json_path": cfg.get("json_path", ""),
                }
                return CustomApiProvider(api_config, parser_cfg)
            else:
                # 多个配置，创建多API提供商
                providers = []
                for cfg in custom_api_configs:
                    api_config = {
                        "url": cfg.get("url", ""),
                        "method": cfg.get("method", "GET"),
                        "timeout": cfg.get("timeout", 30),
                    }
                    parser_cfg = {
                        "type": cfg.get("parser_type", "auto"),
                        "json_path": cfg.get("json_path", ""),
                    }
                    providers.append(CustomApiProvider(api_config, parser_cfg))
                return MultiApiProvider(providers, strategy=multi_api_strategy)

        # 兼容旧的配置格式
        if custom_config:
            return CustomApiProvider(custom_config, parser_config or {})

        logger.warning("api_type 为 custom 但未提供配置，回退到 lolicon")
        if lolicon_config:
            return LoliconProvider(**lolicon_config)
        return LoliconProvider()

    provider_cls = PROVIDERS.get(api_type)
    if provider_cls is None:
        logger.warning("未知的 api_type '%s'，回退到 lolicon", api_type)
        provider_cls = LoliconProvider

    # 创建实例
    if api_type == "lolicon" and lolicon_config:
        return provider_cls(**lolicon_config)
    return provider_cls()
