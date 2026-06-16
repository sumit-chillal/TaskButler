"""Per-request context for tools.

Tools are sync functions invoked by LangChain inside the agent runtime,
so they can't see the LiveKit room name or the ``/api/chat`` ``user_id``
directly. The voice pipeline and the chat endpoint set ``current_user_id``
before calling the agent; ``manage_todo`` (and any future user-scoped tool)
reads it.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Optional

current_user_id: ContextVar[Optional[str]] = ContextVar(
    "current_user_id", default=None
)


def get_current_user_id(default: str = "default") -> str:
    return current_user_id.get() or default
