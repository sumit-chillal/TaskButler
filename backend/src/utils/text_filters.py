"""Text filters used to scrub tool-call markup before it reaches the
TTS layer or the rendered transcript.

Two pure functions:

* ``clean_tts_text(chunk)`` — applied to every streamed LLM delta before
  it is spoken. Aggressive: drops any chunk that is an XML/JSON fragment.

* ``sanitize_transcript_text(message)`` — applied at the frontend when
  rendering a full message. Less aggressive (preserves natural language
  around incidental tags) but replaces an entirely-tool-call message
  with the placeholder ``"[tool executed]"``.
"""

from __future__ import annotations

import re

# Strip lone UTF-16 surrogate code points the LLM sometimes emits. They are
# not valid UTF-8 and crash JSONResponse / json.dumps.
_SURROGATE_RE = re.compile(r"[\ud800-\udfff]")

# ---------------------------------------------------------------------------
# Compiled patterns
# ---------------------------------------------------------------------------
# `<function=name>...</function>` (paired)
_FUNCTION_TAG_PAIR_RE = re.compile(
    r"<function=[^>]*>.*?</function>", re.DOTALL | re.IGNORECASE
)
# `<function=name>` (open only)
_FUNCTION_TAG_OPEN_RE = re.compile(r"</?function[^>]*>", re.IGNORECASE)
# `ToolMessage(...)` or `ToolMessage: ...` to end of line
_TOOL_MESSAGE_RE = re.compile(r"ToolMessage[^\n]*", re.IGNORECASE)
# Any angle-bracket tag
_ANY_TAG_RE = re.compile(r"<[^>\n]+>")
# JSON object literal (greedy-safe, no nested objects)
_JSON_OBJECT_RE = re.compile(r"\{[^{}]*\}")


def clean_tts_text(chunk: str) -> str:
    """Strip tool-call markup from a single streamed delta.

    Returns ``""`` for chunks that are entirely markup so the TTS layer
    does not speak them.
    """
    if not chunk:
        return ""

    s = chunk
    stripped = s.strip()

    # Whole-chunk drop: `<...>` only or `{...}` only
    if (stripped.startswith("<") and stripped.endswith(">")) or stripped.startswith("{"):
        return ""

    # Remove paired and orphan function tags
    s = _FUNCTION_TAG_PAIR_RE.sub("", s)
    s = _FUNCTION_TAG_OPEN_RE.sub("", s)

    # Remove any remaining angle-bracket tags
    s = _ANY_TAG_RE.sub("", s)

    # Remove JSON object literals (tool call arguments that leak through)
    s = _JSON_OBJECT_RE.sub("", s)

    # Remove ToolMessage residue
    s = _TOOL_MESSAGE_RE.sub("", s)

    # Strip surrounding quotes only when they wrap the entire chunk —
    # never strip internal whitespace, which would glue streamed tokens together.
    trimmed = s.strip()
    if len(trimmed) >= 2 and trimmed[0] in ("'", '"') and trimmed[-1] == trimmed[0]:
        s = trimmed[1:-1]

    # Final check: if after cleanup nothing meaningful remains, return empty
    # Important: preserve leading/trailing space in tokens for proper concatenation
    if not s.strip():
        return ""

    # Strip lone UTF-16 surrogates that uvicorn/JSONResponse cannot encode.
    s = _SURROGATE_RE.sub("", s)
    return s


def sanitize_transcript_text(text: str) -> str:
    """Clean a full message string before rendering it in the UI.

    * If the message is *entirely* a tool-call / JSON blob, replace it
      with ``"[tool executed]"``.
    * Otherwise strip incidental ``<...>`` tags and inline ``{...}``
      objects, leaving natural-language content intact.
    """
    if not text:
        return ""

    stripped = text.strip()
    # Whole-message tool-call placeholder
    if (
        (stripped.startswith("<") and stripped.endswith(">"))
        or (stripped.startswith("{") and stripped.endswith("}"))
        or stripped.lower().startswith("toolmessage")
    ):
        return "[tool executed]"

    s = _FUNCTION_TAG_PAIR_RE.sub("", text)
    s = _FUNCTION_TAG_OPEN_RE.sub("", s)
    s = _ANY_TAG_RE.sub("", s)
    s = _JSON_OBJECT_RE.sub("", s)
    s = _TOOL_MESSAGE_RE.sub("", s)
    # Collapse the whitespace runs that those substitutions leave behind
    s = re.sub(r"\s{2,}", " ", s)
    # Strip lone UTF-16 surrogates that uvicorn/JSONResponse can't encode.
    s = _SURROGATE_RE.sub("", s)
    return s.strip()
