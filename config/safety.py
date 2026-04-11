"""安全和缓存相关配置。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from astrbot.api import logger

from ..constants import DEFAULT_TAG_ALIAS
from .helpers import safe_bool, safe_int

if TYPE_CHECKING:
    pass


class SafetyConfigMixin:
    """安全和缓存配置混入类。"""

    _read: Any

    def _log_conflicts_if_any(self) -> None:
        """检测并记录黑白名单冲突警告。"""
        # 检测用户冲突
        user_conflicts = set(self.blocked_users) & set(self.whitelist_users)
        if user_conflicts:
            logger.warning(
                "[access_control] 用户同时存在于黑白名单中: %s，黑名单优先",
                user_conflicts
            )

        # 检测群组冲突
        group_conflicts = set(self.blocked_groups) & set(self.whitelist_groups)
        if group_conflicts:
            logger.warning(
                "[access_control] 群组同时存在于黑白名单中: %s，黑名单优先",
                group_conflicts
            )

    @property
    def access_control_mode(self) -> str:
        """访问控制模式。

        返回:
            none=不启用黑白名单，blacklist=仅黑名单模式，whitelist=仅白名单模式
        """
        mode = self._read(
            ("safety", "access_control_mode"),
            "access_control_mode",
            default="blacklist",
        )
        mode = str(raw_mode).strip().lower()

        valid_modes = ("none", "blacklist", "whitelist")
        if mode not in valid_modes:
            logger.warning(
                "Invalid access_control_mode %r (normalized: %r), falling back to 'blacklist'",
                raw_mode,
                mode,
            )
            return "blacklist"
        return mode

    @property
    def blocked_groups(self) -> list[str]:
        """被屏蔽的群聊列表（黑名单）。

        返回:
            群聊 ID 列表，这些群聊将禁止使用插件功能
        """
        groups = self._read(("safety", "blocked_groups"), "blocked_groups", default=[])
        if isinstance(groups, list):
            return [str(g).strip() for g in groups if str(g).strip()]
        return []

    @property
    def whitelist_groups(self) -> list[str]:
        """白名单群聊列表。

        返回:
            群聊 ID 列表，仅在白名单模式时生效
        """
        groups = self._read(
            ("safety", "whitelist_groups"), "whitelist_groups", default=[]
        )
        if isinstance(groups, list):
            return [str(g).strip() for g in groups if str(g).strip()]
        return []

    def is_group_blocked(self, group_id: str | None) -> bool:
        """检查群聊是否被屏蔽。

        根据访问控制模式决定检查逻辑：
        - none: 所有群组都可用
        - blacklist: 在黑名单中的群组被屏蔽
        - whitelist: 不在白名单中的群组被屏蔽

        参数:
            group_id: 群聊 ID

        返回:
            如果群聊被屏蔽返回 True，否则返回 False
        """
        # 仅当 group_id 为 None 时视为"无群组"，直接返回不屏蔽
        # 其他 falsy 值（例如 "", 0 等）仍会参与访问控制检查
        if group_id is None:
            return False

        mode = self.access_control_mode
        gid = str(group_id)

        if mode == "none":
            # 不启用黑白名单，所有群组都可用
            return False

        if mode == "whitelist":
            # 白名单模式：不在白名单中的群组被屏蔽
            whitelist = self.whitelist_groups
            if not whitelist:
                # 白名单为空时，所有群组都可用（兼容旧配置）
                return False
            return gid not in whitelist

        # 黑名单模式（默认）：在黑名单中的群组被屏蔽
        return gid in self.blocked_groups

    @property
    def blocked_users(self) -> list[str]:
        """被屏蔽的用户列表（黑名单）。

        返回:
            用户 ID 列表，这些用户将禁止使用插件功能
        """
        users = self._read(("safety", "blocked_users"), "blocked_users", default=[])
        if isinstance(users, list):
            return [str(u).strip() for u in users if str(u).strip()]
        return []

    @property
    def whitelist_users(self) -> list[str]:
        """白名单用户列表。

        返回:
            用户 ID 列表，仅在白名单模式时生效
        """
        users = self._read(
            ("safety", "whitelist_users"), "whitelist_users", default=[]
        )
        if isinstance(users, list):
            return [str(u).strip() for u in users if str(u).strip()]
        return []

    def is_user_blocked(self, user_id: str | None) -> bool:
        """检查用户是否被屏蔽。

        用户级黑白名单独立于群组级，优先级如下：
        1. 如果用户在 blocked_users 中，直接屏蔽（黑名单优先）
        2. 如果 whitelist_users 不为空且用户不在其中，屏蔽（白名单模式）
        3. 其他情况不屏蔽

        参数:
            user_id: 用户 ID

        返回:
            如果用户被屏蔽返回 True，否则返回 False
        """
        if user_id is None:
            return False

        uid = str(user_id)

        # 1. 检查用户黑名单（优先级最高）
        if uid in self.blocked_users:
            return True

        # 2. 检查用户白名单（如果配置了白名单）
        whitelist = self.whitelist_users
        if whitelist and uid not in whitelist:
            # 白名单不为空，且用户不在白名单中
            return True

        return False

    def check_access(
        self, user_id: str | None, group_id: str | None
    ) -> tuple[bool, str]:
        """统一检查用户和群组的访问权限（全局）。

        同时检查用户级和群组级的访问控制，返回是否允许访问及原因。
        用户白名单具有最高优先级，白名单用户不受群组级限制影响。

        参数:
            user_id: 用户 ID
            group_id: 群组 ID（私聊时为 None）

        返回:
            (是否被屏蔽, 屏蔽原因)
            - (False, ""): 允许访问
            - (True, "用户被禁用"): 用户在黑名单中
            - (True, "用户不在白名单中"): 配置了用户白名单但用户不在其中
            - (True, "群组被禁用"): 群组在黑名单中
            - (True, "群组不在白名单中"): 白名单模式下群组不在白名单中
        """
        # 从 core 获取 access_control 并使用全局检查
        from ..services import AccessControlManager
        return AccessControlManager.check_global_access(
            self, user_id, group_id, self.access_control_mode
        )

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
