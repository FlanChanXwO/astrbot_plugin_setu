"""Persistence layer — data access and storage.

Contains repository implementations for:
- Access control (blacklist/whitelist)
- Session configuration
- Fortune data
- Cache management
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .access_control_repo import FileBackedAccessControlRepo
from .session_config_json_repository import JsonSessionConfigRepository
from .sqlite_fortune_repository import SQLiteFortuneRepo

if TYPE_CHECKING:
    from astrbot.core import AstrBotConfig

__all__ = [
    "FileBackedAccessControlRepo",
    "JsonSessionConfigRepository",
    "SQLiteFortuneRepo",
    "get_access_control_repo",
    "init_access_control_repo",
    "clear_repo",
    "get_fortune_repo",
    "init_fortune_repo",
    "clear_fortune_repo",
    "get_session_config_repo",
    "init_session_config_repo",
    "clear_session_config_repo",
]

# ==================== Singleton Pattern ====================

_repo: FileBackedAccessControlRepo | None = None
_fortune_repo: SQLiteFortuneRepo | None = None
_session_config_repo: JsonSessionConfigRepository | None = None


def get_access_control_repo() -> FileBackedAccessControlRepo:
    """Get the access control repository singleton.

    Returns:
        The current FileBackedAccessControlRepo instance.

    Raises:
        RuntimeError: If repo not initialized.
    """
    if _repo is None:
        raise RuntimeError(
            "Access control repo not initialized. Call init_access_control_repo() first."
        )
    return _repo


async def init_access_control_repo(
    data_dir: Path, astrbot_config: AstrBotConfig | None = None
) -> FileBackedAccessControlRepo:
    """Initialize access control repository singleton.

    Args:
        data_dir: Plugin data directory.
        astrbot_config: AstrBot config dict for WebUI sync.

    Returns:
        The initialized repository instance.
    """
    global _repo
    _repo = FileBackedAccessControlRepo(data_dir, astrbot_config)
    await _repo.initialize()
    return _repo


def clear_repo() -> None:
    """Clear repo singleton (for testing)."""
    global _repo
    _repo = None


def get_fortune_repo() -> SQLiteFortuneRepo:
    """Get the fortune repository singleton."""
    if _fortune_repo is None:
        raise RuntimeError(
            "Fortune repo not initialized. Call init_fortune_repo() first."
        )
    return _fortune_repo


async def init_fortune_repo(data_dir: Path) -> SQLiteFortuneRepo:
    """Initialize fortune repository singleton."""
    global _fortune_repo
    _fortune_repo = SQLiteFortuneRepo(data_dir / "fortune")
    await _fortune_repo.initialize()
    return _fortune_repo


def clear_fortune_repo() -> None:
    """Clear fortune repo singleton."""
    global _fortune_repo
    _fortune_repo = None


def get_session_config_repo() -> JsonSessionConfigRepository:
    """Get the session configuration repository singleton."""
    if _session_config_repo is None:
        raise RuntimeError(
            "Session config repo not initialized. Call init_session_config_repo() first."
        )
    return _session_config_repo


async def init_session_config_repo(data_dir: Path) -> JsonSessionConfigRepository:
    """Initialize session configuration repository singleton."""
    global _session_config_repo
    _session_config_repo = JsonSessionConfigRepository(data_dir)
    await _session_config_repo.initialize()
    return _session_config_repo


def clear_session_config_repo() -> None:
    """Clear session configuration repo singleton."""
    global _session_config_repo
    _session_config_repo = None
