"""Setu plugin configuration parsing and compatibility helpers."""

from __future__ import annotations

from typing import Any

from astrbot.api import logger
from astrbot.core import AstrBotConfig

from .constants import DEFAULT_TAG_ALIAS


class SetuConfig:
    """Configuration wrapper with nested-config and legacy-config compatibility."""

    def __init__(self, config: AstrBotConfig):
        self._cfg = config

    def _read(
        self,
        nested_path: tuple[str, ...],
        *legacy_keys: str,
        default: Any = None,
    ) -> Any:
        current: Any = self._cfg
        for key in nested_path:
            if isinstance(current, dict):
                current = current.get(key)
            elif hasattr(current, "get"):
                current = current.get(key)
            else:
                current = None
            if current is None:
                break

        if current is not None:
            return current

        for key in legacy_keys:
            try:
                value = self._cfg.get(key)
            except Exception:
                value = None
            if value is not None:
                return value
        return default

    @property
    def api_type(self) -> str:
        api_type = self._read(
            ("general", "api_type"), "api_type", "apiType", default="lolicon"
        )
        return (
            api_type
            if api_type in ("lolicon", "sexnyan", "custom", "all")
            else "lolicon"
        )

    @property
    def multi_api_strategy(self) -> str:
        strategy = self._read(
            ("general", "multi_api_strategy"),
            "multi_api_strategy",
            default="round_robin",
        )
        return (
            strategy
            if strategy in ("round_robin", "random", "failover")
            else "round_robin"
        )

    @property
    def content_mode(self) -> str:
        mode = self._read(
            ("general", "content_mode"), "content_mode", "contentMode", default="sfw"
        )
        return mode if mode in ("sfw", "r18", "mix") else "sfw"

    @property
    def r18_docx_mode(self) -> bool:
        return _safe_bool(
            self._read(("delivery", "r18_docx_mode"), "r18_docx_mode", default=True),
            True,
        )

    @property
    def send_mode(self) -> str:
        mode = self._read(
            ("delivery", "send_mode"), "send_mode", "sendMode", default="image"
        )
        return mode if mode in ("image", "forward", "auto") else "image"

    @property
    def auto_handle_send_failure(self) -> bool:
        return _safe_bool(
            self._read(
                ("delivery", "auto_handle_send_failure"),
                "auto_handle_send_failure",
                default=True,
            ),
            True,
        )

    @property
    def auto_revoke_r18(self) -> bool:
        return _safe_bool(
            self._read(
                ("delivery", "auto_revoke_r18"),
                "auto_revoke_r18",
                default=False,
            ),
            False,
        )

    @property
    def auto_revoke_delay(self) -> int:
        return _safe_int(
            self._read(
                ("delivery", "auto_revoke_delay"),
                "auto_revoke_delay",
                default=30,
            ),
            30,
        )

    @property
    def html_card_mode(self) -> str:
        mode = self._read(("html_card", "mode"), "html_card_mode", default="single")
        return mode if mode in ("single", "multiple") else "single"

    @property
    def max_count(self) -> int:
        return _safe_int(
            self._read(("general", "max_count"), "max_count", "maxCount", default=10),
            10,
        )

    @property
    def exclude_ai(self) -> bool:
        return _safe_bool(
            self._read(
                ("general", "exclude_ai"), "exclude_ai", "excludeAi", default=True
            ),
            True,
        )

    @property
    def image_size(self) -> str:
        size = self._read(
            ("api", "lolicon", "image_size"), "image_size", default="original"
        )
        return (
            size
            if size in ("original", "regular", "small", "thumb", "mini")
            else "original"
        )

    @property
    def proxy(self) -> str:
        return str(
            self._read(("api", "lolicon", "proxy"), "proxy", default="i.pixiv.re")
        )

    @property
    def aspect_ratio(self) -> str:
        ratio = self._read(
            ("api", "lolicon", "aspect_ratio"), "aspect_ratio", default=""
        )
        return ratio if ratio in ("horizontal", "vertical", "square") else ""

    @property
    def uid(self) -> list[int]:
        uids = self._read(("api", "lolicon", "uid"), "uid", default=[])
        if isinstance(uids, list):
            return [_safe_int(uid, 0) for uid in uids if _safe_int(uid, 0) > 0]
        return []

    @property
    def keyword(self) -> str:
        return str(self._read(("api", "lolicon", "keyword"), "keyword", default=""))

    @property
    def max_replenish_rounds(self) -> int:
        return _safe_int(
            self._read(
                ("general", "max_replenish_rounds"),
                "max_replenish_rounds",
                "maxReplenishRounds",
                default=3,
            ),
            3,
        )

    @property
    def enable_html_card(self) -> bool:
        return _safe_bool(
            self._read(("html_card", "enabled"), "enable_html_card", default=False),
            False,
        )

    @property
    def html_card_padding(self) -> int:
        return _safe_int(self._read(("html_card", "card_padding"), default=6), 6)

    @property
    def html_card_gap(self) -> int:
        return _safe_int(self._read(("html_card", "card_gap"), default=6), 6)

    @property
    def custom_api_configs(self) -> list[dict[str, Any]]:
        configs = self._read(
            ("api", "custom_api_configs"), "custom_api_configs", default=[]
        )
        if isinstance(configs, list):
            return configs
        return []

    def get_custom_api_config(self, name: str | None = None) -> dict[str, Any] | None:
        configs = self.custom_api_configs
        if not configs:
            return None

        if name:
            for cfg in configs:
                if cfg.get("name") == name:
                    return cfg
            return None
        return configs[0]

    @property
    def custom_api(self) -> dict[str, Any]:
        cfg = self.get_custom_api_config()
        if cfg:
            return {
                "url": cfg.get("url", ""),
                "method": cfg.get("method", "GET"),
                "timeout": _safe_int(cfg.get("timeout"), 30),
            }
        return {"url": "", "method": "GET", "timeout": 30}

    @property
    def api_response_parser(self) -> dict[str, Any]:
        cfg = self.get_custom_api_config()
        if cfg:
            return {
                "type": cfg.get("parser_type", "auto"),
                "json_path": cfg.get("json_path", ""),
            }
        return {"type": "auto", "json_path": ""}

    @property
    def blocked_groups(self) -> list[str]:
        groups = self._read(("safety", "blocked_groups"), "blocked_groups", default=[])
        if isinstance(groups, list):
            return [str(g).strip() for g in groups if str(g).strip()]
        return []

    def is_group_blocked(self, group_id: str | None) -> bool:
        if not group_id:
            return False
        return str(group_id) in self.blocked_groups

    @property
    def cache_enabled(self) -> bool:
        return _safe_bool(self._read(("cache", "enabled"), default=True), True)

    @property
    def cache_ttl_hours(self) -> int:
        return _safe_int(self._read(("cache", "ttl_hours"), default=2), 2)

    @property
    def cache_max_items(self) -> int:
        return _safe_int(self._read(("cache", "max_items"), default=1), 1)

    @property
    def cache_cleanup_on_start(self) -> bool:
        return _safe_bool(self._read(("cache", "cleanup_on_start"), default=True), True)

    @property
    def tag_alias(self) -> dict[str, list[str]]:
        alias_str = self._read(("safety", "tag_alias"), "tag_alias", default="")
        if not alias_str or not isinstance(alias_str, str):
            return DEFAULT_TAG_ALIAS

        result: dict[str, list[str]] = {}
        lines = alias_str.strip().replace("\r\n", "\n").split("\n")
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith(";"):
                continue

            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if not key or not value:
                continue
            aliases = [a.strip() for a in value.split(",") if a.strip()]
            if aliases:
                result[key] = aliases

        if not result:
            logger.debug("tag_alias parsing returned empty map, fallback to defaults")
            return DEFAULT_TAG_ALIAS
        return result

    def resolve_tags(self, raw_tag: str) -> list[str]:
        if not raw_tag:
            return []

        normalized = raw_tag.replace("，", ",").replace(" ", ",")
        tags = [t.strip() for t in normalized.split(",") if t.strip()]

        result: list[str] = []
        for tag in tags:
            canonical = self._find_canonical_tag(tag)
            result.append(canonical if canonical else tag)
        return result

    def _find_canonical_tag(self, tag: str) -> str | None:
        normalized = tag.lower()
        for canonical, aliases in self.tag_alias.items():
            if not isinstance(canonical, str):
                continue
            if normalized == canonical.lower():
                return canonical
            if isinstance(aliases, list):
                for alias in aliases:
                    if isinstance(alias, str) and normalized == alias.lower():
                        return canonical
        return None

    @property
    def msg_fetching_enabled(self) -> bool:
        return _safe_bool(
            self._read(("messages", "fetching", "enabled"), default=True),
            True,
        )

    @property
    def msg_fetching_text(self) -> str:
        return str(
            self._read(
                ("messages", "fetching", "text"),
                default="正在获取图片，请稍候...",
            )
        )

    @property
    def msg_found_enabled(self) -> bool:
        return _safe_bool(
            self._read(("messages", "found", "enabled"), default=True),
            True,
        )

    @property
    def msg_found_text(self) -> str:
        return str(
            self._read(
                ("messages", "found", "text"),
                default="找到 {count} 张符合要求的图片~",
            )
        )

    @property
    def msg_send_failed_text(self) -> str:
        return str(
            self._read(
                ("messages", "send_failed", "text"),
                "msg_send_failed_text",
                default="图片发送失败，请稍后再试。",
            )
        )

    def format_found_message(self, count: int) -> str:
        """格式化找到图片的消息，替换 {count} 占位符。"""
        return self.msg_found_text.replace("{count}", str(count))


def _safe_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
        return parsed if parsed > 0 else default
    except Exception:
        return default


def _safe_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return default


def parse_count(raw: str) -> int:
    """Parse Arabic/Chinese numeric strings. Return -1 on parse failure."""
    from .constants import CN_NUM

    s = (raw or "").strip()
    if not s:
        return 1
    if s.isdigit():
        return int(s)
    return CN_NUM.get(s, -1)
