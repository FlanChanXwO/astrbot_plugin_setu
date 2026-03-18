"""多 API 提供商，支持轮询、随机和故障转移策略。"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from astrbot.api import logger

if TYPE_CHECKING:
    from .base import SetuImageProvider


class MultiApiProvider:
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
