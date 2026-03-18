"""HTML 卡片相关配置。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .helpers import safe_bool, safe_int

if TYPE_CHECKING:
    from .base import ConfigBase


class HtmlCardConfigMixin:
    """HTML 卡片配置混入类。"""

    _read: Any

    @property
    def html_card_mode(self: ConfigBase) -> str:
        """HTML 卡片模式。

        返回:
            返回卡片模式：single（单张）、multiple（多张）
        """
        mode = self._read(("html_card", "mode"), "html_card_mode", default="single")
        return mode if mode in ("single", "multiple") else "single"

    @property
    def enable_html_card(self: ConfigBase) -> bool:
        """是否启用 HTML 卡片包装。

        返回:
            是否将图片包装为 HTML 卡片以绕过审核
        """
        return safe_bool(
            self._read(("html_card", "enabled"), "enable_html_card", default=False),
            False,
        )

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
