"""AstrBot Setu Plugin - Main entry point.

Commands are defined directly on the Star subclass so AstrBot's decorator-based
registration discovers them. Business logic is delegated to handler helpers.
"""

from __future__ import annotations

import asyncio
import datetime
import re
from collections.abc import AsyncGenerator
from contextlib import suppress
from typing import Any

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools
from astrbot.core import AstrBotConfig

from .src.infrastructure import (
    init_access_control_repo,
    init_fortune_repo,
    init_provider_from_config,
    init_session_config_repo,
)
from .src.infrastructure.astrbot import init_config, set_plugin_context
from .src.infrastructure.astrbot.commands import (
    FortuneCommandHandler,
    SessionConfigCommandHandler,
    SetuCommandHandler,
    register_fortune_llm_tools,
    register_session_config_llm_tools,
    register_setu_llm_tools,
    unregister_fortune_llm_tools,
    unregister_session_config_llm_tools,
    unregister_setu_llm_tools,
)
from .src.infrastructure.astrbot.session_config_api import (
    register_session_config_web_apis,
)
from .src.shared.send_cache import clear_send_cache, init_send_cache

# Regex patterns for command triggers
SETU_REGEX_PATTERN = r"^/?(来\s*(.*?)(份|个|张|点))(.*?)(?:福利|色|瑟|涩|塞)?图$"
FORTUNE_REGEX_PATTERN = r"^(?!/)(今日运势|jrys)$"

# Module-level handler singletons
_setu_handler: SetuCommandHandler | None = None
_fortune_handler: FortuneCommandHandler | None = None
_session_config_handler: SessionConfigCommandHandler | None = None

FORTUNE_REFRESH_COMMANDS = {
    "刷新今日运势": "self",
    "刷新jrys": "self",
    "flush_jrys": "self",
    "刷新本群今日运势": "group",
    "刷新本群jrys": "group",
    "flush_group_jrys": "group",
    "刷新全局今日运势": "all",
    "刷新全局jrys": "all",
    "flush_all_jrys": "all",
}
FORTUNE_TOGGLE_COMMANDS = {"开启运势": "enable", "关闭运势": "disable"}
FORTUNE_USER_COMMANDS = {
    "拉黑运势用户": "block",
    "解除运势拉黑": "unblock",
    "信任运势用户": "trust",
    "取消运势信任": "untrust",
}
FORTUNE_REFRESH_ARG_ALIASES = {
    "": "self",
    "我": "self",
    "自己": "self",
    "我的": "self",
    "self": "self",
    "me": "self",
    "本群": "group",
    "群": "group",
    "group": "group",
    "全局": "all",
    "全部": "all",
    "all": "all",
    "global": "all",
}
FORTUNE_TOGGLE_ARG_ALIASES = {
    "开": "enable",
    "开启": "enable",
    "on": "enable",
    "关": "disable",
    "关闭": "disable",
    "off": "disable",
}
FORTUNE_USER_ARG_ALIASES = {
    "拉黑": "block",
    "黑名单": "block",
    "block": "block",
    "解除拉黑": "unblock",
    "解黑": "unblock",
    "取消拉黑": "unblock",
    "unblock": "unblock",
    "信任": "trust",
    "白名单": "trust",
    "trust": "trust",
    "取消信任": "untrust",
    "移除信任": "untrust",
    "取消白名单": "untrust",
    "untrust": "untrust",
}

_LEADING_COMMAND_PREFIX_PATTERN = re.compile(r"^[^\w\u4e00-\u9fff]+")


def _get_invoked_command(event: AstrMessageEvent) -> str:
    raw_message = getattr(event, "message_str", None)
    if not raw_message and hasattr(event, "get_message_str"):
        raw_message = event.get_message_str()
    text = str(raw_message or "").strip()
    if not text:
        return ""
    first_token = text.split(maxsplit=1)[0]
    return _LEADING_COMMAND_PREFIX_PATTERN.sub("", first_token).strip()


def _is_fortune_command_invocation(event: AstrMessageEvent) -> bool:
    """Return True when the message is already handled by fortune command routing."""
    if not getattr(event, "is_at_or_wake_command", False):
        return False
    return _get_invoked_command(event) in {"今日运势", "jrys"}


def _fortune_auto_refresh_enabled(config: Any) -> bool:
    fortune = getattr(config, "fortune", None)
    return (
        getattr(fortune, "enabled", False) is True
        and getattr(fortune, "auto_refresh", False) is True
    )


def _seconds_until_next_midnight() -> float:
    now = datetime.datetime.now()
    tomorrow = now.date() + datetime.timedelta(days=1)
    next_midnight = datetime.datetime.combine(tomorrow, datetime.time.min)
    return max(1.0, (next_midnight - now).total_seconds())


def _resolve_fortune_refresh_target(event: AstrMessageEvent, args: str) -> str:
    command = _get_invoked_command(event)
    if command in FORTUNE_REFRESH_COMMANDS:
        return FORTUNE_REFRESH_COMMANDS[command]

    target = FORTUNE_REFRESH_ARG_ALIASES.get((args or "").strip().lower())
    if target:
        return target
    raise ValueError("用法：/运势刷新 [我|本群|全局]")


def _resolve_fortune_toggle_action(event: AstrMessageEvent, args: str) -> str:
    command = _get_invoked_command(event)
    if command in FORTUNE_TOGGLE_COMMANDS:
        return FORTUNE_TOGGLE_COMMANDS[command]

    action = FORTUNE_TOGGLE_ARG_ALIASES.get((args or "").strip().lower())
    if action:
        return action
    raise ValueError("用法：/运势开关 <开|关>")


def _resolve_fortune_user_action(event: AstrMessageEvent, args: str) -> tuple[str, str]:
    command = _get_invoked_command(event)
    if command in FORTUNE_USER_COMMANDS:
        return FORTUNE_USER_COMMANDS[command], args

    normalized_args = (args or "").strip()
    if not normalized_args:
        raise ValueError("用法：/运势用户 <拉黑|解黑|信任|取消信任> [用户]")

    parts = normalized_args.split(maxsplit=1)
    action = FORTUNE_USER_ARG_ALIASES.get(parts[0].lower())
    if not action:
        raise ValueError("用法：/运势用户 <拉黑|解黑|信任|取消信任> [用户]")
    target = parts[1] if len(parts) > 1 else ""
    return action, target


class SetuPlugin(Star):
    """Main plugin class with command handlers on the Star subclass.

    AstrBot only discovers @filter.command/@filter.regex handlers whose
    __module__ matches the plugin's main module path. Defining handlers
    here ensures they are found and bound to the Star instance.
    """

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context, config)
        self.context = context
        self._plugin_config = config
        self._fortune_pregenerate_task: asyncio.Task[None] | None = None
        register_session_config_web_apis(self.context)

    async def initialize(self) -> None:
        global _setu_handler, _fortune_handler, _session_config_handler

        raw_config = self._runtime_plugin_config()
        cfg = init_config(raw_config)
        set_plugin_context(self.context)
        data_dir = StarTools.get_data_dir(self.name)

        init_provider_from_config(cfg)

        await init_access_control_repo(data_dir, raw_config)
        await init_fortune_repo(data_dir)
        await init_session_config_repo(data_dir)
        await init_send_cache(
            data_dir,
            enabled=cfg.cache_enabled,
            ttl_hours=cfg.cache_ttl_hours,
            max_items=cfg.cache_max_items,
            cleanup_on_start=cfg.cache_cleanup_on_start,
        )

        _setu_handler = SetuCommandHandler()
        _fortune_handler = FortuneCommandHandler()
        _session_config_handler = SessionConfigCommandHandler()
        if _fortune_auto_refresh_enabled(cfg):
            self._fortune_pregenerate_task = asyncio.create_task(
                self._fortune_pregenerate_loop(), name="setu_fortune_pregenerate"
            )

        try:
            register_setu_llm_tools()
            register_fortune_llm_tools()
            register_session_config_llm_tools()
        except Exception as e:
            logger.warning("Failed to register LLM tools: %s", e)

        logger.info("SetuPlugin initialized successfully")

    async def terminate(self) -> None:
        global _setu_handler, _fortune_handler, _session_config_handler

        from .src.infrastructure import (
            clear_fortune_repo,
            clear_provider,
            clear_repo,
            clear_session_config_repo,
        )

        if self._fortune_pregenerate_task is not None:
            self._fortune_pregenerate_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._fortune_pregenerate_task
            self._fortune_pregenerate_task = None

        try:
            unregister_setu_llm_tools()
            unregister_fortune_llm_tools()
            unregister_session_config_llm_tools()
        except Exception:
            pass

        clear_provider()
        clear_repo()
        clear_fortune_repo()
        clear_session_config_repo()
        clear_send_cache()

        _setu_handler = None
        _fortune_handler = None
        _session_config_handler = None

        logger.info("SetuPlugin terminated")

    async def _fortune_pregenerate_loop(self) -> None:
        """Cache fortune card images for recently active users after day rollover."""
        while True:
            await asyncio.sleep(_seconds_until_next_midnight())
            await self._pregenerate_active_fortune_images()

    async def _pregenerate_active_fortune_images(self) -> None:
        if _fortune_handler is None:
            return
        try:
            cached_count = await _fortune_handler.pregenerate_active_fortune_images()
            if cached_count:
                logger.info(
                    "[fortune] Pregenerated %d rendered fortune card caches",
                    cached_count,
                )
            else:
                logger.debug("[fortune] No fortune card caches pregenerated")
        except Exception as exc:
            logger.warning("[fortune] Failed to pregenerate fortune card caches: %s", exc)

    def _runtime_plugin_config(self) -> dict[str, Any]:
        """Return the plugin-scoped config dict passed in by AstrBot."""
        if isinstance(self._plugin_config, dict):
            return dict(self._plugin_config)
        items = getattr(self._plugin_config, "items", None)
        if callable(items):
            return dict(items())
        return dict(self._plugin_config)

    # ==================== Setu Commands ====================

    @filter.regex(SETU_REGEX_PATTERN)
    async def get_random_picture(
        self, event: AstrMessageEvent
    ) -> AsyncGenerator[Any, None]:
        """来份色图 / 来张图 etc."""
        if _setu_handler is None:
            yield event.plain_result("插件未初始化")
            return
        async for result in _setu_handler.get_random_picture(event):
            yield result

    @filter.command("setu")
    async def setu_command(
        self, event: AstrMessageEvent, count: str = "1", *, tags: str = ""
    ) -> AsyncGenerator[Any, None]:
        """/setu [count] [tags...]"""
        if _setu_handler is None:
            yield event.plain_result("插件未初始化")
            return
        async for result in _setu_handler.setu_command(event, count, tags=tags):
            yield result

    @filter.command("session_config")
    async def session_config_command(
        self, event: AstrMessageEvent, args: str = ""
    ) -> AsyncGenerator[Any, None]:
        """/session_config get|set|clear"""
        if _session_config_handler is None:
            yield event.plain_result("插件未初始化")
            return
        async for result in _session_config_handler.session_config_command(event, args):
            yield result

    # ==================== Fortune Commands ====================

    @filter.command("今日运势", alias={"jrys"})
    async def fortune_command(
        self, event: AstrMessageEvent
    ) -> AsyncGenerator[Any, None]:
        """今日运势 / jrys"""
        if _fortune_handler is None:
            yield event.plain_result("插件未初始化")
            return
        async for result in _fortune_handler.fortune_command(event):
            yield result

    @filter.regex(FORTUNE_REGEX_PATTERN)
    async def fortune_regex_command(
        self, event: AstrMessageEvent
    ) -> AsyncGenerator[Any, None]:
        """纯文本今日运势/jrys入口（不带命令前缀）。"""
        if _is_fortune_command_invocation(event):
            return
        if _fortune_handler is None:
            yield event.plain_result("插件未初始化")
            return
        async for result in _fortune_handler.fortune_command(event):
            yield result

    @filter.command(
        "运势刷新",
        alias={
            "刷新今日运势",
            "刷新jrys",
            "flush_jrys",
            "刷新本群今日运势",
            "刷新本群jrys",
            "flush_group_jrys",
            "刷新全局今日运势",
            "刷新全局jrys",
            "flush_all_jrys",
        },
    )
    async def fortune_refresh_command(
        self, event: AstrMessageEvent, args: str = ""
    ) -> AsyncGenerator[Any, None]:
        """运势刷新 [我|本群|全局]"""
        if _fortune_handler is None:
            yield event.plain_result("插件未初始化")
            return

        try:
            target = _resolve_fortune_refresh_target(event, args)
        except ValueError as exc:
            yield event.plain_result(str(exc))
            return

        handler_map = {
            "self": _fortune_handler.refresh_fortune_command,
            "group": _fortune_handler.refresh_group_fortune_command,
            "all": _fortune_handler.refresh_all_fortune_command,
        }
        async for result in handler_map[target](event):
            yield result

    @filter.command("运势开关", alias={"开启运势", "关闭运势"})
    async def fortune_toggle_command(
        self, event: AstrMessageEvent, args: str = ""
    ) -> AsyncGenerator[Any, None]:
        """运势开关 <开|关>"""
        if _fortune_handler is None:
            yield event.plain_result("插件未初始化")
            return

        try:
            action = _resolve_fortune_toggle_action(event, args)
        except ValueError as exc:
            yield event.plain_result(str(exc))
            return

        handler_map = {
            "enable": _fortune_handler.enable_fortune_group_command,
            "disable": _fortune_handler.disable_fortune_group_command,
        }
        async for result in handler_map[action](event, ""):
            yield result

    @filter.command(
        "运势用户",
        alias={"拉黑运势用户", "解除运势拉黑", "信任运势用户", "取消运势信任"},
    )
    async def fortune_user_command(
        self, event: AstrMessageEvent, args: str = ""
    ) -> AsyncGenerator[Any, None]:
        """运势用户 <拉黑|解黑|信任|取消信任> [用户]"""
        if _fortune_handler is None:
            yield event.plain_result("插件未初始化")
            return

        try:
            action, target = _resolve_fortune_user_action(event, args)
        except ValueError as exc:
            yield event.plain_result(str(exc))
            return

        handler_map = {
            "block": _fortune_handler.block_fortune_user_command,
            "unblock": _fortune_handler.unblock_fortune_user_command,
            "trust": _fortune_handler.trust_fortune_user_command,
            "untrust": _fortune_handler.untrust_fortune_user_command,
        }
        async for result in handler_map[action](event, target):
            yield result
