"""消息配置相关。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .helpers import safe_bool

if TYPE_CHECKING:
    from .base import ConfigBase


class MessagesConfigMixin:
    """消息配置混入类。"""

    _read: Any

    @property
    def msg_fetching_enabled(self: "ConfigBase") -> bool:
        """是否启用获取中提示。

        返回:
            开始获取图片时是否发送提示消息
        """
        return safe_bool(
            self._read(("messages", "fetching", "enabled"), default=True),
            True,
        )

    @property
    def msg_fetching_text(self: "ConfigBase") -> str:
        """获取中提示文本。

        返回:
            开始获取图片时显示的文本
        """
        return str(
            self._read(
                ("messages", "fetching", "text"),
                default="正在获取图片，请稍候...",
            )
        )

    @property
    def msg_found_enabled(self: "ConfigBase") -> bool:
        """是否启用找到图片提示。

        返回:
            成功找到图片后是否发送提示消息
        """
        return safe_bool(
            self._read(("messages", "found", "enabled"), default=True),
            True,
        )

    @property
    def msg_found_text(self: "ConfigBase") -> str:
        """找到图片提示文本。

        返回:
            成功找到图片后显示的文本，可使用 {count} 占位符
        """
        return str(
            self._read(
                ("messages", "found", "text"),
                default="找到 {count} 张符合要求的图片~",
            )
        )

    @property
    def msg_send_failed_text(self: "ConfigBase") -> str:
        """发送失败提示文本。

        返回:
            图片发送失败时显示的文本
        """
        return str(
            self._read(
                ("messages", "send_failed", "text"),
                "msg_send_failed_text",
                default="图片发送失败，请稍后再试。",
            )
        )

    def format_found_message(
        self: "ConfigBase", count: int, revoke_delay: int | None = None
    ) -> str:
        """格式化找到图片的消息。

        将 msg_found_text 中的 {count} 和 {revoke_delay} 占位符替换为实际值。

        参数:
            count: 找到的图片数量
            revoke_delay: 自动撤回延迟（秒），为 None 时不替换该变量

        返回:
            格式化后的消息文本
        """
        result = self.msg_found_text.replace("{count}", str(count))
        if revoke_delay is not None:
            result = result.replace("{revoke_delay}", str(revoke_delay))
        return result
