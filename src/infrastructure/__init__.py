"""Infrastructure layer — external concerns and technical details.

Contains implementations for:
- Sending strategies (direct, forward, HTML card)
- Persistence (repositories, file I/O)
- External API clients
- Caching
- Permission checking
"""

from __future__ import annotations

from ..shared import get_logger
from .permission_service import PermissionService
from .persistence import (
    FileBackedAccessControlRepo,
    JsonSessionConfigRepository,
    SQLiteFortuneRepo,
    clear_fortune_repo,
    clear_repo,
    clear_session_config_repo,
    get_access_control_repo,
    get_fortune_repo,
    get_session_config_repo,
    init_access_control_repo,
    init_fortune_repo,
    init_session_config_repo,
)
from .providers import (
    clear_provider,
    get_provider,
    init_provider,
    init_provider_from_config,
)
from .sending import (
    DirectSendStrategy,
    ForwardSendStrategy,
    HtmlCardFallbackStrategy,
    ImageSender,
    resolve_send_mode,
)

__all__ = [
    "ImageSender",
    "DirectSendStrategy",
    "ForwardSendStrategy",
    "HtmlCardFallbackStrategy",
    "resolve_send_mode",
    "FileBackedAccessControlRepo",
    "JsonSessionConfigRepository",
    "SQLiteFortuneRepo",
    "PermissionService",
    # Singleton getters
    "get_provider",
    "init_provider",
    "init_provider_from_config",
    "clear_provider",
    "get_access_control_repo",
    "init_access_control_repo",
    "clear_repo",
    "get_fortune_repo",
    "init_fortune_repo",
    "clear_fortune_repo",
    "get_session_config_repo",
    "init_session_config_repo",
    "clear_session_config_repo",
    # Logger
    "get_logger",
]
