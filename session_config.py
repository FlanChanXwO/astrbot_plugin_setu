"""会话级别配置管理器。

提供会话级别的配置覆盖功能，允许管理员在特定会话中设置不同的内容模式。
配置存储在 AstrBotConfig 中，可在 WebUI 中管理。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from astrbot.api import logger

from .session_config_base import SessionConfigBase

if TYPE_CHECKING:
    from astrbot.core import AstrBotConfig


class SessionConfigManager(SessionConfigBase):
    """会话级别配置管理器。

    管理每个会话（群聊/私聊）的独立配置，支持内容模式覆盖。
    配置存储在 AstrBotConfig 的 session_configs 字段中，可在 WebUI 中管理。

    Attributes:
        _config: AstrBotConfig 配置对象
        _data_dir: 插件数据目录（用于迁移）
        _lock: 异步锁，防止并发读写不一致
    """

    # 允许会话覆盖的配置项
    ALLOWED_KEYS = {"content_mode", "r18_docx_mode", "auto_revoke_r18", "send_mode"}

    # 有效的内容模式值
    VALID_CONTENT_MODES = {"sfw", "r18", "mix"}

    # 有效的发送模式值
    VALID_SEND_MODES = {"image", "forward", "auto"}

    def __init__(self, config: AstrBotConfig, data_dir: Path | None = None):
        """初始化会话配置管理器。

        参数:
            config: AstrBotConfig 配置对象
            data_dir: 插件数据目录（用于迁移旧配置）
        """
        super().__init__(config, config_key="session_configs")
        self._data_dir = data_dir
        self._migrated = False

    async def initialize(self) -> None:
        """初始化配置，迁移旧配置文件到新格式。"""
        if self._data_dir and not self._migrated:
            await self._migrate_old_config()
            self._migrated = True
        logger.info("[session_config] SessionConfigManager initialized")

    async def _migrate_old_config(self) -> None:
        """迁移旧位置的配置文件到 AstrBotConfig。"""
        old_config_file = self._data_dir / "setu" / "setu_session_config.json"
        if not old_config_file.exists():
            # 检查旧的位置
            old_config_file = self._data_dir / "session_config.json"

        if not old_config_file.exists():
            return

        try:
            content = await asyncio.to_thread(
                old_config_file.read_text, encoding="utf-8"
            )
            old_data = json.loads(content)
            sessions = old_data.get("sessions", {})

            if not sessions:
                return

            # 转换格式到新的 template_list 格式
            new_configs = self._get_configs()

            for session_key, session_data in sessions.items():
                parsed = self._parse_session_key(session_key)
                if not parsed:
                    continue

                session_type, session_id = parsed
                is_group = session_type == "group"

                # 构建新的配置项
                new_item = {
                    "session_id": session_id,
                    "session_type": "group" if is_group else "private",
                }

                # 迁移各配置项
                if "content_mode" in session_data:
                    new_item["content_mode"] = session_data["content_mode"]
                if "r18_docx_mode" in session_data:
                    new_item["r18_docx_mode"] = (
                        "enabled" if session_data["r18_docx_mode"] else "disabled"
                    )
                if "auto_revoke_r18" in session_data:
                    new_item["auto_revoke_r18"] = (
                        "enabled" if session_data["auto_revoke_r18"] else "disabled"
                    )
                if "send_mode" in session_data:
                    new_item["send_mode"] = session_data["send_mode"]

                self.merge_session_item(new_configs, new_item)

            # 保存迁移后的配置
            self._save_configs(new_configs)

            # 删除旧配置文件
            await asyncio.to_thread(old_config_file.unlink)
            logger.info(
                "[session_config] Migrated old config to AstrBotConfig, %d sessions",
                len(new_configs),
            )
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("[session_config] Failed to migrate old config: %s", exc)

    def _get_session_config(self, session_id: str, is_group: bool) -> dict | None:
        """获取会话配置项。"""
        return self._find_session_config(session_id, is_group)

    def _get_session_key(self, session_id: str, is_group: bool) -> str:
        """生成会话键。"""
        prefix = "group" if is_group else "private"
        return f"{prefix}:{session_id}"

    async def set_config(
        self, session_id: str, is_group: bool, key: str, value: Any
    ) -> bool:
        """设置会话配置项。

        参数:
            session_id: 会话ID
            is_group: 是否为群聊
            key: 配置键
            value: 配置值

        返回:
            设置成功返回 True，否则返回 False
        """
        if key not in self.ALLOWED_KEYS:
            logger.warning("[session_config] Key %s is not allowed", key)
            return False

        # 验证 content_mode 值
        if key == "content_mode" and value not in self.VALID_CONTENT_MODES:
            logger.warning("[session_config] Invalid content_mode: %s", value)
            return False

        # 验证 send_mode 值
        if key == "send_mode" and value not in self.VALID_SEND_MODES:
            logger.warning("[session_config] Invalid send_mode: %s", value)
            return False

        async with self._lock:
            session_type = "group" if is_group else "private"
            configs = self._get_configs()

            # 查找现有配置
            existing_idx = self._find_session_index(configs, session_id, is_group)

            # 根据配置项类型设置值
            config_value = value
            if key == "r18_docx_mode":
                config_value = "enabled" if value else "disabled"
            elif key == "auto_revoke_r18":
                config_value = "enabled" if value else "disabled"

            if existing_idx is not None:
                # 更新现有配置
                configs[existing_idx][key] = config_value
            else:
                # 创建新配置
                new_item = {
                    "session_id": session_id,
                    "session_type": session_type,
                    key: config_value,
                }
                configs.append(new_item)

            self._save_configs(configs)

        session_key = self._get_session_key(session_id, is_group)
        logger.info(
            "[session_config] Set %s=%s for session %s", key, value, session_key
        )
        return True

    async def get_config(
        self, session_id: str, is_group: bool, key: str, default: Any = None
    ) -> Any:
        """获取会话配置项。

        参数:
            session_id: 会话ID
            is_group: 是否为群聊
            key: 配置键
            default: 默认值

        返回:
            配置值，如果不存在则返回默认值
        """
        async with self._lock:
            cfg = self._get_session_config(session_id, is_group)
            if not cfg:
                return default

            value = cfg.get(key)
            if value is None or value == "":
                return default

            # 转换布尔值类型
            if key == "r18_docx_mode":
                return value == "enabled"
            if key == "auto_revoke_r18":
                return value == "enabled"

            return value

    async def clear_config(self, session_id: str, is_group: bool, key: str) -> bool:
        """清除会话配置项。

        参数:
            session_id: 会话ID
            is_group: 是否为群聊
            key: 配置键

        返回:
            清除成功返回 True，否则返回 False
        """
        async with self._lock:
            configs = self._get_configs()

            idx = self._find_session_index(configs, session_id, is_group)
            if idx is None:
                return False

            cfg = configs[idx]
            if key not in cfg:
                return False

            del cfg[key]
            # 如果配置项都为空，删除整个会话配置
            if not any(k in cfg for k in self.ALLOWED_KEYS if k != key):
                configs.pop(idx)

            self._save_configs(configs)
            session_key = self._get_session_key(session_id, is_group)
            logger.info("[session_config] Cleared %s for session %s", key, session_key)
            return True

    async def get_session_content_mode(
        self, session_id: str, is_group: bool
    ) -> str | None:
        """获取会话的内容模式。

        参数:
            session_id: 会话ID
            is_group: 是否为群聊

        返回:
            内容模式 (sfw/r18/mix)，如果未设置则返回 None
        """
        return await self.get_config(session_id, is_group, "content_mode")

    async def set_session_content_mode(
        self, session_id: str, is_group: bool, mode: str
    ) -> bool:
        """设置会话的内容模式。

        参数:
            session_id: 会话ID
            is_group: 是否为群聊
            mode: 内容模式 (sfw/r18/mix)

        返回:
            设置成功返回 True，否则返回 False
        """
        return await self.set_config(session_id, is_group, "content_mode", mode)

    async def clear_session_content_mode(self, session_id: str, is_group: bool) -> bool:
        """清除会话的内容模式设置。

        参数:
            session_id: 会话ID
            is_group: 是否为群聊

        返回:
            清除成功返回 True，否则返回 False
        """
        return await self.clear_config(session_id, is_group, "content_mode")

    async def get_session_r18_docx_mode(
        self, session_id: str, is_group: bool
    ) -> bool | None:
        """获取会话的 R18 Docx 模式设置。

        参数:
            session_id: 会话ID
            is_group: 是否为群聊

        返回:
            R18 Docx 模式设置 (True/False)，如果未设置则返回 None
        """
        return await self.get_config(session_id, is_group, "r18_docx_mode")

    async def set_session_r18_docx_mode(
        self, session_id: str, is_group: bool, enabled: bool
    ) -> bool:
        """设置会话的 R18 Docx 模式。

        参数:
            session_id: 会话ID
            is_group: 是否为群聊
            enabled: 是否启用 R18 Docx 模式

        返回:
            设置成功返回 True，否则返回 False
        """
        return await self.set_config(
            session_id, is_group, "r18_docx_mode", bool(enabled)
        )

    async def clear_session_r18_docx_mode(
        self, session_id: str, is_group: bool
    ) -> bool:
        """清除会话的 R18 Docx 模式设置。

        参数:
            session_id: 会话ID
            is_group: 是否为群聊

        返回:
            清除成功返回 True，否则返回 False
        """
        return await self.clear_config(session_id, is_group, "r18_docx_mode")

    async def get_session_auto_revoke_r18(
        self, session_id: str, is_group: bool
    ) -> bool | None:
        """获取会话的自动撤回 R18 设置。

        参数:
            session_id: 会话ID
            is_group: 是否为群聊

        返回:
            自动撤回设置 (True/False)，如果未设置则返回 None
        """
        return await self.get_config(session_id, is_group, "auto_revoke_r18")

    async def set_session_auto_revoke_r18(
        self, session_id: str, is_group: bool, enabled: bool
    ) -> bool:
        """设置会话的自动撤回 R18。

        参数:
            session_id: 会话ID
            is_group: 是否为群聊
            enabled: 是否启用自动撤回

        返回:
            设置成功返回 True，否则返回 False
        """
        return await self.set_config(
            session_id, is_group, "auto_revoke_r18", bool(enabled)
        )

    async def clear_session_auto_revoke_r18(
        self, session_id: str, is_group: bool
    ) -> bool:
        """清除会话的自动撤回 R18 设置。

        参数:
            session_id: 会话ID
            is_group: 是否为群聊

        返回:
            清除成功返回 True，否则返回 False
        """
        return await self.clear_config(session_id, is_group, "auto_revoke_r18")

    async def get_session_send_mode(
        self, session_id: str, is_group: bool
    ) -> str | None:
        """获取会话的发送模式设置。

        参数:
            session_id: 会话ID
            is_group: 是否为群聊

        返回:
            发送模式 (image/forward/auto)，如果未设置则返回 None
        """
        return await self.get_config(session_id, is_group, "send_mode")

    async def set_session_send_mode(
        self, session_id: str, is_group: bool, mode: str
    ) -> bool:
        """设置会话的发送模式。

        参数:
            session_id: 会话ID
            is_group: 是否为群聊
            mode: 发送模式 (image/forward/auto)

        返回:
            设置成功返回 True，否则返回 False
        """
        return await self.set_config(session_id, is_group, "send_mode", mode)

    async def clear_session_send_mode(self, session_id: str, is_group: bool) -> bool:
        """清除会话的发送模式设置。

        参数:
            session_id: 会话ID
            is_group: 是否为群聊

        返回:
            清除成功返回 True，否则返回 False
        """
        return await self.clear_config(session_id, is_group, "send_mode")

    async def cleanup_expired_sessions(self, max_age_days: int = 30) -> int:
        """[Deprecated] 兼容接口：清理过期会话配置（当前实现为 no-op）。

        历史版本曾基于时间戳删除会话配置；当前配置结构不再保存时间信息，
        因此该方法仅兼容旧调用方而保留。

        参数:
            max_age_days: 兼容参数，当前版本中不会被使用

        返回:
            始终返回 0，不会执行任何删除操作
        """
        logger.info(
            "[session_config] cleanup_expired_sessions is deprecated no-op; "
            "max_age_days=%s is ignored",
            max_age_days,
        )
        return 0
