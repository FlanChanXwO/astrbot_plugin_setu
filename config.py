"""Setu 插件的配置解析和管理。"""

from __future__ import annotations

from typing import Any

from astrbot.core import AstrBotConfig
from astrbot.api import logger

from .constants import DEFAULT_TAG_ALIAS


class SetuConfig:
    """配置包装类，提供类型安全的配置访问。"""

    def __init__(self,config: AstrBotConfig):
        self._cfg = config

    @property
    def api_type(self) -> str:
        """API 提供商类型：'lolicon'、'sexnyan'、'custom' 或 'all'。"""
        api_type = self._cfg.get("api_type", self._cfg.get("apiType", "lolicon"))
        return api_type if api_type in ("lolicon", "sexnyan", "custom", "all") else "lolicon"

    @property
    def multi_api_strategy(self) -> str:
        """多 API 策略：'round_robin'、'random' 或 'failover'。"""
        strategy = self._cfg.get("multi_api_strategy", "round_robin")
        return strategy if strategy in ("round_robin", "random", "failover") else "round_robin"

    @property
    def content_mode(self) -> str:
        """内容模式：'sfw'（和谐）、'r18'（成人）或 'mix'（混合）。"""
        return self._cfg.get("content_mode", self._cfg.get("contentMode", "sfw"))

    @property
    def r18_docx_mode(self) -> bool:
        """R18 图片是否使用 Docx 封装发送。"""
        return _safe_bool(self._cfg.get("r18_docx_mode"), True)

    @property
    def send_mode(self) -> str:
        """发送模式：'image'（直接发送）、'forward'（模拟转发）或 'auto'（自动选择）。"""
        mode = self._cfg.get("send_mode", self._cfg.get("sendMode", "image"))
        return mode if mode in ("image", "forward", "auto") else "image"

    @property
    def html_card_mode(self) -> str:
        """HTML卡片模式：'single'（多图合一）或 'multiple'（单图单卡片合并转发）。"""
        mode = self._cfg.get("html_card_mode", "single")
        return mode if mode in ("single", "multiple") else "single"

    @property
    def max_count(self) -> int:
        """每次请求的最大图片数量。"""
        return _safe_int(self._cfg.get("max_count", self._cfg.get("maxCount", 10)), 10)

    @property
    def exclude_ai(self) -> bool:
        """是否排除 AI 生成的作品（仅 Lolicon API 有效）。"""
        return _safe_bool(
            self._cfg.get("exclude_ai", self._cfg.get("excludeAi", True)), True
        )

    @property
    def image_size(self) -> str:
        """图片规格：'original'、'regular'、'small'、'thumb'、'mini'（仅 Lolicon API 有效）。"""
        size = self._cfg.get("image_size", "original")
        return size if size in ("original", "regular", "small", "thumb", "mini") else "original"

    @property
    def proxy(self) -> str:
        """图片反代服务（仅 Lolicon API 有效）。"""
        return self._cfg.get("proxy", "i.pixiv.re")

    @property
    def aspect_ratio(self) -> str:
        """图片长宽比（仅 Lolicon API 有效）。"""
        ratio = self._cfg.get("aspect_ratio", "")
        return ratio if ratio in ("horizontal", "vertical", "square") else ""

    @property
    def uid(self) -> list[int]:
        """指定作者 UID 列表（仅 Lolicon API 有效）。"""
        uids = self._cfg.get("uid", [])
        if isinstance(uids, list):
            return [_safe_int(uid, 0) for uid in uids if _safe_int(uid, 0) > 0]
        return []

    @property
    def keyword(self) -> str:
        """关键词搜索（仅 Lolicon API 有效）。"""
        return str(self._cfg.get("keyword", ""))

    @property
    def max_replenish_rounds(self) -> int:
        """下载失败时的最大补充轮数。"""
        return _safe_int(
            self._cfg.get("max_replenish_rounds", self._cfg.get("maxReplenishRounds", 3)),
            3,
        )

    @property
    def enable_html_card(self) -> bool:
        """是否启用 HTML 卡片包装（防审核）。"""
        return _safe_bool(self._cfg.get("enable_html_card"), False)

    @property
    def custom_api_configs(self) -> list[dict[str, Any]]:
        """自定义 API 配置列表（template_list 格式）。"""
        configs = self._cfg.get("custom_api_configs", [])
        if isinstance(configs, list):
            return configs
        return []

    def get_custom_api_config(self, name: str | None = None) -> dict[str, Any] | None:
        """获取指定名称的自定义 API 配置，或返回第一个可用的配置。"""
        configs = self.custom_api_configs
        if not configs:
            return None

        if name:
            for cfg in configs:
                if cfg.get("name") == name:
                    return cfg
            return None

        # 返回第一个配置
        return configs[0] if configs else None

    @property
    def custom_api(self) -> dict[str, Any]:
        """兼容旧的自定义 API 配置获取方式，返回第一个配置或空配置。"""
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
        """API 响应解析配置。"""
        cfg = self.get_custom_api_config()
        if cfg:
            return {
                "type": cfg.get("parser_type", "auto"),
                "json_path": cfg.get("json_path", ""),
            }
        return {"type": "auto", "json_path": ""}

    @property
    def blocked_groups(self) -> list[str]:
        """屏蔽的群聊列表。"""
        groups = self._cfg.get("blocked_groups", [])
        if isinstance(groups, list):
            return [str(g).strip() for g in groups if str(g).strip()]
        return []

    def is_group_blocked(self, group_id: str | None) -> bool:
        """检查群聊是否被屏蔽。"""
        if not group_id:
            return False
        return str(group_id) in self.blocked_groups

    @property
    def tag_alias(self) -> dict[str, list[str]]:
        """标签别名映射配置。

        从 INI 格式文本解析：
        白丝=白丝,白絲,white stockings
        萝莉=萝莉,loli
        """
        alias_str = self._cfg.get("tag_alias", "")
        logger.info("[tag_alias] 读取原始配置: %r", alias_str)

        if not alias_str or not isinstance(alias_str, str):
            logger.info("[tag_alias] 配置为空，使用默认值")
            return DEFAULT_TAG_ALIAS

        result = {}
        # 统一处理换行符（支持 \n 和 \r\n）
        lines = alias_str.strip().replace('\r\n', '\n').split('\n')
        logger.info("[tag_alias] 解析行数: %d", len(lines))

        for line in lines:
            line = line.strip()
            # 跳过空行和注释
            if not line or line.startswith('#') or line.startswith(';'):
                continue

            # 解析 key=value 格式
            if '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()

                if key and value:
                    # 值是逗号分隔的别名列表
                    aliases = [a.strip() for a in value.split(',') if a.strip()]
                    if aliases:
                        result[key] = aliases
                        logger.info("[tag_alias] 解析映射: %s -> %s", key, aliases)

        logger.info("[tag_alias] 最终解析结果: %s", result)
        return result if result else DEFAULT_TAG_ALIAS

    def resolve_tags(self, raw_tag: str) -> list[str]:
        """将用户输入的标签解析为标准标签列表（支持智能别名匹配）。

        支持多种分隔符：英文逗号(,)、中文逗号(，)、空格( )
        """
        if not raw_tag:
            return []

        # 统一替换所有分隔符为英文逗号，然后分割
        normalized = raw_tag.replace('，', ',').replace(' ', ',')
        tags = [t.strip() for t in normalized.split(',') if t.strip()]
        logger.info("[resolve_tags] 输入: %r, 分割后: %s", raw_tag, tags)

        result: list[str] = []
        for tag in tags:
            canonical = self._find_canonical_tag(tag)
            if canonical:
                result.append(canonical)
                logger.info("[resolve_tags] 标签 %r 解析为 %r", tag, canonical)
            else:
                result.append(tag)
                logger.info("[resolve_tags] 标签 %r 未找到别名，使用原值", tag)

        logger.info("[resolve_tags] 最终结果: %s", result)
        return result

    def _find_canonical_tag(self, tag: str) -> str | None:
        """查找标签的标准名称（支持别名匹配）。"""
        normalized = tag.lower()
        logger.info("[_find_canonical_tag] 查找标签: %r (normalized: %r)", tag, normalized)
        logger.info("[_find_canonical_tag] 当前别名映射: %s", self.tag_alias)

        for canonical, aliases in self.tag_alias.items():
            if not isinstance(canonical, str):
                continue
            if normalized == canonical.lower():
                logger.info("[_find_canonical_tag] 直接匹配到标准标签: %s", canonical)
                return canonical
            if isinstance(aliases, list):
                for alias in aliases:
                    if isinstance(alias, str) and normalized == alias.lower():
                        logger.info("[_find_canonical_tag] 通过别名 %r 匹配到标准标签: %s", alias, canonical)
                        return canonical

        logger.info("[_find_canonical_tag] 未找到匹配")
        return None


def _safe_int(value: Any, default: int) -> int:
    """安全地解析类似整数的配置值，失败时返回默认值。"""
    try:
        parsed = int(value)
        return parsed if parsed > 0 else default
    except Exception:
        return default


def _safe_bool(value: Any, default: bool) -> bool:
    """安全地解析类似布尔值的配置值，失败时返回默认值。"""
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
    """解析数量字符串（支持阿拉伯数字或中文数字），解析失败返回 -1。"""
    from .constants import CN_NUM

    s = (raw or "").strip()
    if not s:
        return 1
    if s.isdigit():
        return int(s)
    return CN_NUM.get(s, -1)
