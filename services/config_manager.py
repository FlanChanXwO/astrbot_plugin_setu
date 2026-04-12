"""配置管理服务，用于持久化黑白名单等配置到文件。"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

from astrbot.api import logger

if TYPE_CHECKING:
    from astrbot.core import AstrBotConfig


class ConfigManager:
    """配置管理器，负责读写插件配置文件。

    同时管理两个配置存储位置：
    1. 插件数据目录的 config.json - 运行时快速访问
    2. AstrBot 主配置 - 供 webui 显示和编辑
    """

    SAFETY_LIST_KEYS = (
        "setu_blocked_users",
        "setu_whitelist_users",
        "setu_blocked_groups",
        "setu_whitelist_groups",
        "fortune_blocked_users",
        "fortune_whitelist_users",
        "fortune_blocked_groups",
        "fortune_whitelist_groups",
    )
    SAFETY_MODE_KEYS = (
        "setu_user_access_control_mode",
        "setu_group_access_control_mode",
        "fortune_user_access_control_mode",
        "fortune_group_access_control_mode",
    )
    LEGACY_MODE_TO_NEW = {
        "setu_access_control_mode": (
            "setu_user_access_control_mode",
            "setu_group_access_control_mode",
        ),
        "fortune_access_control_mode": (
            "fortune_user_access_control_mode",
            "fortune_group_access_control_mode",
        ),
    }

    def __init__(
        self, plugin_data_dir: Path, astrbot_config: AstrBotConfig | None = None
    ):
        """初始化配置管理器。

        参数:
            plugin_data_dir: 插件数据目录
            astrbot_config: AstrBot 配置对象，用于同步到 webui
        """
        self._data_dir = plugin_data_dir
        self._config_file = plugin_data_dir / "config.json"
        self._cache: dict[str, Any] = {}
        self._astrbot_config = astrbot_config
        self._main_config_cache: dict[str, Any] | None = None
        self._main_config_cache_mtime: float | None = None
        self._main_config_cache_path: Path | None = None
        self._main_config_cache_lock = threading.Lock()

    async def initialize(self) -> None:
        """初始化，加载现有配置。"""
        self._load_config()
        # 启动时优先吸收 WebUI 最新值，避免本地缓存反向覆盖。
        imported = self._sync_from_astrbot_config()
        if not imported:
            self._sync_to_astrbot_config()

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
            # 同时同步到 AstrBot 配置供 webui 显示
            self._sync_to_astrbot_config()
            return True
        except (OSError, TypeError) as e:
            logger.error("Failed to save config file: %s", e)
            return False

    def _invalidate_main_config_cache(self) -> None:
        """失效主配置缓存。"""
        with self._main_config_cache_lock:
            self._main_config_cache = None
            self._main_config_cache_mtime = None
            self._main_config_cache_path = None

    def _iter_main_config_candidates(self) -> list[Path]:
        """构造可能的主配置文件路径候选。"""
        config_file_name = "astrbot_plugin_setu_config.json"
        candidates: list[Path] = []
        # 常见结构：data/plugins/<plugin>
        candidates.append(self._data_dir.parent.parent / "config" / config_file_name)
        # 兜底：遍历父目录尝试 data/config 路径
        candidates.extend(
            parent / "data" / "config" / config_file_name
            for parent in self._data_dir.parents
        )
        return candidates

    def _load_main_config_with_cache(self) -> dict[str, Any] | None:
        """加载主配置并基于 mtime 进行缓存。"""
        config_path: Path | None = None
        for candidate in self._iter_main_config_candidates():
            if candidate.is_file():
                config_path = candidate
                break

        if config_path is None:
            return None

        try:
            mtime = config_path.stat().st_mtime
        except OSError:
            return None

        with self._main_config_cache_lock:
            if (
                self._main_config_cache_path == config_path
                and self._main_config_cache_mtime == mtime
                and self._main_config_cache is not None
            ):
                return self._main_config_cache

            try:
                # AstrBot 主配置在 Windows 上可能带 BOM，使用 utf-8-sig 兼容读取。
                with open(config_path, encoding="utf-8-sig") as f:
                    data = json.load(f)
            except (OSError, json.JSONDecodeError) as e:
                logger.warning("Failed to load main config %s: %s", config_path, e)
                return None

            if not isinstance(data, dict):
                return None

            self._main_config_cache = data
            self._main_config_cache_mtime = mtime
            self._main_config_cache_path = config_path
            return data

    def _get_safety_section(self) -> dict[str, Any] | None:
        """从主配置中获取 safety 配置段（带缓存）。"""
        main_cfg = self._load_main_config_with_cache()
        if not main_cfg:
            return None
        safety = main_cfg.get("safety")
        if not isinstance(safety, dict):
            return None
        return safety

    def _get_safety_value_from_file(self, key: str, default: Any = None) -> Any:
        """从主配置文件读取单个 safety 配置值（带缓存）。"""
        safety_config = self._get_safety_section()
        if safety_config is None:
            return default

        # 兼容旧键：请求新键时可回退到旧键。
        if key not in safety_config:
            if (
                key
                in (
                    "setu_user_access_control_mode",
                    "setu_group_access_control_mode",
                )
                and "setu_access_control_mode" in safety_config
            ):
                value = safety_config["setu_access_control_mode"]
            elif (
                key
                in (
                    "fortune_user_access_control_mode",
                    "fortune_group_access_control_mode",
                )
                and "fortune_access_control_mode" in safety_config
            ):
                value = safety_config["fortune_access_control_mode"]
            else:
                return default
        else:
            value = safety_config[key]

        if key in self.SAFETY_LIST_KEYS:
            if not isinstance(value, list):
                return []
            return [str(v).strip() for v in value if str(v).strip()]

        if key in self.SAFETY_MODE_KEYS:
            return value if value in {"none", "blacklist", "whitelist"} else default

        return value

    def _sync_to_astrbot_config(self) -> None:
        """将本地配置同步到 AstrBot 配置供 webui 显示。

        配置在 schema 中定义于顶层 safety 下，webui 期望从该路径读取。
        """
        if self._astrbot_config is None:
            return

        try:
            updated = False

            # 确保顶层 safety 存在（webui 配置路径）
            if "safety" not in self._astrbot_config:
                self._astrbot_config["safety"] = {}
                updated = True

            safety_config = self._astrbot_config["safety"]
            if not isinstance(safety_config, dict):
                safety_config = {}
                self._astrbot_config["safety"] = safety_config
                updated = True

            # 仅同步缓存中明确存在的键，避免启动时空缓存覆盖 WebUI。
            for key in self.SAFETY_LIST_KEYS:
                if key not in self._cache:
                    continue
                value = self._cache.get(key)
                if not isinstance(value, list):
                    value = []
                if safety_config.get(key) != value:
                    safety_config[key] = value
                    updated = True

            for key in self.SAFETY_MODE_KEYS:
                if key not in self._cache:
                    continue
                value = self._cache.get(key)
                if value is not None and safety_config.get(key) != value:
                    safety_config[key] = value
                    updated = True

            if (
                updated
                and hasattr(self._astrbot_config, "save_config")
                and callable(getattr(self._astrbot_config, "save_config"))
            ):
                self._astrbot_config.save_config()
                self._invalidate_main_config_cache()
                logger.debug(
                    "[config_manager] Synced config to AstrBot safety (top-level) and saved"
                )

        except Exception as e:
            logger.debug("[config_manager] Failed to sync to AstrBot config: %s", e)

    def _sync_from_astrbot_config(self) -> bool:
        """从 AstrBot 配置同步到本地（webui 修改后）。

        从顶层 safety 同步黑白名单列表和访问控制模式到本地缓存。
        返回是否成功导入了任意安全配置键。
        """
        if self._astrbot_config is None:
            return False

        try:
            imported = False
            updated = False

            safety_config = self._astrbot_config.get("safety", {})
            if not isinstance(safety_config, dict):
                return False

            for key in self.SAFETY_LIST_KEYS:
                if key not in safety_config:
                    continue
                imported = True
                value = safety_config.get(key)
                if not isinstance(value, list):
                    value = []
                value = [str(v).strip() for v in value if str(v).strip()]
                if self._cache.get(key) != value:
                    self._cache[key] = value
                    updated = True

            valid_modes = {"none", "blacklist", "whitelist"}
            # 优先读取新键
            for key in self.SAFETY_MODE_KEYS:
                if key not in safety_config:
                    continue
                imported = True
                value = safety_config.get(key)
                if value not in valid_modes:
                    continue
                if self._cache.get(key) != value:
                    self._cache[key] = value
                    updated = True

            # 若新键缺失，尝试旧键映射。
            for legacy_key, mapped_keys in self.LEGACY_MODE_TO_NEW.items():
                if legacy_key not in safety_config:
                    continue
                imported = True
                value = safety_config.get(legacy_key)
                if value not in valid_modes:
                    continue
                for key in mapped_keys:
                    if key not in safety_config and self._cache.get(key) != value:
                        self._cache[key] = value
                        updated = True

            if updated:
                self._data_dir.mkdir(parents=True, exist_ok=True)
                with open(self._config_file, "w", encoding="utf-8") as f:
                    json.dump(self._cache, f, ensure_ascii=False, indent=2)
                logger.debug(
                    "[config_manager] Synced config from AstrBot/webui safety (top-level)"
                )

            return imported

        except Exception as e:
            logger.debug("[config_manager] Failed to sync from AstrBot config: %s", e)
            return False

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值。"""
        if key in self.SAFETY_LIST_KEYS or key in self.SAFETY_MODE_KEYS:
            file_value = self._get_safety_value_from_file(key, None)
            if file_value is not None:
                return file_value

            if self._astrbot_config is not None:
                try:
                    safety_config = self._astrbot_config.get("safety", {})
                    if isinstance(safety_config, dict) and key in safety_config:
                        return safety_config[key]
                except Exception:
                    pass

            if key in self._cache:
                return self._cache[key]
            return default

        if key in self._cache:
            return self._cache[key]

        return default

    def _get_access_control_mode_from_file(self, key: str, default: Any = None) -> Any:
        """兼容方法：访问控制模式读取统一复用 safety 读取路径。"""
        return self._get_safety_value_from_file(key, default)

    def set(self, key: str, value: Any) -> bool:
        """设置配置值。"""
        self._cache[key] = value
        return self._save_config()

    def get_list(self, key: str) -> list[str]:
        """获取列表类型的配置值。"""
        value = self.get(key, [])
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
        return []

    def add_to_list(self, key: str, item: str) -> bool:
        """添加项目到列表。"""
        current = self.get_list(key)
        item_str = str(item).strip()

        if not item_str:
            return False
        if item_str in current:
            return True

        current.append(item_str)
        self._cache[key] = current
        return self._save_config()

    def remove_from_list(self, key: str, item: str) -> bool:
        """从列表中移除项目。"""
        current = self.get_list(key)
        item_str = str(item).strip()

        if item_str not in current:
            return True

        current.remove(item_str)
        self._cache[key] = current
        return self._save_config()

    def is_in_list(self, key: str, item: str) -> bool:
        """检查项目是否在列表中。"""
        current = self.get_list(key)
        return str(item).strip() in current


class AccessControlManager:
    """访问控制管理器，封装黑白名单管理逻辑。"""

    KEY_SETU_ACCESS_CONTROL_MODE = "setu_access_control_mode"
    KEY_SETU_BLOCKED_USERS = "setu_blocked_users"
    KEY_SETU_WHITELIST_USERS = "setu_whitelist_users"
    KEY_SETU_BLOCKED_GROUPS = "setu_blocked_groups"
    KEY_SETU_WHITELIST_GROUPS = "setu_whitelist_groups"

    KEY_FORTUNE_ACCESS_CONTROL_MODE = "fortune_access_control_mode"
    KEY_FORTUNE_BLOCKED_USERS = "fortune_blocked_users"
    KEY_FORTUNE_WHITELIST_USERS = "fortune_whitelist_users"
    KEY_FORTUNE_BLOCKED_GROUPS = "fortune_blocked_groups"
    KEY_FORTUNE_WHITELIST_GROUPS = "fortune_whitelist_groups"

    def __init__(self, config_manager: ConfigManager):
        self._cfg = config_manager

    def add_setu_blocked_user(self, user_id: str) -> bool:
        user_id = str(user_id).strip()
        if not user_id:
            return False
        # 避免同一用户同时存在于黑白名单。
        self._cfg.remove_from_list(self.KEY_SETU_WHITELIST_USERS, user_id)
        return self._cfg.add_to_list(self.KEY_SETU_BLOCKED_USERS, user_id)

    def remove_setu_blocked_user(self, user_id: str) -> bool:
        return self._cfg.remove_from_list(self.KEY_SETU_BLOCKED_USERS, user_id)

    def is_setu_user_blocked(self, user_id: str) -> bool:
        return self._cfg.is_in_list(self.KEY_SETU_BLOCKED_USERS, user_id)

    def get_setu_blocked_users(self) -> list[str]:
        return self._cfg.get_list(self.KEY_SETU_BLOCKED_USERS)

    def add_setu_whitelist_user(self, user_id: str) -> bool:
        user_id = str(user_id).strip()
        if not user_id:
            return False
        # 被信任时自动从黑名单移除。
        self._cfg.remove_from_list(self.KEY_SETU_BLOCKED_USERS, user_id)
        return self._cfg.add_to_list(self.KEY_SETU_WHITELIST_USERS, user_id)

    def remove_setu_whitelist_user(self, user_id: str) -> bool:
        return self._cfg.remove_from_list(self.KEY_SETU_WHITELIST_USERS, user_id)

    def is_setu_user_whitelisted(self, user_id: str) -> bool:
        return self._cfg.is_in_list(self.KEY_SETU_WHITELIST_USERS, user_id)

    def get_setu_whitelist_users(self) -> list[str]:
        return self._cfg.get_list(self.KEY_SETU_WHITELIST_USERS)

    def add_setu_blocked_group(self, group_id: str) -> bool:
        return self._cfg.add_to_list(self.KEY_SETU_BLOCKED_GROUPS, group_id)

    def remove_setu_blocked_group(self, group_id: str) -> bool:
        return self._cfg.remove_from_list(self.KEY_SETU_BLOCKED_GROUPS, group_id)

    def is_setu_group_blocked(self, group_id: str) -> bool:
        return self._cfg.is_in_list(self.KEY_SETU_BLOCKED_GROUPS, group_id)

    def get_setu_blocked_groups(self) -> list[str]:
        return self._cfg.get_list(self.KEY_SETU_BLOCKED_GROUPS)

    def add_setu_whitelist_group(self, group_id: str) -> bool:
        return self._cfg.add_to_list(self.KEY_SETU_WHITELIST_GROUPS, group_id)

    def remove_setu_whitelist_group(self, group_id: str) -> bool:
        return self._cfg.remove_from_list(self.KEY_SETU_WHITELIST_GROUPS, group_id)

    def is_setu_group_whitelisted(self, group_id: str) -> bool:
        return self._cfg.is_in_list(self.KEY_SETU_WHITELIST_GROUPS, group_id)

    def get_setu_whitelist_groups(self) -> list[str]:
        return self._cfg.get_list(self.KEY_SETU_WHITELIST_GROUPS)

    def add_fortune_blocked_user(self, user_id: str) -> bool:
        user_id = str(user_id).strip()
        if not user_id:
            return False
        self._cfg.remove_from_list(self.KEY_FORTUNE_WHITELIST_USERS, user_id)
        return self._cfg.add_to_list(self.KEY_FORTUNE_BLOCKED_USERS, user_id)

    def remove_fortune_blocked_user(self, user_id: str) -> bool:
        return self._cfg.remove_from_list(self.KEY_FORTUNE_BLOCKED_USERS, user_id)

    def is_fortune_user_blocked(self, user_id: str) -> bool:
        return self._cfg.is_in_list(self.KEY_FORTUNE_BLOCKED_USERS, user_id)

    def get_fortune_blocked_users(self) -> list[str]:
        return self._cfg.get_list(self.KEY_FORTUNE_BLOCKED_USERS)

    def add_fortune_whitelist_user(self, user_id: str) -> bool:
        user_id = str(user_id).strip()
        if not user_id:
            return False
        self._cfg.remove_from_list(self.KEY_FORTUNE_BLOCKED_USERS, user_id)
        return self._cfg.add_to_list(self.KEY_FORTUNE_WHITELIST_USERS, user_id)

    def remove_fortune_whitelist_user(self, user_id: str) -> bool:
        return self._cfg.remove_from_list(self.KEY_FORTUNE_WHITELIST_USERS, user_id)

    def is_fortune_user_whitelisted(self, user_id: str) -> bool:
        return self._cfg.is_in_list(self.KEY_FORTUNE_WHITELIST_USERS, user_id)

    def get_fortune_whitelist_users(self) -> list[str]:
        return self._cfg.get_list(self.KEY_FORTUNE_WHITELIST_USERS)

    def add_fortune_blocked_group(self, group_id: str) -> bool:
        return self._cfg.add_to_list(self.KEY_FORTUNE_BLOCKED_GROUPS, group_id)

    def remove_fortune_blocked_group(self, group_id: str) -> bool:
        return self._cfg.remove_from_list(self.KEY_FORTUNE_BLOCKED_GROUPS, group_id)

    def is_fortune_group_blocked(self, group_id: str) -> bool:
        return self._cfg.is_in_list(self.KEY_FORTUNE_BLOCKED_GROUPS, group_id)

    def get_fortune_blocked_groups(self) -> list[str]:
        return self._cfg.get_list(self.KEY_FORTUNE_BLOCKED_GROUPS)

    def add_fortune_whitelist_group(self, group_id: str) -> bool:
        return self._cfg.add_to_list(self.KEY_FORTUNE_WHITELIST_GROUPS, group_id)

    def remove_fortune_whitelist_group(self, group_id: str) -> bool:
        return self._cfg.remove_from_list(self.KEY_FORTUNE_WHITELIST_GROUPS, group_id)

    def is_fortune_group_whitelisted(self, group_id: str) -> bool:
        return self._cfg.is_in_list(self.KEY_FORTUNE_WHITELIST_GROUPS, group_id)

    def get_fortune_whitelist_groups(self) -> list[str]:
        return self._cfg.get_list(self.KEY_FORTUNE_WHITELIST_GROUPS)

    def check_setu_access(
        self,
        user_id: str | None,
        group_id: str | None,
        user_access_control_mode: str = "none",
        group_access_control_mode: str = "none",
    ) -> tuple[bool, str]:
        """检查色图功能访问权限。

        参数:
            user_id: 用户 ID
            group_id: 群组 ID
            user_access_control_mode: 用户访问控制模式 (none/blacklist/whitelist)
            group_access_control_mode: 群组访问控制模式 (none/blacklist/whitelist)

        返回:
            (是否被屏蔽, 屏蔽原因)
        """
        if user_id is not None:
            uid = str(user_id)
            if user_access_control_mode == "blacklist":
                is_blocked = self.is_setu_user_blocked(uid)
                blocked_users = self.get_setu_blocked_users()
                logger.debug(
                    "[check_setu_access] User blacklist mode: user=%s, blocked=%s, blocked_users=%s",
                    uid,
                    is_blocked,
                    blocked_users,
                )
                if is_blocked:
                    return True, "用户被禁用"
            elif (
                user_access_control_mode == "whitelist"
                and not self.is_setu_user_whitelisted(uid)
            ):
                return True, "用户不在白名单中"

        if group_id is not None:
            gid = str(group_id)
            if group_access_control_mode == "blacklist" and self.is_setu_group_blocked(
                gid
            ):
                return True, "群组被禁用"
            if (
                group_access_control_mode == "whitelist"
                and not self.is_setu_group_whitelisted(gid)
            ):
                return True, "群组不在白名单中"

        return False, ""

    def check_fortune_access(
        self,
        user_id: str | None,
        group_id: str | None,
        user_access_control_mode: str = "none",
        group_access_control_mode: str = "none",
    ) -> tuple[bool, str]:
        """检查运势功能访问权限。

        参数:
            user_id: 用户 ID
            group_id: 群组 ID
            user_access_control_mode: 用户访问控制模式 (none/blacklist/whitelist)
            group_access_control_mode: 群组访问控制模式 (none/blacklist/whitelist)

        返回:
            (是否被屏蔽, 屏蔽原因)
        """
        if user_id is not None:
            uid = str(user_id)
            if user_access_control_mode == "blacklist" and self.is_fortune_user_blocked(
                uid
            ):
                return True, "用户被禁用"
            if (
                user_access_control_mode == "whitelist"
                and not self.is_fortune_user_whitelisted(uid)
            ):
                return True, "用户不在白名单中"

        if group_id is not None:
            gid = str(group_id)
            if (
                group_access_control_mode == "blacklist"
                and self.is_fortune_group_blocked(gid)
            ):
                return True, "群组被禁用"
            if (
                group_access_control_mode == "whitelist"
                and not self.is_fortune_group_whitelisted(gid)
            ):
                return True, "群组不在白名单中"

        return False, ""

    def get_all_lists(self) -> dict[str, list[str]]:
        """获取所有黑白名单列表。

        返回:
            包含所有列表的字典
        """
        return {
            "setu_blocked_users": self.get_setu_blocked_users(),
            "setu_whitelist_users": self.get_setu_whitelist_users(),
            "setu_blocked_groups": self.get_setu_blocked_groups(),
            "setu_whitelist_groups": self.get_setu_whitelist_groups(),
            "fortune_blocked_users": self.get_fortune_blocked_users(),
            "fortune_whitelist_users": self.get_fortune_whitelist_users(),
            "fortune_blocked_groups": self.get_fortune_blocked_groups(),
            "fortune_whitelist_groups": self.get_fortune_whitelist_groups(),
        }
