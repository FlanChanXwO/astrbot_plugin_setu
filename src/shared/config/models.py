"""Pydantic v2 configuration models for Setu plugin.

Replaces the ConfigBase + mixin chain with type-safe, validated models.
Each section mirrors the _conf_schema.json structure for WebUI compatibility.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ImageSize(str, Enum):
    """Valid image sizes for Lolicon/Atri APIs."""

    ORIGINAL = "original"
    REGULAR = "regular"
    SMALL = "small"
    THUMB = "thumb"
    MINI = "mini"


class AspectRatio(str, Enum):
    """Valid aspect ratios for filtering."""

    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"
    SQUARE = "square"


class ContentModeStr(str, Enum):
    """Content rating modes."""

    SFW = "sfw"
    R18 = "r18"
    MIX = "mix"


class ApiTypeStr(str, Enum):
    """API provider types."""

    LOLICON = "lolicon"
    ATRI = "atri"
    SEXNYAN = "sexnyan"
    CUSTOM = "custom"
    ALL = "all"


class MultiApiStrategyStr(str, Enum):
    """Multi-API strategy types."""

    ROUND_ROBIN = "round_robin"
    RANDOM = "random"
    FAILOVER = "failover"


class SendModeStr(str, Enum):
    """Image send modes."""

    IMAGE = "image"
    FORWARD = "forward"
    AUTO = "auto"


class NapcatStreamModeStr(str, Enum):
    """NapCat stream upload modes."""

    DISABLED = "disabled"
    FALLBACK = "fallback"
    ALWAYS = "always"


class HtmlCardStrategyStr(str, Enum):
    """HTML card strategies."""

    NEVER = "never"
    FALLBACK = "fallback"
    ALWAYS = "always"


class AccessControlModeStr(str, Enum):
    """Access control modes."""

    NONE = "none"
    BLACKLIST = "blacklist"
    WHITELIST = "whitelist"


class ProviderConfig(BaseModel):
    """Configuration for a single API provider (Lolicon or Atri)."""

    image_size: ImageSize = ImageSize.ORIGINAL
    proxy: str = "i.pixiv.re"
    aspect_ratio: AspectRatio | None = None
    uid: list[int] = Field(default_factory=list)
    keyword: str = ""
    exclude_ai: bool = True

    @field_validator("aspect_ratio", mode="before")
    @classmethod
    def normalize_empty_aspect_ratio(cls, value: Any) -> Any:
        """Treat empty-string aspect ratio from schema/config files as None."""
        if value == "":
            return None
        return value


class LoliconConfig(ProviderConfig):
    """Lolicon API specific configuration."""

    pass


class AtriConfig(ProviderConfig):
    """Atri API specific configuration."""

    pass


class CustomApiConfig(BaseModel):
    """Custom API configuration."""

    name: str = "My custom API"
    url: str = ""
    method: str = "GET"
    timeout: int = 30
    parser_type: str = "auto"
    json_path: str = ""


class SetuGeneralConfig(BaseModel):
    """Setu general configuration."""

    api_type: ApiTypeStr = ApiTypeStr.LOLICON
    multi_api_strategy: MultiApiStrategyStr = MultiApiStrategyStr.ROUND_ROBIN
    content_mode: ContentModeStr = ContentModeStr.SFW
    max_count: int = Field(default=10, ge=1, le=10)
    max_replenish_rounds: int = Field(default=3, ge=1, le=3)
    tag_alias: str = ""


class DeliveryConfig(BaseModel):
    """Image delivery configuration."""

    send_mode: SendModeStr = SendModeStr.IMAGE
    r18_docx_mode: bool = True
    auto_handle_send_failure: bool = True
    auto_revoke_r18: bool = False
    auto_revoke_delay: int = Field(default=30, ge=5, le=300)
    napcat_stream_mode: NapcatStreamModeStr = NapcatStreamModeStr.FALLBACK


class HtmlCardConfig(BaseModel):
    """HTML card wrapping configuration."""

    strategy: HtmlCardStrategyStr = HtmlCardStrategyStr.FALLBACK
    mode: str = "single"
    card_padding: int = Field(default=6, ge=0, le=30)
    card_gap: int = Field(default=6, ge=0, le=30)


class FortuneConfig(BaseModel):
    """Fortune (Today's Luck) configuration."""

    enabled: bool = True
    api_type: str = "inherit"
    tags: str = ""
    content_mode: ContentModeStr = ContentModeStr.SFW
    allow_user_refresh: bool = False
    auto_refresh: bool = True


class CacheConfig(BaseModel):
    """Disk cache used before adapter-level image sending."""

    enabled: bool = True
    ttl_hours: int = Field(default=2, ge=1, le=168)
    max_items: int = Field(default=200, ge=1, le=1000)
    cleanup_on_start: bool = True


class PerformanceConfig(BaseModel):
    """Performance tuning configuration."""

    enable_range_download: bool = False
    range_segments: int = Field(default=3, ge=2, le=6)
    range_download_threshold: int = Field(default=512, ge=256, le=2048)
    download_concurrent_limit: int = Field(default=10, ge=1, le=50)
    download_timeout_seconds: int = Field(default=30, ge=5, le=120)


class MessagesFetchingConfig(BaseModel):
    """Fetching message configuration."""

    enabled: bool = True
    text: str = "正在获取图片，请稍候..."


class MessagesFoundConfig(BaseModel):
    """Found message configuration."""

    enabled: bool = True
    text: str = "找到 {count} 张符合要求的图片~"


class MessagesSendFailedConfig(BaseModel):
    """Send failed message configuration."""

    enabled: bool = True
    text: str = "图片发送失败，请稍后再试。"


class MessageTextConfig(BaseModel):
    """Generic user-facing message configuration."""

    enabled: bool = True
    text: str = ""


class MessagesConfig(BaseModel):
    """User-facing message configuration."""

    fetching: MessagesFetchingConfig = Field(default_factory=MessagesFetchingConfig)
    found: MessagesFoundConfig = Field(default_factory=MessagesFoundConfig)
    send_failed: MessagesSendFailedConfig = Field(
        default_factory=MessagesSendFailedConfig
    )
    rate_limited: MessageTextConfig = Field(
        default_factory=lambda: MessageTextConfig(
            text="你有一个请求正在处理中，请稍后再试~"
        )
    )
    config_not_loaded: MessageTextConfig = Field(
        default_factory=lambda: MessageTextConfig(text="配置未加载")
    )
    invalid_count: MessageTextConfig = Field(
        default_factory=lambda: MessageTextConfig(
            text="数量解析失败，图片数量必须在{min_count}-{max_count}之间"
        )
    )
    max_count_exceeded: MessageTextConfig = Field(
        default_factory=lambda: MessageTextConfig(
            text="一次最多只能获取{max_count}张哦~"
        )
    )
    count_out_of_range: MessageTextConfig = Field(
        default_factory=lambda: MessageTextConfig(
            text="图片数量必须在{min_count}-{max_count}之间哦~"
        )
    )
    fetch_timeout: MessageTextConfig = Field(
        default_factory=lambda: MessageTextConfig(
            text="获取图片超时，网络可能不稳定，请稍后再试。"
        )
    )
    fetch_failed: MessageTextConfig = Field(
        default_factory=lambda: MessageTextConfig(text="获取图片失败，请稍后再试")
    )
    no_result: MessageTextConfig = Field(
        default_factory=lambda: MessageTextConfig(
            text="未找到{tags_info}符合要求的图片~"
        )
    )
    empty_payload: MessageTextConfig = Field(
        default_factory=lambda: MessageTextConfig(text="运气不好，一张图都没拿到...")
    )
    r18_docx_failed: MessageTextConfig = Field(
        default_factory=lambda: MessageTextConfig(
            text="R18 Docx 封装失败，请稍后再试或联系管理员。"
        )
    )
    fortune_config_not_loaded: MessageTextConfig = Field(
        default_factory=lambda: MessageTextConfig(text="配置未加载")
    )
    fortune_group_only: MessageTextConfig = Field(
        default_factory=lambda: MessageTextConfig(text="此命令仅支持群聊")
    )
    fortune_missing_user_id: MessageTextConfig = Field(
        default_factory=lambda: MessageTextConfig(text="请指定用户ID")
    )
    fortune_get_failed: MessageTextConfig = Field(
        default_factory=lambda: MessageTextConfig(text="获取运势失败: {error}")
    )
    fortune_refresh_failed: MessageTextConfig = Field(
        default_factory=lambda: MessageTextConfig(text="刷新运势失败: {error}")
    )
    fortune_refresh_group_failed: MessageTextConfig = Field(
        default_factory=lambda: MessageTextConfig(text="刷新群运势失败: {error}")
    )
    fortune_refresh_all_failed: MessageTextConfig = Field(
        default_factory=lambda: MessageTextConfig(text="刷新全局运势失败: {error}")
    )
    fortune_refresh_group_done: MessageTextConfig = Field(
        default_factory=lambda: MessageTextConfig(
            text="已刷新本群 {count} 位用户的今日运势"
        )
    )
    fortune_refresh_all_done: MessageTextConfig = Field(
        default_factory=lambda: MessageTextConfig(
            text="已刷新全局 {count} 位用户的今日运势"
        )
    )
    fortune_enabled_group_done: MessageTextConfig = Field(
        default_factory=lambda: MessageTextConfig(text="运势功能已开启")
    )
    fortune_disabled_group_done: MessageTextConfig = Field(
        default_factory=lambda: MessageTextConfig(text="运势功能已关闭")
    )
    fortune_block_user_done: MessageTextConfig = Field(
        default_factory=lambda: MessageTextConfig(
            text="用户 {user_id} 已添加到运势黑名单"
        )
    )
    fortune_unblock_user_done: MessageTextConfig = Field(
        default_factory=lambda: MessageTextConfig(
            text="用户 {user_id} 已从运势黑名单移除"
        )
    )
    fortune_trust_user_done: MessageTextConfig = Field(
        default_factory=lambda: MessageTextConfig(
            text="用户 {user_id} 已添加到运势白名单"
        )
    )
    fortune_untrust_user_done: MessageTextConfig = Field(
        default_factory=lambda: MessageTextConfig(
            text="用户 {user_id} 已从运势白名单移除"
        )
    )


class SafetyConfig(BaseModel):
    """Safety and access control configuration."""

    setu_user_access_control_mode: AccessControlModeStr = AccessControlModeStr.NONE
    setu_group_access_control_mode: AccessControlModeStr = AccessControlModeStr.NONE
    setu_blocked_users: list[str] = Field(default_factory=list)
    setu_whitelist_users: list[str] = Field(default_factory=list)
    setu_blocked_groups: list[str] = Field(default_factory=list)
    setu_whitelist_groups: list[str] = Field(default_factory=list)
    fortune_user_access_control_mode: AccessControlModeStr = AccessControlModeStr.NONE
    fortune_group_access_control_mode: AccessControlModeStr = AccessControlModeStr.NONE
    fortune_blocked_users: list[str] = Field(default_factory=list)
    fortune_whitelist_users: list[str] = Field(default_factory=list)
    fortune_blocked_groups: list[str] = Field(default_factory=list)
    fortune_whitelist_groups: list[str] = Field(default_factory=list)


class SessionTemplateItem(BaseModel):
    """Session configuration template item."""

    session_id: str = ""
    session_type: str = "group"
    content_mode: str = ""
    r18_docx_mode: str = ""
    auto_revoke_r18: str = ""
    send_mode: str = ""


class FortuneSessionTemplateItem(BaseModel):
    """Fortune session configuration template item."""

    session_id: str = ""
    session_type: str = "group"
    tags: str = ""
    content_mode: str = ""


class ApiSectionConfig(BaseModel):
    """API section configuration."""

    lolicon: LoliconConfig = Field(default_factory=LoliconConfig)
    atri: AtriConfig = Field(default_factory=AtriConfig)
    custom_api_configs: list[CustomApiConfig] = Field(default_factory=list)


class SetuPluginConfig(BaseModel):
    """Root Pydantic model for Setu plugin configuration.

    This replaces the ConfigBase + mixin chain with a single validated model.
    The structure mirrors _conf_schema.json for WebUI compatibility.

    The model can be instantiated directly from AstrBotConfig dict:
        config = SetuPluginConfig(**astrbot_config)
    """

    setu_general: SetuGeneralConfig = Field(default_factory=SetuGeneralConfig)
    delivery: DeliveryConfig = Field(default_factory=DeliveryConfig)
    html_card: HtmlCardConfig = Field(default_factory=HtmlCardConfig)
    fortune: FortuneConfig = Field(default_factory=FortuneConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    api: ApiSectionConfig = Field(default_factory=ApiSectionConfig)
    messages: MessagesConfig = Field(default_factory=MessagesConfig)
    safety: SafetyConfig = Field(default_factory=SafetyConfig)
    performance: PerformanceConfig = Field(default_factory=PerformanceConfig)
    session_configs: list[SessionTemplateItem] = Field(default_factory=list)
    fortune_session_configs: list[FortuneSessionTemplateItem] = Field(
        default_factory=list
    )

    @field_validator("session_configs")
    @classmethod
    def validate_session_configs(
        cls, v: list[SessionTemplateItem]
    ) -> list[SessionTemplateItem]:
        """Validate session configurations."""
        for item in v:
            if item.session_type not in ("group", "private"):
                raise ValueError(f"Invalid session_type: {item.session_type}")
        return v

    @field_validator("fortune_session_configs")
    @classmethod
    def validate_fortune_session_configs(
        cls, v: list[FortuneSessionTemplateItem]
    ) -> list[FortuneSessionTemplateItem]:
        """Validate fortune session configurations."""
        for item in v:
            if item.session_type not in ("group", "private"):
                raise ValueError(f"Invalid session_type: {item.session_type}")
        return v

    # Convenience properties for backward compatibility
    @property
    def api_type(self) -> str:
        """Get API type."""
        return self.setu_general.api_type.value

    @property
    def multi_api_strategy(self) -> str:
        """Get multi-API strategy."""
        return self.setu_general.multi_api_strategy.value

    @property
    def content_mode(self) -> str:
        """Get content mode."""
        return self.setu_general.content_mode.value

    @property
    def max_count(self) -> int:
        """Get max count."""
        return self.setu_general.max_count

    @property
    def max_replenish_rounds(self) -> int:
        """Get max replenish rounds."""
        return self.setu_general.max_replenish_rounds

    @property
    def tag_alias(self) -> str:
        """Get tag alias string."""
        return self.setu_general.tag_alias

    @property
    def send_mode(self) -> str:
        """Get send mode."""
        return self.delivery.send_mode.value

    @property
    def r18_docx_mode(self) -> bool:
        """Get R18 DOCX mode."""
        return self.delivery.r18_docx_mode

    @property
    def auto_revoke_r18(self) -> bool:
        """Get auto-revoke R18."""
        return self.delivery.auto_revoke_r18

    @property
    def auto_revoke_delay(self) -> int:
        """Get auto-revoke delay."""
        return self.delivery.auto_revoke_delay

    @property
    def napcat_stream_mode(self) -> str:
        """Get NapCat stream upload mode."""
        return self.delivery.napcat_stream_mode.value

    @property
    def html_card_strategy(self) -> str:
        """Get HTML card strategy."""
        return self.html_card.strategy.value

    @property
    def html_card_padding(self) -> int:
        """Get HTML card padding."""
        return self.html_card.card_padding

    @property
    def html_card_gap(self) -> int:
        """Get HTML card gap."""
        return self.html_card.card_gap

    @property
    def cache_enabled(self) -> bool:
        """Get cache enabled."""
        return self.cache.enabled

    @property
    def cache_ttl_hours(self) -> int:
        """Get cache TTL hours."""
        return self.cache.ttl_hours

    @property
    def cache_max_items(self) -> int:
        """Get cache max items."""
        return self.cache.max_items

    @property
    def cache_cleanup_on_start(self) -> bool:
        """Get cache cleanup on start."""
        return self.cache.cleanup_on_start

    @property
    def download_concurrent_limit(self) -> int:
        """Get download concurrent limit."""
        return self.performance.download_concurrent_limit

    @property
    def download_timeout_seconds(self) -> int:
        """Get download timeout seconds."""
        return self.performance.download_timeout_seconds

    @property
    def enable_range_download(self) -> bool:
        """Get enable range download."""
        return self.performance.enable_range_download

    @property
    def range_segments(self) -> int:
        """Get range segments."""
        return self.performance.range_segments

    @property
    def range_threshold(self) -> int:
        """Get range threshold."""
        return self.performance.range_download_threshold

    @property
    def exclude_ai(self) -> bool:
        """Get exclude AI."""
        return self.api.lolicon.exclude_ai

    @property
    def image_size(self) -> str:
        """Get image size."""
        return self.api.lolicon.image_size.value

    @property
    def proxy(self) -> str:
        """Get proxy."""
        return self.api.lolicon.proxy

    @property
    def aspect_ratio(self) -> str:
        """Get aspect ratio."""
        return (
            self.api.lolicon.aspect_ratio.value if self.api.lolicon.aspect_ratio else ""
        )

    @property
    def uid(self) -> list[int]:
        """Get UID list."""
        return self.api.lolicon.uid

    @property
    def keyword(self) -> str:
        """Get keyword."""
        return self.api.lolicon.keyword

    @property
    def atri_image_size(self) -> str:
        """Get Atri image size."""
        return self.api.atri.image_size.value

    @property
    def atri_proxy(self) -> str:
        """Get Atri proxy."""
        return self.api.atri.proxy

    @property
    def atri_aspect_ratio(self) -> str:
        """Get Atri aspect ratio."""
        return self.api.atri.aspect_ratio.value if self.api.atri.aspect_ratio else ""

    @property
    def atri_uid(self) -> list[int]:
        """Get Atri UID list."""
        return self.api.atri.uid

    @property
    def atri_keyword(self) -> str:
        """Get Atri keyword."""
        return self.api.atri.keyword

    @property
    def atri_exclude_ai(self) -> bool:
        """Get Atri exclude AI."""
        return self.api.atri.exclude_ai

    @property
    def fortune_api_type(self) -> str:
        """Get fortune API type."""
        return self.fortune.api_type

    @property
    def custom_api(self) -> dict[str, Any]:
        """Get custom API config."""
        if self.api.custom_api_configs:
            cfg = self.api.custom_api_configs[0]
            return {
                "url": cfg.url,
                "method": cfg.method,
                "timeout": cfg.timeout,
            }
        return {"url": "", "method": "GET", "timeout": 30}

    @property
    def api_response_parser(self) -> dict[str, Any]:
        """Get API response parser config."""
        if self.api.custom_api_configs:
            cfg = self.api.custom_api_configs[0]
            return {
                "type": cfg.parser_type,
                "json_path": cfg.json_path,
            }
        return {"type": "auto", "json_path": ""}

    @property
    def custom_api_configs(self) -> list[dict[str, Any]]:
        """Get custom API configs."""
        return [cfg.model_dump() for cfg in self.api.custom_api_configs]

    def get_custom_api_config(self, name: str | None = None) -> dict[str, Any] | None:
        """Get custom API config by name."""
        configs = self.api.custom_api_configs
        if not configs:
            return None
        if name:
            for cfg in configs:
                if cfg.name == name:
                    return cfg.model_dump()
            return None
        return configs[0].model_dump()

    @property
    def msg_fetching_enabled(self) -> bool:
        """Get fetching message enabled."""
        return self.messages.fetching.enabled

    @property
    def msg_fetching_text(self) -> str:
        """Get fetching message text."""
        return self.messages.fetching.text

    @property
    def msg_found_enabled(self) -> bool:
        """Get found message enabled."""
        return self.messages.found.enabled

    @property
    def msg_found_text(self) -> str:
        """Get found message text."""
        return self.messages.found.text

    @property
    def msg_send_failed_text(self) -> str:
        """Get send failed message text."""
        return self.messages.send_failed.text

    @property
    def msg_send_failed_enabled(self) -> bool:
        """Get send failed message enabled."""
        return self.messages.send_failed.enabled

    def resolve_message(self, key: str, **kwargs: Any) -> str | None:
        """Resolve configured message text by key with placeholder substitution."""
        if key == "fetching":
            if not self.msg_fetching_enabled:
                return None
            text = self.msg_fetching_text
        elif key == "found":
            if not self.msg_found_enabled:
                return None
            text = self.msg_found_text
        elif key == "send_failed":
            if not self.msg_send_failed_enabled:
                return None
            text = self.msg_send_failed_text
        else:
            item = getattr(self.messages, key, None)
            if not item or not getattr(item, "enabled", True):
                return None
            text = str(getattr(item, "text", "") or "")

        result = str(text)
        for k, v in kwargs.items():
            result = result.replace(f"{{{k}}}", str(v))
        return result

    @property
    def setu_user_access_control_mode(self) -> str:
        """Get Setu user access control mode."""
        return self.safety.setu_user_access_control_mode.value

    @property
    def setu_group_access_control_mode(self) -> str:
        """Get Setu group access control mode."""
        return self.safety.setu_group_access_control_mode.value

    @property
    def fortune_user_access_control_mode(self) -> str:
        """Get Fortune user access control mode."""
        return self.safety.fortune_user_access_control_mode.value

    @property
    def fortune_group_access_control_mode(self) -> str:
        """Get Fortune group access control mode."""
        return self.safety.fortune_group_access_control_mode.value

    def format_found_message(self, count: int, revoke_delay: int | None = None) -> str:
        """Format found message with placeholders."""
        result = self.msg_found_text.replace("{count}", str(count))
        if revoke_delay is not None:
            result = result.replace("{revoke_delay}", str(revoke_delay))
        return result

    def get_effective_fortune_api_type(self) -> str:
        """Get effective fortune API type."""
        fortune_api = self.fortune.api_type
        if fortune_api == "inherit":
            return self.api_type
        return fortune_api
