"""AstrBot Setu Plugin 日志包装器

提供带插件前缀的日志记录器，避免直接导出单例实例。

使用示例:
    from .logger import get_logger

    logger = get_logger()
    logger.info("消息")
"""

from __future__ import annotations

from typing import Any

from astrbot.api import logger as _astrbot_logger


class PrefixedLogger:
    """AstrBot 日志包装器，添加插件前缀并正确显示调用位置。"""

    PREFIX = "[setu] "
    CALLER_STACKLEVEL = 2

    def _add_prefix(self, msg: object) -> str:
        """为消息添加前缀。"""
        return self.PREFIX + str(msg)

    def _with_stacklevel(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        """确保 stacklevel 参数正确传递以显示真实调用位置。"""
        copied = dict(kwargs)
        if "stacklevel" not in copied:
            copied["stacklevel"] = self.CALLER_STACKLEVEL
        return copied

    def debug(self, msg: object, *args: Any, **kwargs: Any) -> None:
        _astrbot_logger.debug(
            self._add_prefix(msg), *args, **self._with_stacklevel(kwargs)
        )

    def info(self, msg: object, *args: Any, **kwargs: Any) -> None:
        _astrbot_logger.info(
            self._add_prefix(msg), *args, **self._with_stacklevel(kwargs)
        )

    def warning(self, msg: object, *args: Any, **kwargs: Any) -> None:
        _astrbot_logger.warning(
            self._add_prefix(msg), *args, **self._with_stacklevel(kwargs)
        )

    def error(self, msg: object, *args: Any, **kwargs: Any) -> None:
        _astrbot_logger.error(
            self._add_prefix(msg), *args, **self._with_stacklevel(kwargs)
        )

    def exception(self, msg: object, *args: Any, **kwargs: Any) -> None:
        _astrbot_logger.exception(
            self._add_prefix(msg), *args, **self._with_stacklevel(kwargs)
        )

    def critical(self, msg: object, *args: Any, **kwargs: Any) -> None:
        _astrbot_logger.critical(
            self._add_prefix(msg), *args, **self._with_stacklevel(kwargs)
        )


# 内部缓存，禁止直接导出
_logger_instance: PrefixedLogger | None = None


def get_logger() -> PrefixedLogger:
    """获取插件日志记录器单例。

    Returns:
        PrefixedLogger 实例
    """
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = PrefixedLogger()
    return _logger_instance


def clear_logger() -> None:
    """清除日志记录器单例（用于测试）。"""
    global _logger_instance
    _logger_instance = None
