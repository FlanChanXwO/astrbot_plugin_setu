from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot_plugin_setu.main import SetuPlugin


def test_conf_schema_exposes_sexnyan_and_platform_transport_templates() -> None:
    schema_path = Path(__file__).resolve().parents[1] / "_conf_schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    delivery_items = schema["delivery"]["items"]
    assert "auto_revoke_r18" not in delivery_items
    assert delivery_items["auto_revoke_scope"]["default"] == "none"
    assert delivery_items["auto_revoke_scope"]["options"] == [
        "none",
        "sfw",
        "r18",
        "all",
    ]
    assert "doujinshi_file_cleanup_delay" not in delivery_items
    assert delivery_items["doujinshi_send_mode"]["default"] == "pdf"
    assert delivery_items["doujinshi_send_mode"]["options"] == [
        "pdf",
        "archive",
    ]
    assert delivery_items["doujinshi_max_page"]["default"] == 0
    assert delivery_items["auto_revoke_targets"]["default"] == ["doujinshi"]
    assert delivery_items["auto_revoke_targets"]["options"] == [
        "setu",
        "fortune",
        "doujinshi",
    ]
    assert delivery_items["auto_revoke_delay"]["default"] == 30

    transport_templates = delivery_items["platform_transports"]["templates"]
    napcat_items = transport_templates["napcat"]["items"]
    assert napcat_items["local_file_mode"]["default"] == "disabled"
    assert napcat_items["stream_chunk_kb"]["default"] == 64
    assert "WebSocket" in napcat_items["stream_chunk_kb"]["hint"]
    assert napcat_items["local_file_allowed_roots"]["default"] == []

    provider_templates = schema["api"]["items"]["provider_overrides"]["templates"]
    assert set(provider_templates["sexnyan"]["items"]) == {"proxy", "uid", "keyword"}

    message_items = schema["messages"]["items"]["message_overrides"]["templates"][
        "message"
    ]["items"]
    assert "revoke_scheduled" in message_items["message_key"]["options"]
    assert message_items["enabled"]["default"] is True
    assert message_items["text"]["default"].strip()


def test_dashboard_loads_bridge_before_app_script() -> None:
    dashboard_dir = Path(__file__).resolve().parents[1] / "pages" / "dashboard"
    html = (dashboard_dir / "index.html").read_text(encoding="utf-8")

    bridge_index = html.index("/api/plugin/page/bridge-sdk.js")
    app_index = html.index("./app.js")

    assert bridge_index < app_index


def test_dashboard_bridge_is_resolved_dynamically() -> None:
    app_js_path = Path(__file__).resolve().parents[1] / "pages" / "dashboard" / "app.js"
    app_js = app_js_path.read_text(encoding="utf-8")

    assert "var bridge = window.AstrBotPluginPage || null;" not in app_js
    assert "function getBridge()" in app_js
    assert "function waitForBridge()" in app_js
    assert "return window.AstrBotPluginPage || null;" in app_js
    assert "function bridgeReady()" in app_js
    assert "return bridgeReady().then(function (current)" in app_js
    assert "current.apiGet(path, params)" in app_js
    assert "current.apiPost(path, payload)" in app_js


def test_access_control_entry_form_is_modal_dialog() -> None:
    dashboard_dir = Path(__file__).resolve().parents[1] / "pages" / "dashboard"
    html = (dashboard_dir / "index.html").read_text(encoding="utf-8")

    access_tab_start = html.index('id="tab-accessControl"')
    modal_start = html.index('id="access-entry-modal"')
    access_main = html[access_tab_start:modal_start]
    modal_html = html[modal_start:]

    assert 'data-action="ac-open-create"' in access_main
    assert 'data-action="ac-save-entry"' not in access_main
    assert 'role="dialog"' in modal_html
    assert 'aria-modal="true"' in modal_html
    assert 'data-action="ac-save-entry"' in modal_html


def test_dashboard_nav_and_empty_state_stay_plain_and_compact() -> None:
    dashboard_dir = Path(__file__).resolve().parents[1] / "pages" / "dashboard"
    html = (dashboard_dir / "index.html").read_text(encoding="utf-8")
    nav_css = (dashboard_dir / "css" / "nav.css").read_text(encoding="utf-8")
    dashboard_css = (dashboard_dir / "css" / "dashboard.css").read_text(
        encoding="utf-8"
    )
    components_css = (dashboard_dir / "css" / "components.css").read_text(
        encoding="utf-8"
    )

    assert "📋" not in html
    assert "🛡" not in html
    assert "nav-icon" not in html
    assert ".nav-icon" not in nav_css
    assert "justify-content: flex-start" in nav_css
    assert ".table-section > .section-header .action-bar" in dashboard_css
    assert "width: 100%" in dashboard_css
    assert "border: 1px dashed" not in components_css


def test_setu_config_not_loaded_message_uses_resolver() -> None:
    source_path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "infrastructure"
        / "astrbot"
        / "commands"
        / "setu.py"
    )
    source = source_path.read_text(encoding="utf-8")

    assert 'plain_result("配置未加载")' not in source
    assert 'self._message("config_not_loaded")' in source


@pytest.mark.asyncio
async def test_initialize_uses_plugin_config_not_context_config(
    monkeypatch, tmp_path, sample_config_dict
) -> None:
    context = MagicMock()
    context.get_config.return_value = {
        "api": {
            "provider_overrides": [
                {"__template_key": "lolicon", "proxy": "wrong.example.com"}
            ]
        }
    }
    config = MagicMock()
    config.items.return_value = sample_config_dict.items()

    plugin = SetuPlugin(context, config)
    plugin.name = "astrbot_plugin_setu"

    captured: dict[str, object] = {}

    def fake_init_config(raw_config):
        captured["raw_config"] = raw_config
        overrides = {
            item["__template_key"]: item
            for item in raw_config["api"]["provider_overrides"]
        }
        return MagicMock(
            api_type="lolicon",
            custom_api_configs=[],
            multi_api_strategy="round_robin",
            proxy=overrides["lolicon"]["proxy"],
            image_size="original",
            aspect_ratio="",
            uid=[],
            keyword="",
            atri_proxy=overrides["atri"]["proxy"],
            atri_image_size="original",
            atri_aspect_ratio="",
            atri_uid=[],
            atri_keyword="",
            cache_enabled=True,
            cache_ttl_hours=2,
            cache_max_items=200,
            cache_cleanup_on_start=True,
        )

    monkeypatch.setattr("astrbot_plugin_setu.main.init_config", fake_init_config)
    monkeypatch.setattr(
        "astrbot_plugin_setu.main.set_plugin_context", lambda _ctx: None
    )
    monkeypatch.setattr(
        "astrbot_plugin_setu.main.StarTools.get_data_dir", lambda _name: str(tmp_path)
    )
    monkeypatch.setattr(
        "astrbot_plugin_setu.main.init_provider_from_config", lambda _cfg: None
    )
    monkeypatch.setattr(
        "astrbot_plugin_setu.main.init_access_control_repo", AsyncMock()
    )
    monkeypatch.setattr("astrbot_plugin_setu.main.init_fortune_repo", AsyncMock())
    monkeypatch.setattr(
        "astrbot_plugin_setu.main.init_session_config_repo", AsyncMock()
    )
    monkeypatch.setattr("astrbot_plugin_setu.main.init_send_cache", AsyncMock())
    monkeypatch.setattr("astrbot_plugin_setu.main.init_revoke_scheduler", AsyncMock())
    monkeypatch.setattr(
        "astrbot_plugin_setu.main.register_setu_llm_tools", lambda: None
    )
    monkeypatch.setattr(
        "astrbot_plugin_setu.main.register_fortune_llm_tools", lambda: None
    )
    monkeypatch.setattr(
        "astrbot_plugin_setu.main.register_session_config_llm_tools", lambda: None
    )

    await plugin.initialize()

    raw_config = captured["raw_config"]
    assert isinstance(raw_config, dict)
    captured_overrides = {
        item["__template_key"]: item for item in raw_config["api"]["provider_overrides"]
    }
    expected_overrides = {
        item["__template_key"]: item
        for item in sample_config_dict["api"]["provider_overrides"]
    }
    assert (
        captured_overrides["lolicon"]["proxy"] == expected_overrides["lolicon"]["proxy"]
    )
