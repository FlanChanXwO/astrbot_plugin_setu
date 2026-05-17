"""Domain exceptions for Setu and Fortune bounded contexts."""

from __future__ import annotations


class SetuException(Exception):
    """Base exception for Setu domain errors."""

    pass


class ProviderError(SetuException):
    """Raised when image provider fails."""

    pass


class SendError(SetuException):
    """Raised when image sending fails."""

    pass


class AccessDeniedError(SetuException):
    """Raised when access control denies a request."""

    def __init__(self, reason: str = "") -> None:
        self.reason = reason
        super().__init__(f"Access denied: {reason}" if reason else "Access denied")


class ValidationError(SetuException):
    """Raised when input validation fails."""

    pass


class FortuneException(Exception):
    """Base exception for Fortune domain errors."""

    pass


class FortuneNotFoundError(FortuneException):
    """Raised when fortune record is not found."""

    pass
