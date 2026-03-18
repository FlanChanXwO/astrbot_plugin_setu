"""HTML 卡片相关配置。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .helpers import safe_int

if TYPE_CHECKING:
    from .base import ConfigBase


class HtmlCardConfigMixin:
    """HTML 卡片配置混入类。"""

    _read: Any

    @property
    def html_card_strategy(self: ConfigBase) -> str:
        """HTML 卡片策略。

        返回:
            返回策略：never（从不）、fallback（失败时降级）、always（总是）
        """
        strategy = self._read(
            ("html_card", "strategy"), "html_card_strategy", default="fallback"
        )
        if strategy in ("never", "fallback", "always"):
            return strategy
        # 兼容旧版 enabled 配置
        old_enabled = self._read(("html_card", "enabled"), default=None)
        if old_enabled is True:
            return "fallback"
        return "never"

    @property
    def html_card_mode(self: ConfigBase) -> str:
        """HTML 卡片模式。

        返回:
            返回卡片模式：single（单张）、multiple（多张）
        """
        mode = self._read(("html_card", "mode"), "html_card_mode", default="single")
        return mode if mode in ("single", "multiple") else "single"

    @property
    def html_card_padding(self: ConfigBase) -> int:
        """HTML 卡片内边距。

        返回:
            卡片内部图片与边框的距离
        """
        return safe_int(self._read(("html_card", "card_padding"), default=6), 6)

    @property
    def html_card_gap(self: ConfigBase) -> int:
        """HTML 卡片间距。

        返回:
            多张图片之间的间距
        """
        return safe_int(self._read(("html_card", "card_gap"), default=6), 6)
