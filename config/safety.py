"""安全和缓存相关配置。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from astrbot.api import logger

from ..constants import DEFAULT_TAG_ALIAS
from .helpers import safe_bool, safe_int

if TYPE_CHECKING:
    pass


class SafetyConfigMixin:
    """安全和缓存配置混入类。

    注意：用户级黑白名单已完全分离为 setu 和 fortune 独立的配置，
    请通过 AccessControlManager 直接使用功能级黑白名单方法。
    """

    _read: Any

    @staticmethod
    def _normalize_access_mode(value: Any, default: str = "none") -> str:
        """规范化访问控制模式字符串。"""
        if isinstance(value, str) and value in {"none", "blacklist", "whitelist"}:
            return value
        return default

    @property
    def setu_access_control_mode(self) -> str:
        """色图访问控制模式（旧配置，兼容保留）。"""
        value = self._read(("safety", "setu_access_control_mode"), default="none")
        return self._normalize_access_mode(value)

    @property
    def fortune_access_control_mode(self) -> str:
        """运势访问控制模式（旧配置，兼容保留）。"""
        value = self._read(("safety", "fortune_access_control_mode"), default="none")
        return self._normalize_access_mode(value)

    @property
    def setu_user_access_control_mode(self) -> str:
        """色图用户访问控制模式。"""
        value = self._read(
            ("safety", "setu_user_access_control_mode"),
            "setu_user_access_control_mode",
            default=self.setu_access_control_mode,
        )
        return self._normalize_access_mode(value, self.setu_access_control_mode)

    @property
    def setu_group_access_control_mode(self) -> str:
        """色图群组访问控制模式。"""
        value = self._read(
            ("safety", "setu_group_access_control_mode"),
            "setu_group_access_control_mode",
            default=self.setu_access_control_mode,
        )
        return self._normalize_access_mode(value, self.setu_access_control_mode)

    @property
    def fortune_user_access_control_mode(self) -> str:
        """运势用户访问控制模式。"""
        value = self._read(
            ("safety", "fortune_user_access_control_mode"),
            "fortune_user_access_control_mode",
            default=self.fortune_access_control_mode,
        )
        return self._normalize_access_mode(value, self.fortune_access_control_mode)

    @property
    def fortune_group_access_control_mode(self) -> str:
        """运势群组访问控制模式。"""
        value = self._read(
            ("safety", "fortune_group_access_control_mode"),
            "fortune_group_access_control_mode",
            default=self.fortune_access_control_mode,
        )
        return self._normalize_access_mode(value, self.fortune_access_control_mode)

    @property
    def cache_enabled(self) -> bool:
        """是否启用图片缓存。

        返回:
            是否启用 URL 图片磁盘缓存
        """
        return safe_bool(self._read(("cache", "enabled"), default=True), True)

    @property
    def cache_ttl_hours(self) -> int:
        """缓存 TTL（小时）。

        返回:
            缓存条目的存活时间
        """
        return safe_int(self._read(("cache", "ttl_hours"), default=2), 2)

    @property
    def cache_max_items(self) -> int:
        """最大缓存条目数。

        返回:
            缓存最多保留的条目数量
        """
        return safe_int(self._read(("cache", "max_items"), default=1), 1)

    @property
    def cache_cleanup_on_start(self) -> bool:
        """启动时清理缓存。

        返回:
            启动时是否自动清理过期缓存
        """
        return safe_bool(self._read(("cache", "cleanup_on_start"), default=True), True)

    @property
    def download_concurrent_limit(self) -> int:
        """并发下载限制。

        返回:
            同时下载图片的最大并发数，适用于高带宽服务器
        """
        return safe_int(
            self._read(("performance", "download_concurrent_limit"), default=10),
            10,
        )

    @property
    def download_timeout_seconds(self) -> int:
        """下载超时时间（秒）。

        返回:
            单个图片下载的最大超时时间
        """
        return safe_int(
            self._read(("performance", "download_timeout_seconds"), default=30),
            30,
        )

    @property
    def enable_range_download(self) -> bool:
        """启用分段下载。

        返回:
            是否将单张大图分成多段并行下载
        """
        return safe_bool(
            self._read(("performance", "enable_range_download"), default=False),
            False,
        )

    @property
    def range_segments(self) -> int:
        """分段下载的段数。

        返回:
            单张图片的分段下载数，2-4 段通常效果最佳
        """
        return safe_int(
            self._read(("performance", "range_segments"), default=3),
            3,
        )

    @property
    def range_threshold(self) -> int:
        """分段下载阈值(KB)。

        返回:
            图片大于此值才启用分段下载(单位 KB)
        """
        return safe_int(
            self._read(("performance", "range_download_threshold"), default=512),
            512,
        )

    @property
    def tag_alias(self) -> dict[str, list[str]]:
        """标签别名映射。

        返回:
            标签到别名列表的映射字典
        """
        # 从 setu_general 读取（优先）或 safety（兼容旧配置）
        alias_str = self._read(
            ("setu_general", "tag_alias"),
            ("safety", "tag_alias"),
            "tag_alias",
            default="",
        )
        if not alias_str or not isinstance(alias_str, str):
            return DEFAULT_TAG_ALIAS

        result: dict[str, list[str]] = {}
        lines = alias_str.strip().replace("\r\n", "\n").split("\n")
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith(";"):
                continue

            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if not key or not value:
                continue
            aliases = [a.strip() for a in value.split(",") if a.strip()]
            if aliases:
                result[key] = aliases

        if not result:
            logger.debug("tag_alias parsing returned empty map, fallback to defaults")
            return DEFAULT_TAG_ALIAS.copy()
        return result

    def resolve_tags(self, raw_tag: str) -> list[str]:
        """解析并规范化标签字符串。

        将逗号或空格分隔的标签字符串解析为列表，并应用别名映射。

        参数:
            raw_tag: 原始标签字符串

        返回:
            规范化后的标签列表
        """
        if not raw_tag:
            return []

        normalized = raw_tag.replace("，", ",").replace(" ", ",")
        tags = [t.strip() for t in normalized.split(",") if t.strip()]

        result: list[str] = []
        for tag in tags:
            canonical = self._find_canonical_tag(tag)
            result.append(canonical if canonical else tag)
        return result

    def _find_canonical_tag(self, tag: str) -> str | None:
        """查找标签的标准名称。

        参数:
            tag: 标签名称（可能是别名）

        返回:
            标准标签名称，如果未找到返回 None
        """
        normalized = tag.lower()
        for canonical, aliases in self.tag_alias.items():
            if not isinstance(canonical, str):
                continue
            if normalized == canonical.lower():
                return canonical
            if isinstance(aliases, list):
                for alias in aliases:
                    if isinstance(alias, str) and normalized == alias.lower():
                        return canonical
        return None
