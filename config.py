"""Setu 插件配置解析和兼容性辅助模块。

提供配置读取、标签解析、以及新旧配置格式的兼容性支持。
"""

from __future__ import annotations

from typing import Any

from astrbot.api import logger
from astrbot.core import AstrBotConfig

from .constants import DEFAULT_TAG_ALIAS


class SetuConfig:
    """Setu 插件配置包装类。

    支持嵌套配置和旧版配置的兼容性处理，提供类型安全的配置访问方法。
    """

    def __init__(self, config: AstrBotConfig):
        """初始化配置包装器。

        参数:
            config: AstrBot 配置对象
        """
        self._cfg = config

    def _read(
        self,
        nested_path: tuple[str, ...],
        *legacy_keys: str,
        default: Any = None,
    ) -> Any:
        """读取配置值，支持嵌套路径和旧版键名回退。

        优先尝试嵌套路径读取，如果失败则尝试旧版键名，最后返回默认值。

        参数:
            nested_path: 嵌套配置路径，如 ("general", "api_type")
            *legacy_keys: 旧版配置键名，用于兼容性回退
            default: 默认值，读取失败时返回

        返回:
            配置值或默认值
        """
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

        # 尝试旧版键名
        for key in legacy_keys:
            try:
                value = self._cfg.get(key)
            except (KeyError, AttributeError):
                value = None
            if value is not None:
                return value
        return default

    @property
    def api_type(self) -> str:
        """API 提供商类型。

        返回:
            返回 API 类型：lolicon、sexnyan、custom 或 all
        """
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
        """多 API 策略。

        返回:
            返回策略类型：round_robin（轮询）、random（随机）、failover（故障转移）
        """
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
        """内容模式（分级）。

        返回:
            返回内容模式：sfw（全年龄）、r18（成人）、mix（混合）
        """
        mode = self._read(
            ("general", "content_mode"), "content_mode", "contentMode", default="sfw"
        )
        return mode if mode in ("sfw", "r18", "mix") else "sfw"

    @property
    def r18_docx_mode(self) -> bool:
        """R18 Docx 打包模式。

        返回:
            是否将 R18 图片打包到 docx 文件中
        """
        return _safe_bool(
            self._read(("delivery", "r18_docx_mode"), "r18_docx_mode", default=True),
            True,
        )

    @property
    def send_mode(self) -> str:
        """图片发送模式。

        返回:
            返回发送模式：image（直接发送）、forward（合并转发）、auto（自动）
        """
        mode = self._read(
            ("delivery", "send_mode"), "send_mode", "sendMode", default="image"
        )
        return mode if mode in ("image", "forward", "auto") else "image"

    @property
    def auto_handle_send_failure(self) -> bool:
        """自动处理发送失败。

        返回:
            发送失败时是否自动尝试 HTML 卡片降级发送
        """
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
        """自动撤回 R18 内容。

        返回:
            是否自动撤回 R18 图片/文件
        """
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
        """自动撤回延迟时间（秒）。

        返回:
            R18 内容发送后多久自动撤回
        """
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
        """HTML 卡片模式。

        返回:
            返回卡片模式：single（单张）、multiple（多张）
        """
        mode = self._read(("html_card", "mode"), "html_card_mode", default="single")
        return mode if mode in ("single", "multiple") else "single"

    @property
    def max_count(self) -> int:
        """每次请求最大图片数。

        返回:
            单次命令的上限
        """
        return _safe_int(
            self._read(("general", "max_count"), "max_count", "maxCount", default=10),
            10,
        )

    @property
    def exclude_ai(self) -> bool:
        """排除 AI 生成作品（仅 lolicon 生效）。

        返回:
            是否排除 AI 生成的图片
        """
        return _safe_bool(
            self._read(
                ("api", "lolicon", "exclude_ai"),
                "exclude_ai",
                "excludeAi",
                default=True,
            ),
            True,
        )

    @property
    def image_size(self) -> str:
        """图片尺寸（仅 lolicon 生效）。

        返回:
            返回图片尺寸：original（原图）、regular、small、thumb、mini
        """
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
        """图片代理主机（仅 lolicon 生效）。

        返回:
            代理服务器地址，默认 i.pixiv.re
        """
        return str(
            self._read(("api", "lolicon", "proxy"), "proxy", default="i.pixiv.re")
        )

    @property
    def aspect_ratio(self) -> str:
        """宽高比过滤（仅 lolicon 生效）。

        返回:
            返回宽高比：horizontal（横向）、vertical（纵向）、square（方形）
        """
        ratio = self._read(
            ("api", "lolicon", "aspect_ratio"), "aspect_ratio", default=""
        )
        return ratio if ratio in ("horizontal", "vertical", "square") else ""

    @property
    def uid(self) -> list[int]:
        """作者 UID 列表（仅 lolicon 生效）。

        返回:
            指定作者的 UID 列表，用于筛选特定作者的作品
        """
        uids = self._read(("api", "lolicon", "uid"), "uid", default=[])
        if isinstance(uids, list):
            return [_safe_int(uid, 0) for uid in uids if _safe_int(uid, 0) > 0]
        return []

    @property
    def keyword(self) -> str:
        """关键词过滤（仅 lolicon 生效）。

        返回:
            用于过滤图片的关键词
        """
        return str(self._read(("api", "lolicon", "keyword"), "keyword", default=""))

    @property
    def max_replenish_rounds(self) -> int:
        """最大补充轮次。

        返回:
            部分图片下载失败时的重试轮次
        """
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
        """是否启用 HTML 卡片包装。

        返回:
            是否将图片包装为 HTML 卡片以绕过审核
        """
        return _safe_bool(
            self._read(("html_card", "enabled"), "enable_html_card", default=False),
            False,
        )

    @property
    def html_card_padding(self) -> int:
        """HTML 卡片内边距。

        返回:
            卡片内部图片与边框的距离
        """
        return _safe_int(self._read(("html_card", "card_padding"), default=6), 6)

    @property
    def html_card_gap(self) -> int:
        """HTML 卡片间距。

        返回:
            多张图片之间的间距
        """
        return _safe_int(self._read(("html_card", "card_gap"), default=6), 6)

    @property
    def custom_api_configs(self) -> list[dict[str, Any]]:
        """自定义 API 配置列表。

        返回:
            用户自定义的 API 配置列表
        """
        configs = self._read(
            ("api", "custom_api_configs"), "custom_api_configs", default=[]
        )
        if isinstance(configs, list):
            return configs
        return []

    def get_custom_api_config(self, name: str | None = None) -> dict[str, Any] | None:
        """获取自定义 API 配置。

        参数:
            name: 配置名称，如果不指定则返回第一个配置

        返回:
            配置字典或 None
        """
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
        """自定义 API 基本信息。

        返回:
            包含 url、method、timeout 的字典
        """
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
        """API 响应解析器配置。

        返回:
            包含解析器类型和 JSON 路径的字典
        """
        cfg = self.get_custom_api_config()
        if cfg:
            return {
                "type": cfg.get("parser_type", "auto"),
                "json_path": cfg.get("json_path", ""),
            }
        return {"type": "auto", "json_path": ""}

    @property
    def blocked_groups(self) -> list[str]:
        """被屏蔽的群聊列表。

        返回:
            群聊 ID 列表，这些群聊将禁止使用插件功能
        """
        groups = self._read(("safety", "blocked_groups"), "blocked_groups", default=[])
        if isinstance(groups, list):
            return [str(g).strip() for g in groups if str(g).strip()]
        return []

    def is_group_blocked(self, group_id: str | None) -> bool:
        """检查群聊是否被屏蔽。

        参数:
            group_id: 群聊 ID

        返回:
            如果群聊被屏蔽返回 True，否则返回 False
        """
        if not group_id:
            return False
        return str(group_id) in self.blocked_groups

    @property
    def cache_enabled(self) -> bool:
        """是否启用图片缓存。

        返回:
            是否启用 URL 图片磁盘缓存
        """
        return _safe_bool(self._read(("cache", "enabled"), default=True), True)

    @property
    def cache_ttl_hours(self) -> int:
        """缓存 TTL（小时）。

        返回:
            缓存条目的存活时间
        """
        return _safe_int(self._read(("cache", "ttl_hours"), default=2), 2)

    @property
    def cache_max_items(self) -> int:
        """最大缓存条目数。

        返回:
            缓存最多保留的条目数量
        """
        return _safe_int(self._read(("cache", "max_items"), default=1), 1)

    @property
    def cache_cleanup_on_start(self) -> bool:
        """启动时清理缓存。

        返回:
            启动时是否自动清理过期缓存
        """
        return _safe_bool(self._read(("cache", "cleanup_on_start"), default=True), True)

    @property
    def tag_alias(self) -> dict[str, list[str]]:
        """标签别名映射。

        返回:
            标签到别名列表的映射字典
        """
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
        """解析并规范化标签字符串。

        将逗号或空格分隔的标签字符串解析为列表，并应用别名映射。

        参数:
            raw_tag: 原始标签字符串

        返回:
            规范化后的标签列表
        """
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
        """查找标签的标准名称。

        参数:
            tag: 标签名称（可能是别名）

        返回:
            标准标签名称，如果未找到返回 None
        """
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
        """是否启用获取中提示。

        返回:
            开始获取图片时是否发送提示消息
        """
        return _safe_bool(
            self._read(("messages", "fetching", "enabled"), default=True),
            True,
        )

    @property
    def msg_fetching_text(self) -> str:
        """获取中提示文本。

        返回:
            开始获取图片时显示的文本
        """
        return str(
            self._read(
                ("messages", "fetching", "text"),
                default="正在获取图片，请稍候...",
            )
        )

    @property
    def msg_found_enabled(self) -> bool:
        """是否启用找到图片提示。

        返回:
            成功找到图片后是否发送提示消息
        """
        return _safe_bool(
            self._read(("messages", "found", "enabled"), default=True),
            True,
        )

    @property
    def msg_found_text(self) -> str:
        """找到图片提示文本。

        返回:
            成功找到图片后显示的文本，可使用 {count} 占位符
        """
        return str(
            self._read(
                ("messages", "found", "text"),
                default="找到 {count} 张符合要求的图片~",
            )
        )

    @property
    def msg_send_failed_text(self) -> str:
        """发送失败提示文本。

        返回:
            图片发送失败时显示的文本
        """
        return str(
            self._read(
                ("messages", "send_failed", "text"),
                "msg_send_failed_text",
                default="图片发送失败，请稍后再试。",
            )
        )

    def format_found_message(self, count: int) -> str:
        """格式化找到图片的消息。

        将 msg_found_text 中的 {count} 占位符替换为实际数量。

        参数:
            count: 找到的图片数量

        返回:
            格式化后的消息文本
        """
        return self.msg_found_text.replace("{count}", str(count))


def _safe_int(value: Any, default: int) -> int:
    """安全地解析整数。

    参数:
        value: 待解析的值
        default: 解析失败时返回的默认值

    返回:
        解析后的正整数，失败返回默认值
    """
    try:
        parsed = int(value)
        return parsed if parsed > 0 else default
    except Exception:
        return default


def _safe_bool(value: Any, default: bool) -> bool:
    """安全地解析布尔值。

    支持布尔值和字符串形式的布尔值（如 "true", "yes", "1" 等）。

    参数:
        value: 待解析的值
        default: 解析失败时返回的默认值

    返回:
        解析后的布尔值，失败返回默认值
    """
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
    """解析阿拉伯数字或中文数字字符串。

    支持简单数字（如 "3"）和中文数字（如 "三"、"十五"、"二十三"）。
    解析失败返回 -1。

    参数:
        raw: 待解析的数字字符串

    返回:
        解析后的整数，失败返回 -1
    """
    from .utils import cn_to_an

    s = (raw or "").strip()
    if not s:
        return 1
    if s.isdigit():
        return int(s)
    # 尝试使用 utils 中的 cn_to_an 解析复杂中文数字
    try:
        result = cn_to_an(s)
        return result if result > 0 else -1
    except Exception:
        return -1
