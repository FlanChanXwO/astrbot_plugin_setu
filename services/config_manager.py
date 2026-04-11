"""配置管理服务，用于持久化黑白名单等配置到文件。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from astrbot.api import logger


class ConfigManager:
    """配置管理器，负责读写插件配置文件。"""

    def __init__(self, plugin_data_dir: Path):
        """初始化配置管理器。

        参数:
            plugin_data_dir: 插件数据目录
        """
        self._data_dir = plugin_data_dir
        self._config_file = plugin_data_dir / "config.json"
        self._cache: dict[str, Any] = {}

    async def initialize(self) -> None:
        """初始化，加载现有配置。"""
        self._load_config()

    def _load_config(self) -> None:
        """从文件加载配置。"""
        if not self._config_file.exists():
            self._cache = {}
            return

        try:
            with open(self._config_file, encoding="utf-8") as f:
                self._cache = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load config file: %s", e)
            self._cache = {}

    def _save_config(self) -> bool:
        """保存配置到文件。

        返回:
            是否保存成功
        """
        try:
            self._data_dir.mkdir(parents=True, exist_ok=True)
            with open(self._config_file, "w", encoding="utf-8") as f:
                json.dump(self._cache, f, ensure_ascii=False, indent=2)
            return True
        except (OSError, TypeError) as e:
            logger.error("Failed to save config file: %s", e)
            return False

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值。

        参数:
            key: 配置键
            default: 默认值

        返回:
            配置值或默认值
        """
        return self._cache.get(key, default)

    def set(self, key: str, value: Any) -> bool:
        """设置配置值。

        参数:
            key: 配置键
            value: 配置值

        返回:
            是否保存成功
        """
        self._cache[key] = value
        return self._save_config()

    def get_list(self, key: str) -> list[str]:
        """获取列表类型的配置值。

        参数:
            key: 配置键

        返回:
            字符串列表
        """
        value = self._cache.get(key, [])
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
        return []

    def add_to_list(self, key: str, item: str) -> bool:
        """添加项目到列表。

        参数:
            key: 配置键
            item: 要添加的项目

        返回:
            是否保存成功
        """
        current = self.get_list(key)
        item_str = str(item).strip()

        if not item_str:
            return False

        if item_str in current:
            return True  # 已存在，视为成功

        current.append(item_str)
        self._cache[key] = current
        return self._save_config()

    def remove_from_list(self, key: str, item: str) -> bool:
        """从列表中移除项目。

        参数:
            key: 配置键
            item: 要移除的项目

        返回:
            是否保存成功
        """
        current = self.get_list(key)
        item_str = str(item).strip()

        if item_str not in current:
            return True  # 不存在，视为成功

        current.remove(item_str)
        self._cache[key] = current
        return self._save_config()

    def is_in_list(self, key: str, item: str) -> bool:
        """检查项目是否在列表中。

        参数:
            key: 配置键
            item: 要检查的项目

        返回:
            是否存在
        """
        current = self.get_list(key)
        return str(item).strip() in current


class AccessControlManager:
    """访问控制管理器，封装黑白名单管理逻辑。"""

    # 配置键名常量 - 全局
    KEY_BLOCKED_USERS = "blocked_users"
    KEY_WHITELIST_USERS = "whitelist_users"
    KEY_BLOCKED_GROUPS = "blocked_groups"
    KEY_WHITELIST_GROUPS = "whitelist_groups"

    # 配置键名常量 - Fortune运势独立黑名单
    KEY_FORTUNE_BLOCKED_GROUPS = "fortune_blocked_groups"

    def __init__(self, config_manager: ConfigManager):
        """初始化访问控制管理器。

        参数:
            config_manager: 配置管理器实例
        """
        self._cfg = config_manager

    # ============ 便捷方法 - 全局 ============

    def add_blocked_user(self, user_id: str) -> bool:
        """添加用户到黑名单。"""
        return self._cfg.add_to_list(self.KEY_BLOCKED_USERS, user_id)

    def remove_blocked_user(self, user_id: str) -> bool:
        """从黑名单移除用户。"""
        return self._cfg.remove_from_list(self.KEY_BLOCKED_USERS, user_id)

    def is_user_blocked(self, user_id: str) -> bool:
        """检查用户是否在黑名单中。"""
        return self._cfg.is_in_list(self.KEY_BLOCKED_USERS, user_id)

    def get_blocked_users(self) -> list[str]:
        """获取黑名单用户列表。"""
        return self._cfg.get_list(self.KEY_BLOCKED_USERS)

    def add_whitelist_user(self, user_id: str) -> bool:
        """添加用户到白名单。"""
        return self._cfg.add_to_list(self.KEY_WHITELIST_USERS, user_id)

    def remove_whitelist_user(self, user_id: str) -> bool:
        """从白名单移除用户。"""
        return self._cfg.remove_from_list(self.KEY_WHITELIST_USERS, user_id)

    def is_user_whitelisted(self, user_id: str) -> bool:
        """检查用户是否在白名单中。"""
        return self._cfg.is_in_list(self.KEY_WHITELIST_USERS, user_id)

    def get_whitelist_users(self) -> list[str]:
        """获取白名单用户列表。"""
        return self._cfg.get_list(self.KEY_WHITELIST_USERS)

    def add_blocked_group(self, group_id: str) -> bool:
        """添加群组到黑名单。"""
        return self._cfg.add_to_list(self.KEY_BLOCKED_GROUPS, group_id)

    def remove_blocked_group(self, group_id: str) -> bool:
        """从黑名单移除群组。"""
        return self._cfg.remove_from_list(self.KEY_BLOCKED_GROUPS, group_id)

    def is_group_blocked(self, group_id: str) -> bool:
        """检查群组是否在黑名单中。"""
        return self._cfg.is_in_list(self.KEY_BLOCKED_GROUPS, group_id)

    def get_blocked_groups(self) -> list[str]:
        """获取黑名单群组列表。"""
        return self._cfg.get_list(self.KEY_BLOCKED_GROUPS)

    def add_whitelist_group(self, group_id: str) -> bool:
        """添加群组到白名单。"""
        return self._cfg.add_to_list(self.KEY_WHITELIST_GROUPS, group_id)

    def remove_whitelist_group(self, group_id: str) -> bool:
        """从白名单移除群组。"""
        return self._cfg.remove_from_list(self.KEY_WHITELIST_GROUPS, group_id)

    def is_group_whitelisted(self, group_id: str) -> bool:
        """检查群组是否在白名单中。"""
        return self._cfg.is_in_list(self.KEY_WHITELIST_GROUPS, group_id)

    def get_whitelist_groups(self) -> list[str]:
        """获取白名单群组列表。"""
        return self._cfg.get_list(self.KEY_WHITELIST_GROUPS)

    # ============ 便捷方法 - Fortune运势独立黑名单 ============

    def add_fortune_blocked_group(self, group_id: str) -> bool:
        """添加群组到运势黑名单。"""
        return self._cfg.add_to_list(self.KEY_FORTUNE_BLOCKED_GROUPS, group_id)

    def remove_fortune_blocked_group(self, group_id: str) -> bool:
        """从运势黑名单移除群组。"""
        return self._cfg.remove_from_list(self.KEY_FORTUNE_BLOCKED_GROUPS, group_id)

    def is_fortune_group_blocked(self, group_id: str) -> bool:
        """检查群组是否在运势黑名单中。"""
        return self._cfg.is_in_list(self.KEY_FORTUNE_BLOCKED_GROUPS, group_id)

    def get_fortune_blocked_groups(self) -> list[str]:
        """获取运势黑名单群组列表。"""
        return self._cfg.get_list(self.KEY_FORTUNE_BLOCKED_GROUPS)

    # ============ 访问检查 ============

    def check_global_access(
        self,
        user_id: str | None,
        group_id: str | None,
        access_control_mode: str = "blacklist",
    ) -> tuple[bool, str]:
        """检查全局访问权限。

        参数:
            user_id: 用户 ID
            group_id: 群组 ID
            access_control_mode: 访问控制模式

        返回:
            (是否被屏蔽, 屏蔽原因)
        """
        # 检查全局用户黑白名单
        if user_id is not None:
            uid = str(user_id)

            if self.is_user_blocked(uid):
                return True, "用户被禁用"

            global_whitelist = self.get_whitelist_users()
            if global_whitelist:
                if uid in global_whitelist:
                    return False, ""  # 全局白名单用户
                return True, "用户不在白名单中"

        # 检查全局群组黑白名单
        if group_id is not None:
            gid = str(group_id)

            if self.is_group_blocked(gid):
                return True, "群组被禁用"

            if access_control_mode == "whitelist":
                group_whitelist = self.get_whitelist_groups()
                if group_whitelist and gid not in group_whitelist:
                    return True, "群组不在白名单中"

        return False, ""

    def get_all_lists(self) -> dict[str, list[str]]:
        """获取所有黑白名单列表。

        返回:
            包含所有列表的字典
        """
        return {
            "blocked_users": self.get_blocked_users(),
            "whitelist_users": self.get_whitelist_users(),
            "blocked_groups": self.get_blocked_groups(),
            "whitelist_groups": self.get_whitelist_groups(),
            "fortune_blocked_groups": self.get_fortune_blocked_groups(),
        }