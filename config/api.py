"""API 相关配置。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .helpers import safe_bool, safe_int

if TYPE_CHECKING:
    from .base import ConfigBase


class ApiConfigMixin:
    """API 配置混入类。"""

    _read: Any

    @property
    def api_type(self: ConfigBase) -> str:
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
    def multi_api_strategy(self: ConfigBase) -> str:
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
    def content_mode(self: ConfigBase) -> str:
        """内容模式（分级）。

        返回:
            返回内容模式：sfw（全年龄）、r18（成人）、mix（混合）
        """
        mode = self._read(
            ("general", "content_mode"), "content_mode", "contentMode", default="sfw"
        )
        return mode if mode in ("sfw", "r18", "mix") else "sfw"

    @property
    def exclude_ai(self: ConfigBase) -> bool:
        """排除 AI 生成作品（仅 lolicon 生效）。

        返回:
            是否排除 AI 生成的图片
        """
        return safe_bool(
            self._read(
                ("api", "lolicon", "exclude_ai"),
                "exclude_ai",
                "excludeAi",
                default=True,
            ),
            True,
        )

    @property
    def image_size(self: ConfigBase) -> str:
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
    def proxy(self: ConfigBase) -> str:
        """图片代理主机（仅 lolicon 生效）。

        返回:
            代理服务器地址，默认 i.pixiv.re
        """
        return str(
            self._read(("api", "lolicon", "proxy"), "proxy", default="i.pixiv.re")
        )

    @property
    def aspect_ratio(self: ConfigBase) -> str:
        """宽高比过滤（仅 lolicon 生效）。

        返回:
            返回宽高比：horizontal（横向）、vertical（纵向）、square（方形）
        """
        ratio = self._read(
            ("api", "lolicon", "aspect_ratio"), "aspect_ratio", default=""
        )
        return ratio if ratio in ("horizontal", "vertical", "square") else ""

    @property
    def uid(self: ConfigBase) -> list[int]:
        """作者 UID 列表（仅 lolicon 生效）。

        返回:
            指定作者的 UID 列表，用于筛选特定作者的作品
        """
        uids = self._read(("api", "lolicon", "uid"), "uid", default=[])
        if isinstance(uids, list):
            return [safe_int(uid, 0) for uid in uids if safe_int(uid, 0) > 0]
        return []

    @property
    def keyword(self: ConfigBase) -> str:
        """关键词过滤（仅 lolicon 生效）。

        返回:
            用于过滤图片的关键词
        """
        return str(self._read(("api", "lolicon", "keyword"), "keyword", default=""))

    @property
    def max_replenish_rounds(self: ConfigBase) -> int:
        """最大补充轮次。

        返回:
            部分图片下载失败时的重试轮次
        """
        return safe_int(
            self._read(
                ("general", "max_replenish_rounds"),
                "max_replenish_rounds",
                "maxReplenishRounds",
                default=3,
            ),
            3,
        )

    @property
    def custom_api_configs(self: ConfigBase) -> list[dict[str, Any]]:
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

    def get_custom_api_config(
        self, name: str | None = None
    ) -> dict[str, Any] | None:
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
                "timeout": safe_int(cfg.get("timeout"), 30),
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
