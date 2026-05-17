"""Tests for domain exceptions."""

from __future__ import annotations

import pytest

from astrbot_plugin_setu.src.domain.exceptions import (
    AccessDeniedError,
    FortuneException,
    FortuneNotFoundError,
    ProviderError,
    SendError,
    SetuException,
    ValidationError,
)


class TestSetuException:
    """Test SetuException base class."""

    def test_setu_exception(self) -> None:
        """Test basic SetuException."""
        with pytest.raises(SetuException):
            raise SetuException("Test error")


class TestProviderError:
    """Test ProviderError."""

    def test_provider_error(self) -> None:
        """Test ProviderError is SetuException."""
        with pytest.raises(SetuException):
            raise ProviderError("Provider failed")


class TestSendError:
    """Test SendError."""

    def test_send_error(self) -> None:
        """Test SendError is SetuException."""
        with pytest.raises(SetuException):
            raise SendError("Send failed")


class TestAccessDeniedError:
    """Test AccessDeniedError."""

    def test_access_denied_with_reason(self) -> None:
        """Test AccessDeniedError with reason."""
        error = AccessDeniedError("User is blocked")
        assert str(error) == "Access denied: User is blocked"
        assert error.reason == "User is blocked"

    def test_access_denied_no_reason(self) -> None:
        """Test AccessDeniedError without reason."""
        error = AccessDeniedError()
        assert str(error) == "Access denied"
        assert error.reason == ""


class TestValidationError:
    """Test ValidationError."""

    def test_validation_error(self) -> None:
        """Test ValidationError is SetuException."""
        with pytest.raises(SetuException):
            raise ValidationError("Invalid input")


class TestFortuneException:
    """Test FortuneException base class."""

    def test_fortune_exception(self) -> None:
        """Test basic FortuneException."""
        with pytest.raises(FortuneException):
            raise FortuneException("Fortune error")


class TestFortuneNotFoundError:
    """Test FortuneNotFoundError."""

    def test_fortune_not_found(self) -> None:
        """Test FortuneNotFoundError is FortuneException."""
        with pytest.raises(FortuneException):
            raise FortuneNotFoundError("Fortune not found")
