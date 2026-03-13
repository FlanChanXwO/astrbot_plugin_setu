"""配置辅助函数。"""

from __future__ import annotations

from typing import Any

from astrbot.api import logger


def safe_int(value: Any, default: int) -> int:
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


def safe_bool(value: Any, default: bool) -> bool:
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
    from ..utils import cn_to_an

    s = (raw or "").strip()
    if not s:
        return 1
    if s.isdigit():
        return int(s)
    # 尝试使用 utils 中的 cn_to_an 解析复杂中文数字
    try:
        result = cn_to_an(s)
        return result if result > 0 else -1
    except Exception as e:
        logger.debug("error parsing count: %s", e)
        return -1
