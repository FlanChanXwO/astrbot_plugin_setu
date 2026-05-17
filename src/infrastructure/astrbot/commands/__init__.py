"""AstrBot command adapters."""

from __future__ import annotations

from .fortune import (
    FortuneCommandHandler,
)
from .fortune import (
    register_llm_tools as register_fortune_llm_tools,
)
from .fortune import (
    unregister_llm_tools as unregister_fortune_llm_tools,
)
from .session_config import (
    SessionConfigCommandHandler,
)
from .session_config import (
    register_llm_tools as register_session_config_llm_tools,
)
from .session_config import (
    unregister_llm_tools as unregister_session_config_llm_tools,
)
from .setu import (
    SetuCommandHandler,
)
from .setu import (
    register_llm_tools as register_setu_llm_tools,
)
from .setu import (
    unregister_llm_tools as unregister_setu_llm_tools,
)

__all__ = [
    "FortuneCommandHandler",
    "SessionConfigCommandHandler",
    "SetuCommandHandler",
    "register_fortune_llm_tools",
    "register_session_config_llm_tools",
    "register_setu_llm_tools",
    "unregister_fortune_llm_tools",
    "unregister_session_config_llm_tools",
    "unregister_setu_llm_tools",
]
