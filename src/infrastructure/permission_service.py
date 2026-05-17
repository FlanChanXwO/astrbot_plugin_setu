"""Permission service for checking user roles.

Centralizes admin/super-user checks that were duplicated across
CommandHandler, LlmHandlers, and Fortune handlers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..shared import get_logger

if TYPE_CHECKING:
    from astrbot.api.event import AstrMessageEvent

logger = get_logger()


class PermissionService:
    """Service for checking user permissions.

    Provides a single place for admin/super-user checks,
    eliminating duplication across handlers.
    """

    @staticmethod
    def is_admin(event: AstrMessageEvent) -> bool:
        """Check if user is admin or super user.

        Args:
            event: Message event

        Returns:
            True if user is admin or super user
        """
        try:
            # Check is_admin method
            if hasattr(event, "is_admin") and callable(getattr(event, "is_admin")):
                if event.is_admin():
                    return True

            # Check is_super_user method
            if hasattr(event, "is_super_user") and callable(
                getattr(event, "is_super_user")
            ):
                if event.is_super_user():
                    return True

            # Check message_obj.sender.role
            if hasattr(event, "message_obj"):
                msg_obj = event.message_obj
                if hasattr(msg_obj, "sender") and hasattr(msg_obj.sender, "role"):
                    role = msg_obj.sender.role
                    if role in ("admin", "owner"):
                        return True

        except AttributeError as e:
            logger.debug("Permission check attr error: %s", e)
            pass

        return False

    @staticmethod
    def is_super_user(event: AstrMessageEvent) -> bool:
        """Check if user is super user.

        Args:
            event: Message event

        Returns:
            True if user is super user
        """
        try:
            if hasattr(event, "is_super_user") and callable(
                getattr(event, "is_super_user")
            ):
                if event.is_super_user():
                    return True

        except AttributeError as e:
            logger.debug("Super user check attr error: %s", e)
            pass

        return False

    @staticmethod
    def require_admin(event: AstrMessageEvent) -> tuple[bool, str]:
        """Check admin permission and return result with message.

        Args:
            event: Message event

        Returns:
            Tuple of (has_permission, error_message)
        """
        if PermissionService.is_admin(event):
            return True, ""
        return False, "❌ 权限不足：此命令仅限管理员或超级管理员使用。"

    @staticmethod
    def require_super_user(event: AstrMessageEvent) -> tuple[bool, str]:
        """Check super user permission and return result with message.

        Args:
            event: Message event

        Returns:
            Tuple of (has_permission, error_message)
        """
        if PermissionService.is_super_user(event):
            return True, ""
        return False, "❌ 权限不足：此命令仅限超级管理员使用。"
