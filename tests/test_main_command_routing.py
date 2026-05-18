from __future__ import annotations

import re

from astrbot_plugin_setu.main import (
    FORTUNE_REGEX_PATTERN,
    _resolve_fortune_refresh_target,
    _resolve_fortune_toggle_action,
    _resolve_fortune_user_action,
)


def test_resolve_fortune_refresh_target_from_new_command(mock_event) -> None:
    mock_event.message_str = "/运势刷新 本群"
    assert _resolve_fortune_refresh_target(mock_event, "本群") == "group"


def test_resolve_fortune_refresh_target_from_legacy_alias(mock_event) -> None:
    mock_event.message_str = "/刷新全局今日运势"
    assert _resolve_fortune_refresh_target(mock_event, "") == "all"


def test_resolve_fortune_toggle_action_from_new_command(mock_event) -> None:
    mock_event.message_str = "/运势开关 关"
    assert _resolve_fortune_toggle_action(mock_event, "关") == "disable"


def test_resolve_fortune_toggle_action_from_legacy_alias(mock_event) -> None:
    mock_event.message_str = "/开启运势"
    assert _resolve_fortune_toggle_action(mock_event, "") == "enable"


def test_resolve_fortune_user_action_from_new_command(mock_event) -> None:
    mock_event.message_str = "/运势用户 拉黑 12345"
    assert _resolve_fortune_user_action(mock_event, "拉黑 12345") == ("block", "12345")


def test_resolve_fortune_user_action_from_legacy_alias(mock_event) -> None:
    mock_event.message_str = "/取消运势信任 12345"
    assert _resolve_fortune_user_action(mock_event, "12345") == ("untrust", "12345")


def test_fortune_regex_pattern_matches_plain_jrys() -> None:
    assert re.match(FORTUNE_REGEX_PATTERN, "jrys")
    assert re.match(FORTUNE_REGEX_PATTERN, "今日运势")
    assert not re.match(FORTUNE_REGEX_PATTERN, "/jrys")
