"""今日运势会话配置管理。

支持会话级别的独立配置，包括标签和内容模式。
配置存储在 AstrBotConfig 的 fortune_session_configs 字段中，可在 WebUI 中管理。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from astrbot.api import logger

if TYPE_CHECKING:
    from astrbot.core import AstrBotConfig


class FortuneSessionConfig:
    """今日运势会话配置管理器。

    配置存储在 AstrBotConfig 的 fortune_session_configs 字段中，可在 WebUI 中管理。
    """

    # 允许会话覆盖的配置项
    ALLOWED_KEYS = {"tags", "content_mode"}

    # 有效的内容模式值
    VALID_CONTENT_MODES = {"sfw", "r18", "mix"}

    def __init__(self, config: AstrBotConfig, data_dir: Path | None = None):
        """初始化配置管理器。

        参数:
            config: AstrBotConfig 配置对象
            data_dir: 插件数据目录（用于迁移旧配置）
        """
        self._config = config
        self._data_dir = data_dir
        self._lock = asyncio.Lock()
        self._migrated = False

    async def initialize(self) -> None:
        """初始化配置，迁移旧配置文件到新格式。"""
        if self._data_dir and not self._migrated:
            await self._migrate_old_config()
            self._migrated = True
        logger.info("[fortune_session] Session config initialized")

    async def _migrate_old_config(self) -> None:
        """迁移旧位置的配置文件到 AstrBotConfig。"""
        old_config_file = self._data_dir / "fortune_session_config.json"

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
            new_configs = list(self._config.get("fortune_session_configs", []))

            for session_key, session_data in sessions.items():
                # 解析 session_key (格式: "group:12345" 或 "private:67890")
                parts = session_key.split(":", 1)
                if len(parts) != 2:
                    continue

                session_type, session_id = parts

                # 构建新的配置项
                new_item = {
                    "session_id": session_id,
                    "session_type": session_type,
                }

                # 迁移各配置项
                if "tags" in session_data:
                    new_item["tags"] = session_data["tags"]
                if "content_mode" in session_data:
                    new_item["content_mode"] = session_data["content_mode"]

                # 检查是否已存在
                existing_idx = None
                for i, cfg in enumerate(new_configs):
                    if (
                        cfg.get("session_id") == session_id
                        and cfg.get("session_type") == session_type
                    ):
                        existing_idx = i
                        break

                if existing_idx is not None:
                    new_configs[existing_idx] = new_item
                else:
                    new_configs.append(new_item)

            # 保存迁移后的配置
            self._config["fortune_session_configs"] = new_configs
            self._config.save_config()

            # 删除旧配置文件
            await asyncio.to_thread(old_config_file.unlink)
            logger.info(
                "[fortune_session] Migrated old config to AstrBotConfig, %d sessions",
                len(new_configs),
            )
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("[fortune_session] Failed to migrate old config: %s", exc)

    def _get_session_config(self, session_id: str, is_group: bool) -> dict | None:
        """获取会话配置项。"""
        session_type = "group" if is_group else "private"
        configs = self._config.get("fortune_session_configs", [])

        for cfg in configs:
            if (
                cfg.get("session_id") == session_id
                and cfg.get("session_type") == session_type
            ):
                return cfg
        return None

    def _get_session_key(self, session_id: str, is_group: bool) -> str:
        """生成会话键。"""
        prefix = "group" if is_group else "private"
        return f"{prefix}:{session_id}"

    async def set_config(
        self, session_id: str, is_group: bool, key: str, value: Any
    ) -> bool:
        """设置会话配置项。"""
        if key not in self.ALLOWED_KEYS:
            logger.warning("[fortune_session] Key %s is not allowed", key)
            return False

        if key == "content_mode" and value not in self.VALID_CONTENT_MODES:
            logger.warning("[fortune_session] Invalid content_mode: %s", value)
            return False

        async with self._lock:
            session_type = "group" if is_group else "private"
            configs = list(self._config.get("fortune_session_configs", []))

            # 查找现有配置
            existing_idx = None
            for i, cfg in enumerate(configs):
                if (
                    cfg.get("session_id") == session_id
                    and cfg.get("session_type") == session_type
                ):
                    existing_idx = i
                    break

            if existing_idx is not None:
                # 更新现有配置
                configs[existing_idx][key] = value
            else:
                # 创建新配置
                new_item = {
                    "session_id": session_id,
                    "session_type": session_type,
                    key: value,
                }
                configs.append(new_item)

            self._config["fortune_session_configs"] = configs
            self._config.save_config()

        session_key = self._get_session_key(session_id, is_group)
        logger.info("[fortune_session] Set %s=%s for %s", key, value, session_key)
        return True

    async def get_config(
        self, session_id: str, is_group: bool, key: str, default: Any = None
    ) -> Any:
        """获取会话配置项。"""
        cfg = self._get_session_config(session_id, is_group)
        if not cfg:
            return default

        value = cfg.get(key)
        if value is None or value == "":
            return default

        return value

    async def clear_config(self, session_id: str, is_group: bool, key: str) -> bool:
        """清除会话配置项。"""
        async with self._lock:
            session_type = "group" if is_group else "private"
            configs = list(self._config.get("fortune_session_configs", []))

            for i, cfg in enumerate(configs):
                if (
                    cfg.get("session_id") == session_id
                    and cfg.get("session_type") == session_type
                ):
                    if key in cfg:
                        del cfg[key]
                        # 如果配置项都为空，删除整个会话配置
                        remaining_keys = [k for k in self.ALLOWED_KEYS if k in cfg]
                        if not remaining_keys:
                            configs.pop(i)
                        self._config["fortune_session_configs"] = configs
                        self._config.save_config()
                        session_key = self._get_session_key(session_id, is_group)
                        logger.info(
                            "[fortune_session] Cleared %s for %s", key, session_key
                        )
                        return True
            return False

    async def get_session_tags(self, session_id: str, is_group: bool) -> str | None:
        """获取会话的标签配置。"""
        return await self.get_config(session_id, is_group, "tags")

    async def set_session_tags(
        self, session_id: str, is_group: bool, tags: str
    ) -> bool:
        """设置会话的标签配置。"""
        return await self.set_config(session_id, is_group, "tags", tags)

    async def clear_session_tags(self, session_id: str, is_group: bool) -> bool:
        """清除会话的标签配置。"""
        return await self.clear_config(session_id, is_group, "tags")

    async def get_session_content_mode(
        self, session_id: str, is_group: bool
    ) -> str | None:
        """获取会话的内容模式配置。"""
        return await self.get_config(session_id, is_group, "content_mode")

    async def set_session_content_mode(
        self, session_id: str, is_group: bool, mode: str
    ) -> bool:
        """设置会话的内容模式配置。"""
        return await self.set_config(session_id, is_group, "content_mode", mode)

    async def clear_session_content_mode(self, session_id: str, is_group: bool) -> bool:
        """清除会话的内容模式配置。"""
        return await self.clear_config(session_id, is_group, "content_mode")

    async def get_effective_tags(
        self, session_id: str, is_group: bool, global_tags: str
    ) -> str:
        """获取生效的标签（优先会话配置）。"""
        session_tags = await self.get_session_tags(session_id, is_group)
        if session_tags is not None:
            return session_tags
        return global_tags

    async def get_effective_content_mode(
        self, session_id: str, is_group: bool, global_mode: str
    ) -> str:
        """获取生效的内容模式（优先会话配置）。"""
        session_mode = await self.get_session_content_mode(session_id, is_group)
        if session_mode:
            return session_mode
        return global_mode