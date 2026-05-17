"""Test configuration for AstrBot Setu plugin tests."""

from __future__ import annotations

import pytest


@pytest.fixture
def sample_access_policy():
    """Create sample access policy for testing."""
    from astrbot_plugin_setu.src.domain.access_control import AccessPolicy

    return AccessPolicy.for_session(
        user_id="test_user",
        group_id="test_group",
        user_mode="none",
        group_mode="none",
    )
