"""Fortune command handler - all Fortune-related commands."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from astrbot.api.event import AstrMessageEvent
from astrbot.core.provider.register import llm_tools

from ....domain.access_control import AccessPolicy
from ....domain.fortune import (
    FortuneGenerationRequest,
    FortuneRecord,
)
from ....domain.fortune.service import FortuneService
from ....shared import get_logger
from ... import get_access_control_repo
from ...permission_service import PermissionService
from ...persistence import get_fortune_repo
from ..config import get_config

logger = get_logger()

# Regex pattern directly in decorator (not in constants)
FORTUNE_REGEX_PATTERN = r"^(?!/)(今日运势|jrys)$"


class FortuneCommandHandler:
    """Handles all Fortune-related commands.

    Uses singleton pattern for config, fortune repo, and access control repo.
    Commands are auto-registered by AstrBot decorators.
    """

    def __init__(self) -> None:
        pass

    # ==================== Command Handlers ====================

    async def fortune_command(
        self, event: AstrMessageEvent
    ) -> AsyncGenerator[Any, None]:
        """Handle /今日运势 command (/今日运势, /jrys)."""
        config = get_config()
        if not config:
            yield event.plain_result(self._message("config_not_loaded"))
            return

        has_perm, msg = await self._check_access(event, config)
        if not has_perm:
            yield event.plain_result(msg)
            return

        request = self._build_fortune_request(event)

        try:
            repo = get_fortune_repo()
            service = FortuneService(repository=repo)
            result = await service.get_or_create_fortune(request)
            yield event.plain_result(self._format_fortune(result))
        except Exception as e:
            yield event.plain_result(self._message("fortune_get_failed", error=e))

    async def refresh_fortune_command(
        self, event: AstrMessageEvent
    ) -> AsyncGenerator[Any, None]:
        """Handle /刷新今日运势 command."""
        has_perm, msg = PermissionService.require_admin(event)
        if not has_perm:
            yield event.plain_result(msg)
            return

        config = get_config()
        if not config:
            yield event.plain_result(self._message("config_not_loaded"))
            return

        request = self._build_fortune_request(event)

        try:
            repo = get_fortune_repo()
            service = FortuneService(repository=repo)
            result = await service.refresh_fortune(request)
            yield event.plain_result(self._format_fortune(result))
        except Exception as e:
            yield event.plain_result(self._message("fortune_refresh_failed", error=e))

    async def refresh_group_fortune_command(
        self, event: AstrMessageEvent
    ) -> AsyncGenerator[Any, None]:
        """Handle /刷新本群今日运势 command."""
        has_perm, msg = PermissionService.require_admin(event)
        if not has_perm:
            yield event.plain_result(msg)
            return

        group_id = event.get_group_id()
        if not group_id:
            yield event.plain_result(self._message("fortune_group_only"))
            return

        config = get_config()
        if not config:
            yield event.plain_result(self._message("config_not_loaded"))
            return

        try:
            repo = get_fortune_repo()
            service = FortuneService(repository=repo)
            refreshed_count = await service.pregenerate_active_users()
            yield event.plain_result(
                self._message("fortune_refresh_group_done", count=refreshed_count)
            )
        except Exception as e:
            yield event.plain_result(
                self._message("fortune_refresh_group_failed", error=e)
            )

    async def refresh_all_fortune_command(
        self, event: AstrMessageEvent
    ) -> AsyncGenerator[Any, None]:
        """Handle /刷新全局今日运势 command."""
        has_perm, msg = PermissionService.require_super_user(event)
        if not has_perm:
            yield event.plain_result(msg)
            return

        config = get_config()
        if not config:
            yield event.plain_result(self._message("config_not_loaded"))
            return

        try:
            repo = get_fortune_repo()
            service = FortuneService(repository=repo)
            refreshed_count = await service.pregenerate_active_users()
            yield event.plain_result(
                self._message("fortune_refresh_all_done", count=refreshed_count)
            )
        except Exception as e:
            yield event.plain_result(
                self._message("fortune_refresh_all_failed", error=e)
            )

    async def enable_fortune_group_command(
        self, event: AstrMessageEvent, args: str = ""
    ) -> AsyncGenerator[Any, None]:
        """Handle /开启运势 command (enable Fortune for current group)."""
        has_perm, msg = PermissionService.require_admin(event)
        if not has_perm:
            yield event.plain_result(msg)
            return

        group_id = event.get_group_id()
        if not group_id:
            yield event.plain_result(self._message("fortune_group_only"))
            return

        repo = get_access_control_repo()
        await repo.remove_fortune_blocked_group(str(group_id))
        yield event.plain_result(self._message("fortune_enabled_group_done"))

    async def disable_fortune_group_command(
        self, event: AstrMessageEvent, args: str = ""
    ) -> AsyncGenerator[Any, None]:
        """Handle /关闭运势 command (disable Fortune for current group)."""
        has_perm, msg = PermissionService.require_admin(event)
        if not has_perm:
            yield event.plain_result(msg)
            return

        group_id = event.get_group_id()
        if not group_id:
            yield event.plain_result(self._message("fortune_group_only"))
            return

        repo = get_access_control_repo()
        await repo.add_fortune_blocked_group(str(group_id))
        yield event.plain_result(self._message("fortune_disabled_group_done"))

    async def block_fortune_user_command(
        self, event: AstrMessageEvent, args: str = ""
    ) -> AsyncGenerator[Any, None]:
        """Handle /拉黑运势用户 command (add user to Fortune blacklist)."""
        has_perm, msg = PermissionService.require_admin(event)
        if not has_perm:
            yield event.plain_result(msg)
            return

        target_id = args.strip() or event.get_sender_id()
        if not target_id:
            yield event.plain_result(self._message("fortune_missing_user_id"))
            return

        repo = get_access_control_repo()
        await repo.add_fortune_blocked_user(str(target_id))
        yield event.plain_result(
            self._message("fortune_block_user_done", user_id=target_id)
        )

    async def unblock_fortune_user_command(
        self, event: AstrMessageEvent, args: str = ""
    ) -> AsyncGenerator[Any, None]:
        """Handle /解除运势拉黑 command (remove user from Fortune blacklist)."""
        has_perm, msg = PermissionService.require_admin(event)
        if not has_perm:
            yield event.plain_result(msg)
            return

        target_id = args.strip()
        if not target_id:
            yield event.plain_result(self._message("fortune_missing_user_id"))
            return

        repo = get_access_control_repo()
        await repo.remove_fortune_blocked_user(str(target_id))
        yield event.plain_result(
            self._message("fortune_unblock_user_done", user_id=target_id)
        )

    async def trust_fortune_user_command(
        self, event: AstrMessageEvent, args: str = ""
    ) -> AsyncGenerator[Any, None]:
        """Handle /信任运势用户 command (add user to Fortune whitelist)."""
        has_perm, msg = PermissionService.require_admin(event)
        if not has_perm:
            yield event.plain_result(msg)
            return

        target_id = args.strip() or event.get_sender_id()
        if not target_id:
            yield event.plain_result(self._message("fortune_missing_user_id"))
            return

        repo = get_access_control_repo()
        await repo.add_fortune_whitelist_user(str(target_id))
        yield event.plain_result(
            self._message("fortune_trust_user_done", user_id=target_id)
        )

    async def untrust_fortune_user_command(
        self, event: AstrMessageEvent, args: str = ""
    ) -> AsyncGenerator[Any, None]:
        """Handle /取消运势信任 command (remove user from Fortune whitelist)."""
        has_perm, msg = PermissionService.require_admin(event)
        if not has_perm:
            yield event.plain_result(msg)
            return

        target_id = args.strip()
        if not target_id:
            yield event.plain_result(self._message("fortune_missing_user_id"))
            return

        repo = get_access_control_repo()
        await repo.remove_fortune_whitelist_user(str(target_id))
        yield event.plain_result(
            self._message("fortune_untrust_user_done", user_id=target_id)
        )

    # ==================== LLM Tool Handlers ====================

    async def _llm_get_fortune(self, event: AstrMessageEvent) -> str:
        """LLM tool handler for getting today's fortune."""
        config = get_config()
        if not config:
            return self._message("config_not_loaded")

        has_perm, msg = await self._check_access(event, config)
        if not has_perm:
            return msg

        request = self._build_fortune_request(event)

        try:
            repo = get_fortune_repo()
            service = FortuneService(repository=repo)
            result = await service.get_or_create_fortune(request)
            return f"今日运势: {result.title}, 星级: {result.star_count}/{result.max_stars}"
        except Exception as e:
            return self._message("fortune_get_failed", error=e)

    async def _llm_refresh_fortune(self, event: AstrMessageEvent) -> str:
        """LLM tool handler for refreshing today's fortune."""
        has_perm, msg = PermissionService.require_admin(event)
        if not has_perm:
            return msg

        config = get_config()
        if not config:
            return self._message("config_not_loaded")

        request = self._build_fortune_request(event)

        try:
            repo = get_fortune_repo()
            service = FortuneService(repository=repo)
            result = await service.refresh_fortune(request)
            return f"今日运势已刷新: {result.title}"
        except Exception as e:
            return self._message("fortune_refresh_failed", error=e)

    async def _llm_refresh_group_fortune(self, event: AstrMessageEvent) -> str:
        """LLM tool handler for refreshing group fortunes."""
        has_perm, msg = PermissionService.require_admin(event)
        if not has_perm:
            return msg

        group_id = event.get_group_id()
        if not group_id:
            return self._message("fortune_group_only")

        config = get_config()
        if not config:
            return self._message("config_not_loaded")

        try:
            repo = get_fortune_repo()
            service = FortuneService(repository=repo)
            refreshed_count = await service.pregenerate_active_users()
            return self._message("fortune_refresh_group_done", count=refreshed_count)
        except Exception as e:
            return self._message("fortune_refresh_group_failed", error=e)

    async def _llm_refresh_all_fortune(self, event: AstrMessageEvent) -> str:
        """LLM tool handler for refreshing all fortunes."""
        has_perm, msg = PermissionService.require_super_user(event)
        if not has_perm:
            return msg

        config = get_config()
        if not config:
            return self._message("config_not_loaded")

        try:
            repo = get_fortune_repo()
            service = FortuneService(repository=repo)
            refreshed_count = await service.pregenerate_active_users()
            return self._message("fortune_refresh_all_done", count=refreshed_count)
        except Exception as e:
            return self._message("fortune_refresh_all_failed", error=e)

    # ==================== Helper Methods ====================

    async def _check_access(self, event: AstrMessageEvent, config) -> tuple[bool, str]:
        """Check if user/group has access to Fortune feature."""
        from ....domain.access_control.service import AccessControlService

        user_id = event.get_sender_id()
        group_id = event.get_group_id()

        policy = AccessPolicy.for_session(
            user_id=user_id,
            group_id=group_id,
            user_mode=config.fortune_user_access_control_mode if config else "none",
            group_mode=config.fortune_group_access_control_mode if config else "none",
        )

        repo = get_access_control_repo()
        service = AccessControlService(repo)
        return await service.check_fortune_access(policy)

    def _build_fortune_request(
        self, event: AstrMessageEvent
    ) -> FortuneGenerationRequest:
        """Build a framework-free fortune generation request from an AstrBot event."""
        user_id = str(event.get_sender_id())
        username = user_id
        message_obj = getattr(event, "message_obj", None)
        sender = getattr(message_obj, "sender", None)
        for attr in ("nickname", "name", "user_name"):
            value = getattr(sender, attr, None)
            if value:
                username = str(value)
                break
        group_id = event.get_group_id()
        return FortuneGenerationRequest.for_today(
            user_id=user_id,
            username=username,
            group_id=str(group_id) if group_id else None,
        )

    def _format_fortune(self, result: FortuneRecord) -> str:
        """Format fortune result for message sending."""
        return (
            f"🔮 {result.date_str} 运势\n"
            f"📊 {result.title}\n"
            f"⭐ {'★' * result.star_count}{'☆' * (result.max_stars - result.star_count)}\n"
            f"💬 {result.description}"
        )

    def _message(self, key: str, **kwargs: Any) -> str:
        config = get_config()
        if config and hasattr(config, "resolve_message"):
            text = config.resolve_message(key, **kwargs)
            if text is not None:
                return text
        return ""


# ==================== LLM Tools Registration ====================


def register_llm_tools() -> None:
    """Register Fortune LLM tools."""
    _handler = FortuneCommandHandler()
    tools = [
        (
            "get_today_fortune",
            _handler._llm_get_fortune,
            [],
            "Get today's fortune for the user.",
        ),
        (
            "refresh_my_fortune",
            _handler._llm_refresh_fortune,
            [],
            "Refresh my today's fortune (admin only).",
        ),
        (
            "refresh_group_fortune",
            _handler._llm_refresh_group_fortune,
            [],
            "Refresh today's fortune for the current group (admin only).",
        ),
        (
            "refresh_all_fortune",
            _handler._llm_refresh_all_fortune,
            [],
            "Refresh today's fortune for all users (super admin only).",
        ),
    ]

    for name, handler, args, desc in tools:
        try:
            llm_tools.add_func(name=name, func_args=args, desc=desc, handler=handler)
            tool = llm_tools.get_func(name)
            if tool:
                tool.handler_module_path = __name__
        except (AttributeError, RuntimeError):
            pass


def unregister_llm_tools() -> None:
    """Unregister Fortune LLM tools."""
    tool_names = [
        "get_today_fortune",
        "refresh_my_fortune",
        "refresh_group_fortune",
        "refresh_all_fortune",
    ]

    for name in tool_names:
        try:
            llm_tools.remove_func(name)
        except (AttributeError, RuntimeError):
            pass
