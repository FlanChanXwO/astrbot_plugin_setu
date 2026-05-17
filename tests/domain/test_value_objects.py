"""Tests for domain value objects."""

from __future__ import annotations


from astrbot_plugin_setu.src.application.setu import ImagePayload
from astrbot_plugin_setu.src.domain.access_control import AccessPolicy
from astrbot_plugin_setu.src.domain.fortune import FortuneResult, FortuneSeed
from astrbot_plugin_setu.src.domain.setu import SetuRequest
from astrbot_plugin_setu.src.infrastructure.sending import SendOptions


class TestSetuRequest:
    """Test SetuRequest value object."""

    def test_from_user_input(self) -> None:
        """Test creating SetuRequest from user input."""
        request = SetuRequest.from_user_input(3, ["girl", "cute"], False)
        assert request.count == 3
        assert request.tags == ("girl", "cute")
        assert request.r18 is False
        assert request.exclude_ai is True

    def test_with_tags(self) -> None:
        """Test creating new request with different tags."""
        request = SetuRequest.from_user_input(1, ["girl"], False)
        new_request = request.with_tags(["cat", "cute"])
        assert new_request.count == 1
        assert new_request.tags == ("cat", "cute")
        assert new_request.r18 is False


class TestImagePayload:
    """Test ImagePayload value object."""

    def test_empty_payload(self) -> None:
        """Test empty payload detection."""
        payload = ImagePayload((), (), False, ())
        assert payload.is_empty
        assert payload.count == 0

    def test_payload_with_urls(self) -> None:
        """Test payload with URLs."""
        payload = ImagePayload(("url1", "url2"), (), False, ("tag1",))
        assert not payload.is_empty
        assert payload.count == 2

    def test_payload_with_bytes(self) -> None:
        """Test payload with bytes."""
        payload = ImagePayload((), (b"data1", b"data2"), False, ())
        assert not payload.is_empty
        assert payload.count == 2

    def test_payload_count_uses_max(self) -> None:
        """Test count uses max of URLs and bytes."""
        payload = ImagePayload(("url1", "url2"), (b"data1",), False, ())
        assert payload.count == 2


class TestAccessPolicy:
    """Test AccessPolicy value object."""

    def test_for_user(self) -> None:
        """Test creating policy for user."""
        policy = AccessPolicy.for_user("user123", "blacklist")
        assert policy.user_id == "user123"
        assert policy.group_id is None
        assert policy.user_mode == "blacklist"
        assert policy.group_mode == "none"

    def test_for_group(self) -> None:
        """Test creating policy for group."""
        policy = AccessPolicy.for_group("group456", "whitelist")
        assert policy.user_id is None
        assert policy.group_id == "group456"
        assert policy.user_mode == "none"
        assert policy.group_mode == "whitelist"

    def test_for_session(self) -> None:
        """Test creating policy for full session."""
        policy = AccessPolicy.for_session(
            "user123", "group456", "blacklist", "whitelist"
        )
        assert policy.user_id == "user123"
        assert policy.group_id == "group456"
        assert policy.user_mode == "blacklist"
        assert policy.group_mode == "whitelist"


class TestFortuneSeed:
    """Test FortuneSeed value object."""

    def test_for_today(self) -> None:
        """Test creating seed for today."""
        from datetime import date

        seed = FortuneSeed.for_today("user123")
        assert seed.user_id == "user123"
        assert seed.date_str == date.today().isoformat()

    def test_cache_key(self) -> None:
        """Test cache key generation."""
        seed = FortuneSeed("user123", "2026-05-09")
        assert seed.cache_key == "user123_2026-05-09"


class TestFortuneResult:
    """Test FortuneResult value object."""

    def test_max_stars(self) -> None:
        """Test max stars property."""
        seed = FortuneSeed("user123", "2026-05-09")
        result = FortuneResult(
            seed=seed,
            title="大吉",
            star_count=6,
            description="Lucky day!",
            extra_message="",
            theme_color="theme-red",
        )
        assert result.max_stars == 7
        assert result.star_count == 6


class TestSendOptions:
    """Test SendOptions value object."""

    def test_defaults(self) -> None:
        """Test default values."""
        options = SendOptions(
            send_mode="auto",
            use_html_card=False,
            auto_revoke=False,
            revoke_delay=30,
            r18_docx_mode=True,
        )
        assert options.send_mode == "auto"
        assert options.use_html_card is False
        assert options.auto_revoke is False
        assert options.revoke_delay == 30
        assert options.r18_docx_mode is True
        assert options.html_padding == 6
        assert options.html_gap == 6
