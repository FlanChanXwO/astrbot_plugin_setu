"""Setu 插件的常量和映射配置。"""

from __future__ import annotations

# 图片下载的 HTTP 超时时间（秒）
HTTP_TIMEOUT_SECONDS = 30

# 常见标签的默认别名映射
DEFAULT_TAG_ALIAS: dict[str, list[str]] = {
    "白丝": ["白丝", "白絲", "white stockings"],
    "萝莉": ["萝莉", "蘿莉", "loli"],
    "碧蓝档案": ["碧蓝档案", "碧藍檔案", "blue archive", "ba"],
}

# 命令匹配正则表达式
# 组2: 数量(可选), 组4: 标签(支持空格)
# 使用原子组(?>...)和独占量词优化性能，避免回溯
# 限制标签长度和数量，防止超长输入导致性能问题
COMMAND_PATTERN = r"^/?(来\s*([一二两三四五六七八九十百千万亿\d]+)?(?:份|个|张|点))([^\s]{0,30}(?:\s[^\s]{0,30}){0,4})(?:福利|色|瑟|涩|塞)?图$"
