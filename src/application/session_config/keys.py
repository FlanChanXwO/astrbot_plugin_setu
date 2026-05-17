"""Known session-scoped configuration keys and validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from .dto import JsonValue

ValueType = Literal["enum", "bool", "string"]


@dataclass(frozen=True, slots=True)
class SessionConfigKey:
    """Metadata for a supported session override key."""

    key: str
    label: str
    value_type: ValueType
    description: str
    options: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable schema fragment."""
        return {
            "key": self.key,
            "label": self.label,
            "type": self.value_type,
            "description": self.description,
            "options": list(self.options),
        }


SESSION_CONFIG_KEYS: dict[str, SessionConfigKey] = {
    "setu.content_mode": SessionConfigKey(
        key="setu.content_mode",
        label="色图内容分级",
        value_type="enum",
        options=("sfw", "r18", "mix"),
        description="当前会话请求色图时使用的内容分级。",
    ),
    "setu.r18_docx": SessionConfigKey(
        key="setu.r18_docx",
        label="R18 Docx 打包",
        value_type="bool",
        description="当前会话发送 R18 图片时是否优先打包为 Docx。",
    ),
    "setu.auto_revoke": SessionConfigKey(
        key="setu.auto_revoke",
        label="R18 自动撤回",
        value_type="bool",
        description="当前会话发送 R18 内容后是否自动撤回。",
    ),
    "setu.send_mode": SessionConfigKey(
        key="setu.send_mode",
        label="图片发送模式",
        value_type="enum",
        options=("image", "forward", "auto"),
        description="当前会话发送图片时使用直发、合并转发或自动模式。",
    ),
    "fortune.tags": SessionConfigKey(
        key="fortune.tags",
        label="运势图片标签",
        value_type="string",
        description="当前会话生成运势图片时使用的默认标签。",
    ),
    "fortune.content_mode": SessionConfigKey(
        key="fortune.content_mode",
        label="运势内容分级",
        value_type="enum",
        options=("sfw", "r18", "mix"),
        description="当前会话生成运势图片时使用的内容分级。",
    ),
}

TRUE_VALUES = {
    "1",
    "true",
    "yes",
    "y",
    "on",
    "enable",
    "enabled",
    "开",
    "开启",
    "启用",
    "是",
}
FALSE_VALUES = {
    "0",
    "false",
    "no",
    "n",
    "off",
    "disable",
    "disabled",
    "关",
    "关闭",
    "禁用",
    "否",
}


class SessionConfigValidationError(ValueError):
    """Raised when a session configuration key or value is invalid."""


def get_key_definition(key: str) -> SessionConfigKey:
    """Return metadata for a key or raise a validation error."""
    normalized = key.strip()
    definition = SESSION_CONFIG_KEYS.get(normalized)
    if definition is None:
        raise SessionConfigValidationError(
            f"未知配置项：{key}。可用配置项：{', '.join(SESSION_CONFIG_KEYS)}"
        )
    return definition


def normalize_session_type(value: str | None) -> Literal["group", "private"]:
    """Normalize a session type from user/API input."""
    normalized = (value or "private").strip().lower()
    if normalized not in ("group", "private"):
        raise SessionConfigValidationError("session_type 必须是 group 或 private")
    return normalized  # type: ignore[return-value]


def normalize_config_value(key: str, value: Any) -> JsonValue:
    """Normalize and validate a value for a known session config key."""
    definition = get_key_definition(key)
    if definition.value_type == "bool":
        return _normalize_bool(value)
    if definition.value_type == "enum":
        text = str(value).strip().lower()
        if text not in definition.options:
            raise SessionConfigValidationError(
                f"{definition.label} 的值必须是：{', '.join(definition.options)}"
            )
        return text
    return "" if value is None else str(value).strip()


def _normalize_bool(value: Any) -> bool:
    """Normalize common boolean spellings."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    text = str(value).strip().lower()
    if text in TRUE_VALUES:
        return True
    if text in FALSE_VALUES:
        return False
    raise SessionConfigValidationError("布尔值必须是 true/false、on/off 或 1/0")
