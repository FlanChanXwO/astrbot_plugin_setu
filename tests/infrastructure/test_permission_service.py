"""Tests for PermissionService."""

from __future__ import annotations

from unittest.mock import MagicMock


from astrbot_plugin_setu.src.infrastructure.permission_service import PermissionService


class TestPermissionService:
    """Test PermissionService."""

    def test_is_admin_with_role(self, mock_event) -> None:
        """Test is_admin with admin role."""
        mock_event.is_admin = MagicMock(return_value=True)
        assert PermissionService.is_admin(mock_event) is True

    def test_is_admin_with_super_user(self, mock_event) -> None:
        """Test is_admin with super user."""
        mock_event.is_admin = MagicMock(return_value=False)
        mock_event.is_super_user = MagicMock(return_value=True)
        assert PermissionService.is_admin(mock_event) is True

    def test_is_admin_with_sender_role(self, mock_event) -> None:
        """Test is_admin with sender role."""
        mock_event.is_admin = MagicMock(return_value=False)
        mock_event.is_super_user = MagicMock(return_value=False)

        sender = MagicMock()
        sender.role = "admin"
        mock_event.message_obj = MagicMock()
        mock_event.message_obj.sender = sender

        assert PermissionService.is_admin(mock_event) is True

    def test_is_admin_false(self, mock_event) -> None:
        """Test is_admin returns False for regular user."""
        mock_event.is_admin = MagicMock(return_value=False)
        mock_event.is_super_user = MagicMock(return_value=False)
        assert PermissionService.is_admin(mock_event) is False

    def test_is_super_user(self, mock_event) -> None:
        """Test is_super_user."""
        mock_event.is_super_user = MagicMock(return_value=True)
        assert PermissionService.is_super_user(mock_event) is True

    def test_require_admin_granted(self, mock_event) -> None:
        """Test require_admin when permission granted."""
        mock_event.is_admin = MagicMock(return_value=True)
        has_perm, msg = PermissionService.require_admin(mock_event)
        assert has_perm is True
        assert msg == ""

    def test_require_admin_denied(self, mock_event) -> None:
        """Test require_admin when permission denied."""
        mock_event.is_admin = MagicMock(return_value=False)
        mock_event.is_super_user = MagicMock(return_value=False)
        has_perm, msg = PermissionService.require_admin(mock_event)
        assert has_perm is False
        assert "权限不足" in msg

    def test_require_super_user_granted(self, mock_event) -> None:
        """Test require_super_user when permission granted."""
        mock_event.is_super_user = MagicMock(return_value=True)
        has_perm, msg = PermissionService.require_super_user(mock_event)
        assert has_perm is True
        assert msg == ""

    def test_require_super_user_denied(self, mock_event) -> None:
        """Test require_super_user when permission denied."""
        mock_event.is_super_user = MagicMock(return_value=False)
        has_perm, msg = PermissionService.require_super_user(mock_event)
        assert has_perm is False
        assert "权限不足" in msg
