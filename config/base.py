"""配置基础类。"""

from __future__ import annotations

from typing import Any

from astrbot.core import AstrBotConfig


class ConfigBase:
    """配置基础类，提供嵌套配置读取功能。"""

    def __init__(self, config: AstrBotConfig):
        """初始化配置包装器。

        参数:
            config: AstrBot 配置对象
        """
        self._cfg = config

    def _read(
        self,
        nested_path: tuple[str, ...],
        *legacy_keys: str,
        default: Any = None,
    ) -> Any:
        """读取配置值，支持嵌套路径和旧版键名回退。

        优先尝试嵌套路径读取，如果失败则尝试旧版键名，最后返回默认值。

        参数:
            nested_path: 嵌套配置路径，如 ("general", "api_type")
            *legacy_keys: 旧版配置键名，用于兼容性回退
            default: 默认值，读取失败时返回

        返回:
            配置值或默认值
        """
        current: Any = self._cfg
        for key in nested_path:
            if isinstance(current, dict):
                current = current.get(key)
            elif hasattr(current, "get"):
                current = current.get(key)
            else:
                current = None
            if current is None:
                break

        if current is not None:
            return current

        # 尝试旧版键名
        for key in legacy_keys:
            try:
                value = self._cfg.get(key)
            except (KeyError, AttributeError):
                value = None
            if value is not None:
                return value
        return default
