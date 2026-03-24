"""发送和交付相关配置。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .helpers import safe_bool, safe_int

if TYPE_CHECKING:
    from .base import ConfigBase


class DeliveryConfigMixin:
    """发送配置混入类。"""

    _read: Any

    @property
    def r18_docx_mode(self: ConfigBase) -> bool:
        """R18 Docx 打包模式。

        返回:
            是否将 R18 图片打包到 docx 文件中
        """
        return safe_bool(
            self._read(("delivery", "r18_docx_mode"), "r18_docx_mode", default=True),
            True,
        )

    @property
    def send_mode(self: ConfigBase) -> str:
        """图片发送模式。

        返回:
            返回发送模式：image（直接发送）、forward（合并转发）、auto（自动）
        """
        mode = self._read(
            ("delivery", "send_mode"), "send_mode", "sendMode", default="image"
        )
        return mode if mode in ("image", "forward", "auto") else "image"

    @property
    def auto_handle_send_failure(self: ConfigBase) -> bool:
        """自动处理发送失败。

        返回:
            发送失败时是否自动尝试 HTML 卡片降级发送
        """
        return safe_bool(
            self._read(
                ("delivery", "auto_handle_send_failure"),
                "auto_handle_send_failure",
                default=True,
            ),
            True,
        )

    @property
    def auto_revoke_r18(self: ConfigBase) -> bool:
        """自动撤回 R18 内容。

        返回:
            是否自动撤回 R18 图片/文件
        """
        return safe_bool(
            self._read(
                ("delivery", "auto_revoke_r18"),
                "auto_revoke_r18",
                default=False,
            ),
            False,
        )

    @property
    def auto_revoke_delay(self: ConfigBase) -> int:
        """自动撤回延迟时间（秒）。

        返回:
            R18 内容发送后多久自动撤回
        """
        return safe_int(
            self._read(
                ("delivery", "auto_revoke_delay"),
                "auto_revoke_delay",
                default=30,
            ),
            30,
        )

    @property
    def max_count(self: ConfigBase) -> int:
        """每次请求最大图片数。

        返回:
            单次命令的上限
        """
        return safe_int(
            self._read(("general", "max_count"), "max_count", "maxCount", default=10),
            10,
        )

    @property
    def url_send_mode(self: ConfigBase) -> bool:
        """URL 发送模式。

        返回:
            是否直接发送图片 URL 而不是下载后发送
            开启后插件不会下载图片，而是直接发送图片链接
            可以降低服务器带宽和内存占用
        """
        return safe_bool(
            self._read(
                ("delivery", "url_send_mode"),
                "url_send_mode",
                default=False,
            ),
            False,
        )

    @property
    def url_send_verify(self: ConfigBase) -> bool:
        """URL 发送前验证链接有效性。

        返回:
            是否在发送前验证 URL 是否可访问（返回 200）
            仅当 url_send_mode 为 True 时生效
        """
        return safe_bool(
            self._read(
                ("delivery", "url_send_verify"),
                "url_send_verify",
                default=True,
            ),
            True,
        )

    @property
    def url_send_timeout(self: ConfigBase) -> int:
        """URL 验证超时时间（秒）。

        返回:
            验证 URL 时的 HTTP 请求超时时间
        """
        return safe_int(
            self._read(
                ("delivery", "url_send_timeout"),
                "url_send_timeout",
                default=5,
            ),
            5,
        )
