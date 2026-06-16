"""TaskButler — Agent Tools (Four-Pillar Core + HITL Google Workspace).

Pillars exposed to the LLM:

    1. send_email          -> Gmail via gmail.users.messages.send (HITL gated)
    2. add_calendar_event  -> Calendar via events.insert         (HITL gated)
    3. audio_briefing      -> Tavily research + Groq synthesis (live)

The fourth pillar (Environment Orchestrator) is handled by the Intent
Router and Browser Dispatcher and never reaches the LLM.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.types import interrupt
from pydantic import BaseModel

from ..google_workspace import insert_calendar_event, send_gmail
from ..spotify_api import play_focus_music
from .runtime_context import get_current_user_id

logger = logging.getLogger(__name__)


# -------------------------------------------------------------------------
# Shared helpers
# -------------------------------------------------------------------------
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _error_response(tool_name: str, error, **extra) -> dict:
    err = error if isinstance(error, str) else str(error)
    logger.error("Tool '%s' failed: %s", tool_name, err)
    details = {"error": err, **extra}
    return {
        "tool": tool_name,
        "status": "error",
        "icon": "alert-circle",
        "title": "Something went wrong",
        "details": details,
        "timestamp": _now_iso(),
    }


def _run_async(coro):
    """Best-effort sync wrapper for async helpers when called from a tool body."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        new_loop = asyncio.new_event_loop()
        try:
            return new_loop.run_until_complete(coro)
        finally:
            new_loop.close()
    return asyncio.run(coro)


# =========================================================================
# 1. send_email — Gmail (HITL gated)
# =========================================================================
class SendEmailInput(BaseModel):
    to: str
    subject: str
    body: str


@tool(args_schema=SendEmailInput)
def send_email(to: str, subject: str, body: str) -> dict:
    """Send an email. Pauses for explicit user approval before dispatching."""
    user_id = get_current_user_id() or "default"

    payload_preview = {
        "to": to,
        "subject": subject,
        "body_preview": (body or "")[:280],
        "body_chars": len(body or ""),
    }

    approval = interrupt({
        "interrupted": True,
        "tool_name": "send_email",
        "payload_preview": payload_preview,
    })

    if not isinstance(approval, dict) or not approval.get("approved"):
        reason = (approval or {}).get("reason", "user declined")
        return {
            "tool": "send_email",
            "status": "cancelled",
            "icon": "x-circle",
            "title": "Email send cancelled",
            "details": {"reason": reason, **payload_preview},
            "timestamp": _now_iso(),
        }

    final_to = approval.get("to") or to
    final_subject = approval.get("subject") or subject
    final_body = approval.get("body") or body

    try:
        result = _run_async(send_gmail(user_id, final_to, final_subject, final_body))
    except Exception as e:
        return _error_response("send_email", e, step="gmail_api")

    if not result.get("success"):
        if result.get("error") == "google_not_linked":
            return _error_response(
                "send_email",
                "Your Google account is not linked yet — visit /api/auth/google/init.",
                step="oauth",
            )
        return _error_response(
            "send_email", result.get("error", "send failed"),
            step=result.get("step", "gmail"),
        )

    return {
        "tool": "send_email",
        "status": "success",
        "icon": "mail-check",
        "title": f"Email sent to {final_to}",
        "details": {
            "to": final_to,
            "subject": final_subject,
            "message_id": result.get("message_id"),
            "thread_id": result.get("thread_id"),
        },
        "timestamp": _now_iso(),
    }


# =========================================================================
# 2. add_calendar_event — Calendar (HITL gated)
# =========================================================================
class AddCalendarEventInput(BaseModel):
    title: str
    date: str
    time: str
    duration_minutes: int = 60
    description: str = ""
    timezone_name: str = "UTC"


def _resolve_iso(date: str, time: str, tz_name: str = "UTC") -> Optional[datetime]:
    """Best-effort parse of (date, time) into a tz-aware datetime."""
    candidates = [f"{date} {time}", f"{date}T{time}"]
    fmts = [
        "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M",
        "%Y-%m-%d %I:%M %p", "%Y-%m-%d %I %p",
        "%d %B %Y %H:%M", "%d %b %Y %H:%M",
    ]
    for cand in candidates:
        for fmt in fmts:
            try:
                dt = datetime.strptime(cand, fmt)
                return dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
    return None


@tool(args_schema=AddCalendarEventInput)
def add_calendar_event(
    title: str,
    date: str,
    time: str,
    duration_minutes: int = 60,
    description: str = "",
    timezone_name: str = "UTC",
) -> dict:
    """Add a calendar event. Pauses for explicit user approval before inserting."""
    user_id = get_current_user_id() or "default"

    start_dt = _resolve_iso(date, time, timezone_name)
    if start_dt is None:
        start_iso = f"{date} {time}"
        end_iso = ""
    else:
        end_dt = start_dt + timedelta(minutes=duration_minutes)
        start_iso = start_dt.isoformat()
        end_iso = end_dt.isoformat()

    payload_preview = {
        "title": title,
        "date": date,
        "time": time,
        "start_iso": start_iso,
        "end_iso": end_iso,
        "duration_minutes": duration_minutes,
        "description": description,
        "timezone": timezone_name,
    }

    approval = interrupt({
        "interrupted": True,
        "tool_name": "add_calendar_event",
        "payload_preview": payload_preview,
    })

    if not isinstance(approval, dict) or not approval.get("approved"):
        reason = (approval or {}).get("reason", "user declined")
        return {
            "tool": "add_calendar_event",
            "status": "cancelled",
            "icon": "x-circle",
            "title": "Calendar event cancelled",
            "details": {"reason": reason, **payload_preview},
            "timestamp": _now_iso(),
        }

    final_title = approval.get("title") or title
    final_start = approval.get("start_iso") or start_iso
    final_end = approval.get("end_iso") or end_iso
    final_desc = approval.get("description") or description
    final_tz = approval.get("timezone") or timezone_name

    if not final_start or not final_end:
        return _error_response(
            "add_calendar_event",
            "Could not resolve start/end ISO 8601 timestamps. "
            "Please re-issue with explicit ISO values via /api/chat/resume.",
            step="iso_parse",
        )

    try:
        result = _run_async(
            insert_calendar_event(
                user_id=user_id,
                summary=final_title,
                start_iso=final_start,
                end_iso=final_end,
                description=final_desc,
                timezone_name=final_tz,
            )
        )
    except Exception as e:
        return _error_response("add_calendar_event", e, step="calendar_api")

    if not result.get("success"):
        if result.get("error") == "google_not_linked":
            return _error_response(
                "add_calendar_event",
                "Your Google account is not linked yet — visit /api/auth/google/init.",
                step="oauth",
            )
        return _error_response(
            "add_calendar_event", result.get("error", "insert failed"),
            step=result.get("step", "calendar"),
        )

    return {
        "tool": "add_calendar_event",
        "status": "success",
        "icon": "calendar-check",
        "title": f"'{final_title}' added to your calendar",
        "details": {
            "event_id": result.get("event_id"),
            "html_link": result.get("html_link"),
            "start_iso": final_start,
            "end_iso": final_end,
        },
        "timestamp": _now_iso(),
    }


# =========================================================================
# 3. audio_briefing — LIVE: Tavily research -> Groq radio-style synthesis
# =========================================================================
class AudioBriefingInput(BaseModel):
    topic: str = ""
    max_sentences: int = 3


_FALLBACK_SCRIPT = (
    "I'm sorry, I couldn't pull the latest network data for your briefing. "
    "Try again in a moment, or give me a different topic."
)

# Strip characters TTS engines render awkwardly.
_TTS_BAD_CHARS = "*_`#>~|[]{}<"


def _clean_for_voice(text: str) -> str:
    if not text:
        return ""
    cleaned = text
    for ch in _TTS_BAD_CHARS:
        cleaned = cleaned.replace(ch, "")
    # Collapse whitespace.
    cleaned = " ".join(cleaned.split())
    return cleaned.strip()


def _tavily_research(topic: str) -> dict:
    """Run a synchronous Tavily search. Returns {context, sources}."""
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return {"context": "", "sources": [], "error": "missing_tavily_key"}

    from tavily import TavilyClient

    client = TavilyClient(api_key=api_key)
    # Bounded depth + result count so a briefing stays fast and inexpensive.
    resp = client.search(
        query=topic,
        search_depth="basic",
        max_results=5,
        include_answer=True,
    )
    results = resp.get("results", []) or []
    sources = [
        {"title": r.get("title"), "url": r.get("url")}
        for r in results if r.get("url")
    ]
    # Build a compact research blob the LLM can read.
    snippets = []
    if resp.get("answer"):
        snippets.append(f"Tavily summary: {resp['answer']}")
    for r in results:
        title = (r.get("title") or "").strip()
        content = (r.get("content") or "").strip()
        if title or content:
            snippets.append(f"- {title}\n  {content}")
    context = "\n\n".join(snippets)[:6000]  # safety cap
    return {"context": context, "sources": sources}


def _groq_synthesise(topic: str, research_context: str, max_sentences: int) -> str:
    """Localized Groq call that produces a radio-style script."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not configured")

    model_name = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
    llm = ChatOpenAI(
        model=model_name,
        base_url=os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
        api_key=api_key,
        temperature=float(os.getenv("GROQ_TEMPERATURE", "0.4")),
        max_retries=int(os.getenv("GROQ_MAX_RETRIES", "2")),
        max_tokens=400,
        timeout=20.0,
    )

    system_prompt = (
        f"You are a professional radio broadcaster. Synthesize the provided "
        f"research data into a highly conversational, radio-style audio script "
        f"about {topic}. Do not use markdown formatting, bullet points, "
        f"asterisks, code blocks, or structural lists. Write fluid transitions "
        f"tailored explicitly for continuous vocal broadcast. "
        f"Keep it to a maximum of {max_sentences} sentences."
    )
    user_prompt = (
        f"Topic: {topic}\n\n"
        f"Research notes (use only what's relevant, ignore anything off-topic):\n"
        f"{research_context if research_context else '(no external research available)'}\n\n"
        f"Write the script now. Plain prose only. "
        f"Maximum {max_sentences} sentences."
    )

    resp = llm.invoke([("system", system_prompt), ("user", user_prompt)])
    raw = getattr(resp, "content", "") or ""
    if isinstance(raw, list):  # safety: chat models sometimes return parts
        raw = "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in raw)
    return _clean_for_voice(raw)


@tool(args_schema=AudioBriefingInput)
def audio_briefing(topic: str = "", max_sentences: int = 3) -> dict:
    """Live research + radio-style synthesis briefing.

    Uses Tavily to gather fresh web context, then a localized Groq LLM call
    to synthesise a continuous, conversational, TTS-friendly script. On any
    network or model failure the tool returns a graceful fallback script
    instead of crashing the graph.
    """
    max_sentences = max(1, min(int(max_sentences or 3), 6))
    topic = (topic or "").strip() or "your recent activity"

    sources: list = []
    used_research = False
    script: str = ""

    # ---- 1) Research (best-effort — empty context if Tavily unavailable) ----
    try:
        research = _tavily_research(topic)
        context_blob = research.get("context") or ""
        sources = research.get("sources") or []
        used_research = bool(context_blob)
    except Exception as e:
        logger.warning("Tavily research failed for '%s': %s", topic, e)
        context_blob = ""

    # ---- 2) Synthesis (Groq) ----
    try:
        script = _groq_synthesise(topic, context_blob, max_sentences)
    except Exception as e:
        logger.warning("Groq synthesis failed for '%s': %s", topic, e)
        script = ""

    if not script:
        script = _FALLBACK_SCRIPT
        status = "degraded"
    else:
        status = "success"

    return {
        "tool": "audio_briefing",
        "status": status,
        "icon": "headphones",
        "title": f"Briefing: {topic}",
        "details": {
            "topic": topic,
            "max_sentences": max_sentences,
            "script": script,
            "research_used": used_research,
            "sources": sources[:5],
        },
        "timestamp": _now_iso(),
    }


# -------------------------------------------------------------------------
# Aggregate
# -------------------------------------------------------------------------
# =========================================================================
# 4. environment_orchestrator — Calendar block + Spotify focus playlist
#    NO interrupt: zero-friction real-world action.
# =========================================================================
class EnvironmentOrchestratorInput(BaseModel):
    duration_minutes: int = 60
    mode: str = "focus"


_MODE_PLAYLISTS = {
    "focus": os.getenv("SPOTIFY_DEFAULT_PLAYLIST", "spotify:playlist:37i9dQZF1DWZeKCadgRdKQ"),
    # Lo-fi beats — calm/study sibling default.
    "study": "spotify:playlist:37i9dQZF1DWWQRwui0ExPn",
    "deep_work": os.getenv("SPOTIFY_DEFAULT_PLAYLIST", "spotify:playlist:37i9dQZF1DWZeKCadgRdKQ"),
}

_MODE_TITLES = {
    "focus": "Deep Work Session",
    "study": "Study Session",
    "deep_work": "Deep Work Session",
}


@tool(args_schema=EnvironmentOrchestratorInput)
def environment_orchestrator(duration_minutes: int = 60, mode: str = "focus") -> dict:
    """Activate focus mode: instantly block calendar time AND start Spotify."""
    user_id = get_current_user_id() or "default"

    mode_key = (mode or "focus").strip().lower().replace(" ", "_")
    if mode_key not in _MODE_PLAYLISTS:
        mode_key = "focus"
    duration_minutes = max(5, min(int(duration_minutes or 60), 240))

    title = _MODE_TITLES.get(mode_key, "Deep Work Session")
    playlist_uri = _MODE_PLAYLISTS[mode_key]

    now = datetime.now(timezone.utc).replace(microsecond=0)
    start_iso = now.isoformat()
    end_iso = (now + timedelta(minutes=duration_minutes)).isoformat()

    # (a) Calendar block — synchronous via _run_async
    calendar_status: str = "skipped"
    calendar_details: dict = {}
    try:
        cal_result = _run_async(
            insert_calendar_event(
                user_id=user_id,
                summary=title,
                start_iso=start_iso,
                end_iso=end_iso,
                description=f"Auto-blocked by TaskButler ({mode_key} mode).",
                timezone_name="UTC",
            )
        )
        if cal_result.get("success"):
            calendar_status = "blocked"
            calendar_details = {
                "event_id": cal_result.get("event_id"),
                "html_link": cal_result.get("html_link"),
                "start_iso": start_iso,
                "end_iso": end_iso,
            }
        elif cal_result.get("error") == "google_not_linked":
            calendar_status = "not_linked"
            calendar_details = {"hint": "Visit /api/auth/google/init to link Google."}
        else:
            calendar_status = "error"
            calendar_details = {"error": cal_result.get("error", "calendar failed")}
    except Exception as e:
        logger.warning("environment_orchestrator calendar step failed: %s", e)
        calendar_status = "error"
        calendar_details = {"error": str(e)}

    # (b) Spotify playback — synchronous via _run_async
    music_status: str = "skipped"
    music_details: dict = {}
    music_note: Optional[str] = None
    try:
        play_result = _run_async(play_focus_music(user_id, playlist_uri))
        music_details = {
            "playlist_uri": play_result.get("playlist_uri"),
            "reason": play_result.get("reason"),
        }
        if play_result.get("playback_started"):
            music_status = "playing"
        elif play_result.get("reason") == "no_active_device":
            music_status = "no_device"
            music_note = (
                "Open Spotify on your phone or desktop and tap any track once, "
                "then ask me to start the music again."
            )
        elif play_result.get("reason") == "not_linked":
            music_status = "not_linked"
            music_note = "Spotify isn't linked yet — visit /api/auth/spotify/init."
        elif play_result.get("reason") == "premium_required":
            music_status = "premium_required"
            music_note = "Spotify playback control requires a Premium account."
        else:
            music_status = "error"
            music_note = (
                "Calendar blocked, but open Spotify on your phone to start the music."
            )
    except Exception as e:
        logger.warning("environment_orchestrator spotify step failed: %s", e)
        music_status = "error"
        music_details = {"error": str(e)}
        music_note = (
            "Calendar blocked, but open Spotify on your phone to start the music."
        )

    # (c) Compose final tool card
    pieces: list[str] = []
    if calendar_status == "blocked":
        pieces.append(f"calendar blocked for {duration_minutes} min")
    if music_status == "playing":
        pieces.append("Spotify focus playlist playing")
    if not pieces:
        headline = f"{title} requested — see notes."
    else:
        headline = " · ".join(pieces).capitalize() + "."

    return {
        "tool": "environment_orchestrator",
        "status": "success" if (calendar_status == "blocked" or music_status == "playing") else "degraded",
        "icon": "focus",
        "title": headline,
        "details": {
            "mode": mode_key,
            "duration_minutes": duration_minutes,
            "calendar_status": calendar_status,
            "calendar": calendar_details,
            "music_status": music_status,
            "music": music_details,
            "note": music_note,
            "session_event": title,
            "start_iso": start_iso,
            "end_iso": end_iso,
        },
        "timestamp": _now_iso(),
    }


ALL_TOOLS = [
    send_email,
    add_calendar_event,
    audio_briefing,
    environment_orchestrator,
]


def _removed(*_a, **_kw):
    raise RuntimeError(
        "This legacy tool was removed in the four-pillar refactor. "
        "Available tools: send_email, add_calendar_event, audio_briefing."
    )


search_restaurants = _removed
order_ride = _removed
book_flight = _removed
set_alarm = _removed
manage_todo = _removed
get_weather = _removed
