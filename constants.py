"""Setu 插件的常量和映射配置。"""

from __future__ import annotations

# 图片下载的 HTTP 超时时间（秒）- 默认值为 30，可通过配置覆盖
HTTP_TIMEOUT_SECONDS = 30

# 常见标签的默认别名映射
DEFAULT_TAG_ALIAS: dict[str, list[str]] = {
    "白丝": ["白丝", "白絲", "white stockings"],
    "萝莉": ["萝莉", "蘿莉", "loli"],
    "碧蓝档案": ["碧蓝档案", "碧藍檔案", "blue archive", "ba"],
}

# 命令匹配正则表达式
COMMAND_PATTERN = r"^/?(来\s*(.*?)(份|个|张|点))(.*?)(?:福利|色|瑟|涩|塞)?图$"
