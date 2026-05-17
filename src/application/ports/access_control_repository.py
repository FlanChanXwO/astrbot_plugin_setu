"""Repository interface for access control data.

Defines the contract for accessing blacklist/whitelist data.
Implemented by infrastructure layer (e.g., FileBackedAccessControlRepo).
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class AccessControlRepository(ABC):
    """Repository interface for access control data."""

    # Setu user access control
    @abstractmethod
    async def is_setu_user_blocked(self, user_id: str) -> bool:
        """Check if user is in Setu blacklist."""
        ...

    @abstractmethod
    async def is_setu_user_whitelisted(self, user_id: str) -> bool:
        """Check if user is in Setu whitelist."""
        ...

    @abstractmethod
    async def add_setu_blocked_user(self, user_id: str) -> bool:
        """Add user to Setu blacklist."""
        ...

    @abstractmethod
    async def remove_setu_blocked_user(self, user_id: str) -> bool:
        """Remove user from Setu blacklist."""
        ...

    @abstractmethod
    async def add_setu_whitelist_user(self, user_id: str) -> bool:
        """Add user to Setu whitelist."""
        ...

    @abstractmethod
    async def remove_setu_whitelist_user(self, user_id: str) -> bool:
        """Remove user from Setu whitelist."""
        ...

    # Setu group access control
    @abstractmethod
    async def is_setu_group_blocked(self, group_id: str) -> bool:
        """Check if group is in Setu blacklist."""
        ...

    @abstractmethod
    async def is_setu_group_whitelisted(self, group_id: str) -> bool:
        """Check if group is in Setu whitelist."""
        ...

    @abstractmethod
    async def add_setu_blocked_group(self, group_id: str) -> bool:
        """Add group to Setu blacklist."""
        ...

    @abstractmethod
    async def remove_setu_blocked_group(self, group_id: str) -> bool:
        """Remove group from Setu blacklist."""
        ...

    @abstractmethod
    async def add_setu_whitelist_group(self, group_id: str) -> bool:
        """Add group to Setu whitelist."""
        ...

    @abstractmethod
    async def remove_setu_whitelist_group(self, group_id: str) -> bool:
        """Remove group from Setu whitelist."""
        ...

    # Fortune user access control
    @abstractmethod
    async def is_fortune_user_blocked(self, user_id: str) -> bool:
        """Check if user is in Fortune blacklist."""
        ...

    @abstractmethod
    async def is_fortune_user_whitelisted(self, user_id: str) -> bool:
        """Check if user is in Fortune whitelist."""
        ...

    @abstractmethod
    async def add_fortune_blocked_user(self, user_id: str) -> bool:
        """Add user to Fortune blacklist."""
        ...

    @abstractmethod
    async def remove_fortune_blocked_user(self, user_id: str) -> bool:
        """Remove user from Fortune blacklist."""
        ...

    @abstractmethod
    async def add_fortune_whitelist_user(self, user_id: str) -> bool:
        """Add user to Fortune whitelist."""
        ...

    @abstractmethod
    async def remove_fortune_whitelist_user(self, user_id: str) -> bool:
        """Remove user from Fortune whitelist."""
        ...

    # Fortune group access control
    @abstractmethod
    async def is_fortune_group_blocked(self, group_id: str) -> bool:
        """Check if group is in Fortune blacklist."""
        ...

    @abstractmethod
    async def is_fortune_group_whitelisted(self, group_id: str) -> bool:
        """Check if group is in Fortune whitelist."""
        ...

    @abstractmethod
    async def add_fortune_blocked_group(self, group_id: str) -> bool:
        """Add group to Fortune blacklist."""
        ...

    @abstractmethod
    async def remove_fortune_blocked_group(self, group_id: str) -> bool:
        """Remove group from Fortune blacklist."""
        ...

    @abstractmethod
    async def add_fortune_whitelist_group(self, group_id: str) -> bool:
        """Add group to Fortune whitelist."""
        ...

    @abstractmethod
    async def remove_fortune_whitelist_group(self, group_id: str) -> bool:
        """Remove group from Fortune whitelist."""
        ...
