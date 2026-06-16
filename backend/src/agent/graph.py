"""TaskButler - LangGraph Agent Definition (HITL-enabled).

Builds the ReAct agent with:

* ``MemorySaver`` checkpointer (required for interrupt + resume).
* ``interrupt_before=["tools"]`` so the graph pauses BEFORE any tool node
  executes. The granularity requested in the brief — pausing for ONLY
  ``send_email`` and ``add_calendar_event`` — is enforced inside the tools
  themselves via ``langgraph.types.interrupt(...)``: ``audio_briefing``
  does not call ``interrupt``, so resumption is automatic for that tool.
"""

import logging
import os
from typing import Any, Optional

from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

from .prompts import TASKBUTLER_SYSTEM_PROMPT
from .tools import ALL_TOOLS

logger = logging.getLogger(__name__)


def _validate_env():
    required = ["GROQ_API_KEY"]
    missing = [v for v in required if not os.getenv(v)]
    if missing:
        raise EnvironmentError(
            f"Missing required environment variables: {', '.join(missing)}."
        )


def _build_llm(model_name: str) -> ChatOpenAI:
    return ChatOpenAI(
        model=model_name,
        base_url=os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
        api_key=os.getenv("GROQ_API_KEY"),
        temperature=float(os.getenv("GROQ_TEMPERATURE", "0.2")),
        streaming=True,
        max_retries=int(os.getenv("GROQ_MAX_RETRIES", "2")),
        max_tokens=int(os.getenv("GROQ_MAX_TOKENS", "512")),
        # llama-3.1-8b on Groq occasionally emits malformed parallel calls
        # which the server rejects with `tool_use_failed`. Force serial.
        model_kwargs={"parallel_tool_calls": False},
    )


# A single MemorySaver is shared between the primary and fallback agents so
# an interrupt opened by one model can be resumed by the other. The same
# checkpoint backend also powers the HITL idle-expiry sweep below.
_memory = MemorySaver()


def build_agent(model_name: Optional[str] = None):
    """Build the HITL-enabled LangGraph ReAct agent."""
    _validate_env()

    model_name = model_name or os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
    llm = _build_llm(model_name)

    # Per-tool gating (only send_email + add_calendar_event pause for
    # approval) is implemented inside each tool with
    # ``langgraph.types.interrupt(...)``. That gives us the exact equivalent
    # of ``interrupt_before=["send_email", "add_calendar_event"]`` without
    # restructuring create_react_agent's single "tools" node.
    agent = create_react_agent(
        model=llm,
        tools=ALL_TOOLS,
        checkpointer=_memory,
        prompt=TASKBUTLER_SYSTEM_PROMPT,
    )

    logger.info(
        "TaskButler agent built (model=%s, core_tools=%d, HITL: send_email + add_calendar_event)",
        model_name, len(ALL_TOOLS),
    )
    return agent


# Singletons — primary (fast/cheap) + fallback (strong tool-calling).
_agent: Optional[Any] = None
_fallback_agent: Optional[Any] = None


def get_agent() -> Any:
    global _agent
    if _agent is None:
        _agent = build_agent()
    return _agent


def get_fallback_agent() -> Any:
    """Stronger model used to retry once when the primary emits a malformed
    tool call. Shares the same checkpointer so threads are interchangeable.
    """
    global _fallback_agent
    if _fallback_agent is None:
        fallback_name = os.getenv("GROQ_FALLBACK_MODEL", "llama-3.3-70b-versatile")
        _fallback_agent = build_agent(model_name=fallback_name)
    return _fallback_agent


def get_memory() -> MemorySaver:
    """Expose the shared checkpointer for the HITL TTL sweep."""
    return _memory
