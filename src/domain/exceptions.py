"""Domain exceptions for Setu and Fortune bounded contexts."""

from __future__ import annotations


class SetuException(Exception):
    """Base exception for Setu domain errors."""


class ProviderError(SetuException):
    """Raised when image provider fails."""


class SendError(SetuException):
    """Raised when image sending fails."""


class AccessDeniedError(SetuException):
    """Raised when access control denies a request."""

    def __init__(self, reason: str = "") -> None:
        self.reason = reason
        super().__init__(f"Access denied: {reason}" if reason else "Access denied")


class ValidationError(SetuException):
    """Raised when input validation fails."""


class FortuneException(Exception):
    """Base exception for Fortune domain errors."""


class FortuneNotFoundError(FortuneException):
    """Raised when fortune record is not found."""
