"""Lightweight regex-based preference detector.

Returns a dict of ``{preference_key: preference_value}`` extracted from
a single user utterance. Used by the voice pipeline to auto-populate
``TaskButlerMemory.preferences``.
"""

from __future__ import annotations

import re
from typing import Optional

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------
_NAME_RE = re.compile(
    r"\bmy name(?:'?s| is)\s+([A-Z][a-zA-Z'\-]+(?:\s+[A-Z][a-zA-Z'\-]+){0,2})",
    re.IGNORECASE,
)
_HOME_RE = re.compile(
    r"\b(?:i (?:live (?:at|in)|stay (?:at|in))|my (?:home|house|address|place)\s+is(?:\s+at)?)\s+([^.,;\n]+?)(?:[.,;\n]|$)",
    re.IGNORECASE,
)
_WORK_RE = re.compile(
    r"\b(?:i\s+work\s+(?:at|in)|my\s+(?:office|work|workplace)\s+is(?:\s+at)?)\s+([^.,;\n]+?)(?:[.,;\n]|$)",
    re.IGNORECASE,
)
_AIRLINE_RE = re.compile(
    r"\b(?:i\s+prefer|i\s+like|my\s+(?:favorite|favourite|preferred)\s+airline\s+is)\s+([A-Z][\w&\- ]+?)(?:\s+(?:airline|airlines|flights))?(?:[.,;\n]|$)",
    re.IGNORECASE,
)
_RESTAURANT_RE = re.compile(
    r"\bmy\s+(?:favorite|favourite|go-to)\s+(?:restaurant|spot)\s+is\s+([^.,;\n]+?)(?:[.,;\n]|$)",
    re.IGNORECASE,
)
_CUISINE_RE = re.compile(
    r"\bi\s+(?:love|like|prefer)\s+([A-Za-z]+)\s+food\b",
    re.IGNORECASE,
)


def _clean(value: Optional[str]) -> str:
    return (value or "").strip().strip(".,;:'\"")


def detect_preferences(text: str) -> dict:
    """Extract preference key/value pairs from one utterance."""
    if not text or not text.strip():
        return {}
    out: dict[str, str] = {}

    if m := _NAME_RE.search(text):
        out["user_name"] = _clean(m.group(1))

    if m := _HOME_RE.search(text):
        out["home_address"] = _clean(m.group(1))

    if m := _WORK_RE.search(text):
        out["work_address"] = _clean(m.group(1))

    if m := _AIRLINE_RE.search(text):
        val = _clean(m.group(1))
        # Avoid catching short pronouns like "it" / "that"
        if len(val) >= 2 and val.lower() not in {"it", "that", "them", "you"}:
            out["preferred_airline"] = val

    if m := _RESTAURANT_RE.search(text):
        out["favorite_restaurant"] = _clean(m.group(1))

    if m := _CUISINE_RE.search(text):
        out["favorite_cuisine"] = _clean(m.group(1)).lower()

    return out
