"""Domain service for access control logic.

Centralizes access control decisions that were previously duplicated
across SetuCore, CommandHandler, and FortuneCommandHandler.
"""

from __future__ import annotations

from ...application.ports import AccessControlRepository
from .value_objects import AccessPolicy


class AccessControlService:
    """Domain service for access control decisions.

    Provides a single place for access control logic, eliminating
    duplication across SetuCore, CommandHandler, and FortuneCommandHandler.
    """

    def __init__(self, repository: AccessControlRepository) -> None:
        """Initialize access control service.

        Args:
            repository: Repository for accessing blacklist/whitelist data
        """
        self._repo = repository

    async def check_setu_access(self, policy: AccessPolicy) -> tuple[bool, str | None]:
        """Check if Setu access is allowed.

        Args:
            policy: Access policy containing user/group IDs and modes

        Returns:
            Tuple of (allowed, denial_reason). If allowed=True, reason is None.
        """
        return await self._check_access(
            policy,
            user_blacklist_fn=self._repo.is_setu_user_blocked,
            user_whitelist_fn=self._repo.is_setu_user_whitelisted,
            group_blacklist_fn=self._repo.is_setu_group_blocked,
            group_whitelist_fn=self._repo.is_setu_group_whitelisted,
            feature_name="setu",
        )

    async def check_fortune_access(
        self, policy: AccessPolicy
    ) -> tuple[bool, str | None]:
        """Check if Fortune access is allowed.

        Args:
            policy: Access policy containing user/group IDs and modes

        Returns:
            Tuple of (allowed, denial_reason). If allowed=True, reason is None.
        """
        return await self._check_access(
            policy,
            user_blacklist_fn=self._repo.is_fortune_user_blocked,
            user_whitelist_fn=self._repo.is_fortune_user_whitelisted,
            group_blacklist_fn=self._repo.is_fortune_group_blocked,
            group_whitelist_fn=self._repo.is_fortune_group_whitelisted,
            feature_name="fortune",
        )

    async def _check_access(
        self,
        policy: AccessPolicy,
        user_blacklist_fn,
        user_whitelist_fn,
        group_blacklist_fn,
        group_whitelist_fn,
        feature_name: str,
    ) -> tuple[bool, str | None]:
        """Internal access check implementation.

        Args:
            policy: Access policy
            user_blacklist_fn: Async function to check if user is blacklisted
            user_whitelist_fn: Async function to check if user is whitelisted
            group_blacklist_fn: Async function to check if group is blacklisted
            group_whitelist_fn: Async function to check if group is whitelisted
            feature_name: Feature name for logging

        Returns:
            Tuple of (allowed, denial_reason)
        """
        from astrbot.api import logger

        # Check user access control
        if policy.user_id is not None:
            uid = str(policy.user_id)

            if policy.user_mode == "blacklist":
                if await user_blacklist_fn(uid):
                    logger.info(
                        "[%s] Access denied for user=%s: blacklist mode",
                        feature_name,
                        uid,
                    )
                    return False, "用户被禁用"

            elif policy.user_mode == "whitelist":
                if not await user_whitelist_fn(uid):
                    logger.info(
                        "[%s] Access denied for user=%s: not in whitelist",
                        feature_name,
                        uid,
                    )
                    return False, "用户不在白名单中"

        # Check group access control
        if policy.group_id is not None:
            gid = str(policy.group_id)

            if policy.group_mode == "blacklist":
                if await group_blacklist_fn(gid):
                    logger.info(
                        "[%s] Access denied for group=%s: blacklist mode",
                        feature_name,
                        gid,
                    )
                    return False, "群组被禁用"

            elif policy.group_mode == "whitelist":
                if not await group_whitelist_fn(gid):
                    logger.info(
                        "[%s] Access denied for group=%s: not in whitelist",
                        feature_name,
                        gid,
                    )
                    return False, "群组不在白名单中"

        return True, None
