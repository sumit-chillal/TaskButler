from fastapi import FastAPI, APIRouter, Query, HTTPException, Header, Request
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import asyncio
import json
import hashlib
import subprocess
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
import uuid
from datetime import datetime, timezone, timedelta
from livekit import api as livekit_api
from collections import defaultdict

try:
    import jwt as pyjwt
except ImportError:
    pyjwt = None

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parent
app = FastAPI(title="TaskButler API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_router = APIRouter(prefix="/api")

# --- Database ---
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "taskbutler")
client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

# --- Auth ---
AUTH_SECRET = os.getenv("AUTH_SECRET", "taskbutler-dev-secret-change-in-prod")
_users = {
    "demo@taskbutler.ai": {"password_hash": hashlib.sha256(b"demo1234").hexdigest(), "name": "Demo User"}
}

def verify_token_optional(authorization: Optional[str] = None) -> Optional[dict]:
    """Verify JWT token, return None if no token."""
    if not authorization or not pyjwt:
        return None
    try:
        token = authorization.replace("Bearer ", "")
        return pyjwt.decode(token, AUTH_SECRET, algorithms=["HS256"])
    except Exception:
        return None

@api_router.post("/auth/login")
async def login(request: Request):
    body = await request.json()
    email = body.get("email", "").lower().strip()
    password = body.get("password", "")
    user = _users.get(email)
    if not user or user["password_hash"] != hashlib.sha256(password.encode()).hexdigest():
        raise HTTPException(status_code=401, detail="Invalid credentials")
    payload = {
        "user_id": hashlib.sha256(email.encode()).hexdigest()[:12],
        "email": email, "name": user["name"],
        "exp": datetime.utcnow() + timedelta(hours=24)
    }
    token = pyjwt.encode(payload, AUTH_SECRET, algorithm="HS256") if pyjwt else "mock-token"
    return {"token": token, "user": {"name": user["name"], "email": email}}

# --- LiveKit Token ---
@api_router.get("/token")
async def get_livekit_token(
    room: str = Query(...),
    identity: str = Query(...),
    voice_gender: str = Query("female"),
):
    api_key = os.getenv("LIVEKIT_API_KEY")
    api_secret = os.getenv("LIVEKIT_API_SECRET")
    livekit_url = os.getenv("LIVEKIT_URL", "")
    if not api_key or not api_secret:
        raise HTTPException(status_code=500, detail="LIVEKIT_API_KEY and LIVEKIT_API_SECRET must be set")
    # Embed voice_gender in token metadata so the agent worker can read it
    metadata = json.dumps({"voice_gender": voice_gender, "identity": identity})
    token = (
        livekit_api.AccessToken(api_key=api_key, api_secret=api_secret)
        .with_identity(identity)
        .with_metadata(metadata)
        .with_grants(livekit_api.VideoGrants(
            room_join=True, room=room,
            can_publish=True, can_subscribe=True, can_publish_data=True,
        ))
    )
    jwt_token = token.to_jwt()
    return {"token": jwt_token, "url": livekit_url, "ws_url": livekit_url, "voice_gender": voice_gender}

# --- Set Voice ---
@api_router.post("/set-voice")
async def set_voice(request: Request):
    body = await request.json()
    room_name = body.get("room", "")
    voice_gender = body.get("voice_gender", "female")
    # In production, update room metadata via LiveKit API
    return {"status": "ok", "voice_gender": voice_gender}


# --- Google OAuth (Gmail + Calendar) ---------------------------------------
@api_router.get("/auth/google/init")
async def google_oauth_init(user_id: str = Query(...)):
    """Start the Google OAuth flow. Redirects the browser to Google's consent
    screen with offline access so we can capture a refresh_token."""
    from urllib.parse import urlencode
    from fastapi.responses import RedirectResponse

    client_id = os.getenv("GOOGLE_CLIENT_ID")
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")
    scopes = os.getenv(
        "GOOGLE_OAUTH_SCOPES",
        "https://www.googleapis.com/auth/gmail.send "
        "https://www.googleapis.com/auth/calendar.events "
        "openid email profile",
    )
    if not client_id or not redirect_uri:
        raise HTTPException(
            status_code=500,
            detail="GOOGLE_CLIENT_ID / GOOGLE_REDIRECT_URI not configured",
        )
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scopes,
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent",
        "state": user_id,
    }
    return RedirectResponse(
        f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
    )


@api_router.get("/auth/google/callback")
async def google_oauth_callback(
    code: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
    error: Optional[str] = Query(default=None),
):
    """Exchange the authorization ``code`` for tokens and persist to Mongo."""
    import httpx
    from fastapi.responses import RedirectResponse

    from src.db.models import UserOAuthCredentials, get_oauth_repo

    frontend_url = os.getenv("FRONTEND_URL") or os.getenv(
        "NEXT_PUBLIC_BACKEND_URL", "/"
    )
    if error:
        from urllib.parse import quote_plus
        logging.warning("Google OAuth consent rejected: %s", error)
        return RedirectResponse(f"{frontend_url}?oauth_error={quote_plus(error)}")
    if not code or not state:
        raise HTTPException(status_code=400, detail="code and state required")

    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")

    async with httpx.AsyncClient(timeout=20.0) as http:
        token_resp = await http.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
    if token_resp.status_code != 200:
        # Surface the actual Google response to make redirect-uri-mismatch /
        # invalid-client / invalid-grant errors visible in the UI without
        # requiring server-log access.
        try:
            err_body = token_resp.json()
        except Exception:
            err_body = {"raw": token_resp.text}
        err_code = err_body.get("error") or "token_exchange_failed"
        err_desc = err_body.get("error_description") or token_resp.text[:200]
        logging.error(
            "Google token exchange failed status=%s code=%s desc=%s "
            "(redirect_uri=%s, client_id_tail=...%s)",
            token_resp.status_code, err_code, err_desc,
            redirect_uri, (client_id or "")[-6:],
        )
        from urllib.parse import quote_plus
        return RedirectResponse(
            f"{frontend_url}?oauth_error={quote_plus(err_code)}"
            f"&oauth_error_description={quote_plus(err_desc)}"
        )
    tok = token_resp.json()

    # Resolve the user's email — best-effort.
    email_addr = None
    try:
        async with httpx.AsyncClient(timeout=10.0) as http:
            ui = await http.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {tok['access_token']}"},
            )
            if ui.status_code == 200:
                email_addr = ui.json().get("email")
    except Exception as e:
        logging.warning("userinfo fetch failed: %s", e)

    expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=int(tok.get("expires_in", 3600))
    )

    creds = UserOAuthCredentials(
        user_id=state,
        provider="google",
        email=email_addr,
        scopes=(tok.get("scope") or "").split(),
        access_token=tok.get("access_token"),
        refresh_token=tok.get("refresh_token"),
        access_token_expiry=expires_at,
        token_type=tok.get("token_type", "Bearer"),
    )
    try:
        repo = await get_oauth_repo()
        await repo.upsert(creds)
    except Exception as e:
        logging.exception("Google credentials upsert failed for user=%s: %s", state, e)
        from urllib.parse import quote_plus
        return RedirectResponse(
            f"{frontend_url}?oauth_error=storage_failed"
            f"&oauth_error_description={quote_plus(str(e)[:200])}"
        )

    logging.info("Google OAuth linked: user=%s email=%s scopes=%d", state, email_addr, len(creds.scopes))
    return RedirectResponse(f"{frontend_url}?google_linked=1&email={email_addr or ''}")


@api_router.get("/auth/google/status")
async def google_oauth_status(user_id: str = Query(...)):
    from src.db.models import get_oauth_repo
    repo = await get_oauth_repo()
    rec = await repo.get(user_id)
    if rec is None:
        return {"linked": False}
    return {
        "linked": True,
        "email": rec.email,
        "scopes": rec.scopes,
        "expires_at": (
            rec.access_token_expiry.isoformat() if rec.access_token_expiry else None
        ),
    }


@api_router.delete("/auth/google")
@api_router.delete("/auth/google/unlink")
async def google_oauth_unlink(user_id: str = Query(...)):
    from src.db.models import get_oauth_repo
    repo = await get_oauth_repo()
    ok = await repo.delete(user_id, provider="google")
    return {"unlinked": ok, "user_id": user_id, "provider": "google"}


# --- Spotify OAuth (Environment Orchestrator) -----------------------------
@api_router.get("/auth/spotify/init")
async def spotify_oauth_init(user_id: str = Query(...)):
    """Kick off the Spotify Authorization Code flow."""
    from urllib.parse import urlencode
    from fastapi.responses import RedirectResponse

    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI")
    scopes = os.getenv(
        "SPOTIFY_OAUTH_SCOPES",
        "user-modify-playback-state user-read-playback-state "
        "user-read-currently-playing streaming",
    )
    if not client_id or not redirect_uri:
        raise HTTPException(
            status_code=500,
            detail="SPOTIFY_CLIENT_ID / SPOTIFY_REDIRECT_URI not configured",
        )
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": scopes,
        "state": user_id,
        "show_dialog": "true",
    }
    return RedirectResponse(
        f"https://accounts.spotify.com/authorize?{urlencode(params)}"
    )


@api_router.get("/auth/spotify/callback")
async def spotify_oauth_callback(
    code: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
    error: Optional[str] = Query(default=None),
):
    """Exchange Spotify auth code for tokens and persist under provider='spotify'."""
    import base64
    import httpx
    from fastapi.responses import RedirectResponse

    from src.db.models import UserOAuthCredentials, get_oauth_repo

    frontend_url = os.getenv("FRONTEND_URL", "/")
    if error:
        return RedirectResponse(f"{frontend_url}?spotify_error={error}")
    if not code or not state:
        raise HTTPException(status_code=400, detail="code and state required")

    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI")
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()

    async with httpx.AsyncClient(timeout=20.0) as http:
        token_resp = await http.post(
            "https://accounts.spotify.com/api/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
            },
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
    if token_resp.status_code != 200:
        logging.error("Spotify token exchange failed: %s", token_resp.text)
        return RedirectResponse(
            f"{frontend_url}?spotify_error=token_exchange_failed"
        )
    tok = token_resp.json()

    # Best-effort profile fetch.
    email_addr: Optional[str] = None
    try:
        async with httpx.AsyncClient(timeout=10.0) as http:
            me = await http.get(
                "https://api.spotify.com/v1/me",
                headers={"Authorization": f"Bearer {tok['access_token']}"},
            )
            if me.status_code == 200:
                email_addr = me.json().get("email")
    except Exception as e:
        logging.warning("Spotify /me fetch failed: %s", e)

    expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=int(tok.get("expires_in", 3600))
    )

    creds = UserOAuthCredentials(
        user_id=state,
        provider="spotify",
        email=email_addr,
        scopes=(tok.get("scope") or "").split(),
        access_token=tok.get("access_token"),
        refresh_token=tok.get("refresh_token"),
        access_token_expiry=expires_at,
        token_type=tok.get("token_type", "Bearer"),
    )
    repo = await get_oauth_repo()
    await repo.upsert(creds)

    return RedirectResponse(
        f"{frontend_url}?spotify_linked=1&email={email_addr or ''}"
    )


@api_router.get("/auth/spotify/status")
async def spotify_oauth_status(user_id: str = Query(...)):
    from src.db.models import get_oauth_repo
    repo = await get_oauth_repo()
    rec = await repo.get(user_id, provider="spotify")
    if rec is None:
        return {"linked": False}
    return {
        "linked": True,
        "email": rec.email,
        "scopes": rec.scopes,
        "expires_at": (
            rec.access_token_expiry.isoformat() if rec.access_token_expiry else None
        ),
    }


@api_router.delete("/auth/spotify/unlink")
async def spotify_oauth_unlink(user_id: str = Query(...)):
    from src.db.models import get_oauth_repo
    repo = await get_oauth_repo()
    ok = await repo.delete(user_id, provider="spotify")
    return {"unlinked": ok, "user_id": user_id, "provider": "spotify"}


# --- Chat (Text Input) ---
async def _build_messages_with_memory(message: str, user_id: str):
    """Prepend vector-memory context (if any) to the user message."""
    from src.memory.vector_store import get_memory

    messages_in: list = [("user", message)]
    memory = None
    try:
        memory = await get_memory()
        ctx_hits = await memory.retrieve_relevant_context(
            query=message, user_id=user_id, n_results=5,
        )
        if ctx_hits:
            ctx_lines = "\n".join(
                f"- ({h['metadata'].get('role', '?')}): {h['content']}" for h in ctx_hits
            )
            prefs = await memory.get_user_preferences(user_id)
            pref_line = ", ".join(f"{k}={v}" for k, v in prefs.items())
            sys_note = "Relevant context from past conversations:\n" + ctx_lines
            if pref_line:
                sys_note += f"\nKnown user preferences: {pref_line}"
            messages_in = [("system", sys_note), ("user", message)]
    except Exception as e:
        logging.warning(f"Memory context skipped: {e}")
    return messages_in, memory


# Recovery for Groq llama-3.1-8b's malformed `<function=NAME>{json}` calls.
# Restricted to non-HITL tools so we never bypass user approval gates.
_MALFORMED_CALL_RE = None
_SAFE_FALLBACK_TOOLS = {"audio_briefing", "environment_orchestrator"}


async def _recover_from_malformed_tool_call(failed_generation: str) -> Optional[dict]:
    """Parse `<function=NAME>{json}` and invoke the tool directly.

    Returns a tool-result dict on success, or None when recovery isn't safe
    (HITL-gated tool, unparseable payload, or unknown tool name).
    """
    global _MALFORMED_CALL_RE
    import re as _re

    if _MALFORMED_CALL_RE is None:
        _MALFORMED_CALL_RE = _re.compile(
            r"<function\s*=\s*([A-Za-z_][A-Za-z0-9_]*)\s*>\s*(\{.*?\})\s*(?:</function>)?",
            _re.DOTALL,
        )
    m = _MALFORMED_CALL_RE.search(failed_generation or "")
    if not m:
        return None
    tool_name, raw_args = m.group(1), m.group(2)
    if tool_name not in _SAFE_FALLBACK_TOOLS:
        return None
    try:
        args = json.loads(raw_args)
    except json.JSONDecodeError:
        return None
    if not isinstance(args, dict):
        return None

    from src.agent.tools import ALL_TOOLS
    tool_fn = next((t for t in ALL_TOOLS if t.name == tool_name), None)
    if tool_fn is None:
        return None
    try:
        result = await asyncio.to_thread(tool_fn.invoke, args)
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except json.JSONDecodeError:
                result = {"tool": tool_name, "status": "success", "title": result}
        if isinstance(result, dict):
            return result
    except Exception as e:
        logging.warning("Malformed-call recovery for %s failed: %s", tool_name, e)
    return None


async def _astream_collect(agent, payload, config: dict, _surrogate):
    """Stream a graph run and collect (text, tools, last_title, raw_error).

    Returns ``raw_error`` truthy only when an unrecoverable exception is hit.
    Used by both the primary run and the fallback-model retry.
    """
    from src.utils.text_filters import clean_tts_text

    result_text = ""
    tools: list = []
    last_title: Optional[str] = None
    raw_error: Optional[Exception] = None
    try:
        async for event in agent.astream_events(payload, config=config, version="v2"):
            kind = event["event"]
            if kind == "on_chat_model_stream":
                chunk = event["data"]["chunk"]
                content = chunk.content if hasattr(chunk, "content") else ""
                if content:
                    content = _surrogate.sub("", content)
                    cleaned = clean_tts_text(content)
                    if cleaned:
                        result_text += cleaned
            elif kind == "on_tool_end":
                output = event["data"].get("output", "")
                if not hasattr(output, "content"):
                    continue
                try:
                    parsed = (
                        json.loads(output.content)
                        if isinstance(output.content, str)
                        else output.content
                    )
                except (json.JSONDecodeError, TypeError):
                    continue
                if isinstance(parsed, dict):
                    tools.append(parsed)
                    if parsed.get("title"):
                        last_title = parsed["title"]
    except Exception as e:
        raw_error = e
    return result_text, tools, last_title, raw_error


async def _run_graph(agent, payload, config: dict):
    """Run the LangGraph agent once (initial input or Command resume) and
    collect the final state + any tool outputs streamed during execution.

    Returns (result_text, tool_results, last_tool_title, interrupted_payload).
    ``interrupted_payload`` is None unless the graph paused at an interrupt;
    when set it is the dict that was passed to ``interrupt(...)`` inside the
    paused tool, ready to be returned to the HTTP caller.
    """
    import re as _re
    from src.utils.text_filters import clean_tts_text

    _surrogate = _re.compile(r"[\ud800-\udfff]")
    result_text = ""
    tool_results: list = []
    last_tool_title: Optional[str] = None
    try:
        async for event in agent.astream_events(payload, config=config, version="v2"):
            kind = event["event"]
            if kind == "on_chat_model_stream":
                chunk = event["data"]["chunk"]
                content = chunk.content if hasattr(chunk, "content") else ""
                if content:
                    content = _surrogate.sub("", content)
                    cleaned = clean_tts_text(content)
                    if cleaned:
                        result_text += cleaned
            elif kind == "on_tool_end":
                output = event["data"].get("output", "")
                if not hasattr(output, "content"):
                    continue
                try:
                    parsed = (
                        json.loads(output.content)
                        if isinstance(output.content, str)
                        else output.content
                    )
                except (json.JSONDecodeError, TypeError):
                    continue
                if isinstance(parsed, dict):
                    tool_results.append(parsed)
                    if parsed.get("title"):
                        last_tool_title = parsed["title"]
    except Exception as e:
        # Groq's llama-3.1-8b sometimes emits a malformed `<function=...>{...}`
        # tool call which the API rejects with code=tool_use_failed.
        # Strategy:
        #   1. Retry once with the stronger fallback model (same checkpointer)
        #      — the 70b model never emits the malformed syntax.
        #   2. If that still fails, parse the failed_generation and invoke
        #      the tool directly (non-HITL pillars only).
        body = getattr(e, "body", None) or {}
        code = body.get("code") if isinstance(body, dict) else None
        if code == "tool_use_failed":
            failed_gen = body.get("failed_generation", "") if isinstance(body, dict) else ""
            logging.warning("Groq tool_use_failed (primary): %s", failed_gen[:200])

            # ---- (1) Fallback model retry on the SAME thread ---------------
            retried = False
            try:
                from src.agent.graph import get_fallback_agent
                fb_agent = get_fallback_agent()
                fb_text, fb_tools, fb_title, _ = await _astream_collect(
                    fb_agent, payload, config, _surrogate
                )
                if fb_tools or fb_text:
                    result_text = fb_text or result_text
                    tool_results.extend(fb_tools)
                    if fb_title:
                        last_tool_title = fb_title
                    retried = True
                    logging.info("Recovered via GROQ_FALLBACK_MODEL.")
            except Exception as fb_err:
                logging.warning("Fallback model retry also failed: %s", fb_err)

            # ---- (2) Manual parse-and-invoke for non-HITL tools ------------
            if not retried:
                recovered = await _recover_from_malformed_tool_call(failed_gen)
                if recovered is not None:
                    tool_results.append(recovered)
                    last_tool_title = recovered.get("title")
                    title_text = recovered.get("title") or ""
                    result_text = f"Done. {title_text}." if title_text else "Done."
                else:
                    tool_results.append({
                        "tool": "router",
                        "status": "error",
                        "icon": "alert-circle",
                        "title": "Tool call rejected by the model",
                        "details": {
                            "error": "The language model emitted a malformed tool "
                                     "call. Please rephrase or try again.",
                            "failed_generation": failed_gen[:300],
                        },
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                    result_text = "I couldn't complete that — please rephrase and try again."
        else:
            logging.error(f"Chat error: {e}")
            result_text = "I'm sorry, I encountered an issue processing that request."

    result_text = _surrogate.sub("", result_text)

    # After the run, inspect the persisted state for an interrupt.
    interrupted_payload = None
    try:
        snapshot = await agent.aget_state(config)
        # LangGraph 0.2+: interrupts live on snapshot.tasks[*].interrupts[*].value
        for task in getattr(snapshot, "tasks", []) or []:
            interrupts = getattr(task, "interrupts", None) or []
            if interrupts:
                val = interrupts[0].value
                if isinstance(val, dict):
                    interrupted_payload = val
                    break
    except Exception as e:
        logging.warning(f"State snapshot failed: {e}")

    return result_text, tool_results, last_tool_title, interrupted_payload


# Backwards-compat helper used by `/api/summarise` etc.
async def _stream_agent_response(agent, messages_in: list, config: dict):
    text, tools, title, _ = await _run_graph(
        agent, {"messages": messages_in}, config
    )
    return text, tools, title


async def _persist_turn(memory, session_id: str, user_id: str, message: str,
                        result_text: str, last_tool_title: Optional[str]) -> None:
    """Best-effort store of this turn + auto-detect user preferences."""
    if memory is None:
        return
    from src.memory.preferences import detect_preferences
    try:
        await memory.store_interaction(session_id, user_id, "user", message)
        for k, v in detect_preferences(message).items():
            await memory.store_user_preference(user_id, k, v)
        if result_text:
            await memory.store_interaction(
                session_id, user_id, "assistant", result_text,
                metadata={"tool": last_tool_title} if last_tool_title else None,
            )
    except Exception as e:
        logging.warning(f"Memory persist skipped: {e}")


@api_router.post("/chat")
async def chat_message(request: Request):
    body = await request.json()
    message = body.get("message", "")
    session_id = body.get("session_id", "default")
    user_id = body.get("user_id", "default")
    if not message:
        raise HTTPException(status_code=400, detail="message is required")

    from src.agent.graph import get_agent
    from src.agent.runtime_context import current_user_id
    from src.utils.text_filters import sanitize_transcript_text

    _user_token = current_user_id.set(user_id)
    try:
        _touch_thread(session_id)
        messages_in, memory = await _build_messages_with_memory(message, user_id)
        agent = get_agent()
        config = {"configurable": {"thread_id": session_id}}

        result_text, tool_results, last_tool_title, interrupted = await _run_graph(
            agent, {"messages": messages_in}, config
        )

        # ------------------------------------------------------------------
        # HITL: graph paused before a state-changing tool. Return a clean
        # interruption envelope so the client can show a confirmation UI.
        # ------------------------------------------------------------------
        if interrupted:
            tool_name = interrupted.get("tool_name") or "unknown"
            payload_preview = interrupted.get("payload_preview") or {}
            return {
                "interrupted": True,
                "tool_name": tool_name,
                "payload_preview": payload_preview,
                "session_id": session_id,
                "user_id": user_id,
                "response": (
                    f"Ready to {tool_name.replace('_', ' ')} — "
                    "review the preview and approve to proceed."
                ),
                "tool_results": tool_results,
                "timestamp": datetime.now().isoformat(),
            }

        if not result_text.strip() and last_tool_title:
            result_text = f"Done. {last_tool_title}."
        result_text = sanitize_transcript_text(result_text)
        if not result_text and last_tool_title:
            result_text = f"Done. {last_tool_title}."

        await _persist_turn(
            memory, session_id, user_id, message, result_text, last_tool_title
        )
    finally:
        current_user_id.reset(_user_token)

    return {
        "interrupted": False,
        "response": result_text,
        "tool_results": tool_results,
        "session_id": session_id,
        "user_id": user_id,
        "timestamp": datetime.now().isoformat(),
    }


# --- /chat/resume: continue an interrupted HITL flow -----------------------
@api_router.post("/chat/resume")
async def chat_resume(request: Request):
    """
    Resume an interrupted graph thread.

    Body:
        {
          "session_id": "<thread_id used in /api/chat>",
          "user_id":    "<application user id>",
          "approved":   true | false,
          "overrides":  { "to": "...", "subject": "...", ... }  # optional,
          "reason":     "..."                                    # optional
        }
    """
    from langgraph.types import Command

    from src.agent.graph import get_agent
    from src.agent.runtime_context import current_user_id
    from src.utils.text_filters import sanitize_transcript_text

    body = await request.json()
    session_id = body.get("session_id", "default")
    user_id = body.get("user_id", "default")
    approved = bool(body.get("approved", False))
    overrides = body.get("overrides") or {}
    reason = body.get("reason")

    resume_value = {"approved": approved}
    if overrides and isinstance(overrides, dict):
        resume_value.update(overrides)
    if reason:
        resume_value["reason"] = reason

    _user_token = current_user_id.set(user_id)
    try:
        _touch_thread(session_id)
        agent = get_agent()
        config = {"configurable": {"thread_id": session_id}}

        result_text, tool_results, last_tool_title, interrupted = await _run_graph(
            agent, Command(resume=resume_value), config
        )

        if interrupted:
            return {
                "interrupted": True,
                "tool_name": interrupted.get("tool_name"),
                "payload_preview": interrupted.get("payload_preview", {}),
                "session_id": session_id,
                "user_id": user_id,
                "tool_results": tool_results,
                "timestamp": datetime.now().isoformat(),
            }

        if not result_text.strip() and last_tool_title:
            result_text = f"Done. {last_tool_title}."
        result_text = sanitize_transcript_text(result_text)
        if not result_text and last_tool_title:
            result_text = f"Done. {last_tool_title}."
    finally:
        current_user_id.reset(_user_token)

    return {
        "interrupted": False,
        "approved": approved,
        "response": result_text,
        "tool_results": tool_results,
        "session_id": session_id,
        "user_id": user_id,
        "timestamp": datetime.now().isoformat(),
    }

# --- Conversation Storage ---
_conversations: dict = defaultdict(list)

@api_router.post("/conversation/save")
async def save_conversation(request: Request):
    body = await request.json()
    user_id = body.get("user_id", "anonymous")
    _conversations[user_id].append({
        "session_id": body.get("session_id", ""),
        "summary": body.get("summary", ""),
        "messages": body.get("messages", []),
        "tool_results": body.get("tool_results", []),
        "timestamp": body.get("timestamp", datetime.now().isoformat()),
        "duration_seconds": body.get("duration_seconds", 0)
    })
    return {"status": "saved"}

@api_router.get("/conversation/history")
async def get_history(user_id: str = Query("anonymous")):
    convos = _conversations.get(user_id, [])
    return {"conversations": sorted(convos, key=lambda x: x["timestamp"], reverse=True)[:20]}

@api_router.get("/conversation/{session_id}")
async def get_conversation(session_id: str, user_id: str = Query("anonymous")):
    convos = _conversations.get(user_id, [])
    for c in convos:
        if c["session_id"] == session_id:
            return c
    return {"error": "not found"}

# --- Summarise ---
@api_router.post("/summarise")
async def summarise_conversation(request: Request):
    body = await request.json()
    messages = body.get("messages", [])
    if not messages:
        return {"summary": "No messages to summarise."}
    
    from langchain_openai import ChatOpenAI
    try:
        llm = ChatOpenAI(
            model="llama-3.3-70b-versatile",
            base_url="https://api.groq.com/openai/v1",
            api_key=os.getenv("GROQ_API_KEY"), temperature=0.3
        )
        history = "\n".join([f"{m.get('role', 'user').upper()}: {m.get('text', '')}" for m in messages[-20:]])
        response = await llm.ainvoke(
            f"Summarise this voice assistant conversation in 2-3 sentences, listing what tasks were completed:\n\n{history}"
        )
        return {"summary": response.content}
    except Exception as e:
        logging.error(f"Summarise error: {e}")
        return {"summary": "Session completed with " + str(len(messages)) + " messages exchanged."}

# --- System Status ---
@api_router.get("/status")
async def get_system_status():
    statuses = {}
    statuses["LiveKit"] = "connected" if all([os.getenv("LIVEKIT_URL"), os.getenv("LIVEKIT_API_KEY")]) else "error"
    statuses["Groq LLM"] = "healthy" if os.getenv("GROQ_API_KEY") else "error"
    statuses["Deepgram STT"] = "active" if os.getenv("DEEPGRAM_API_KEY") else "error"
    statuses["Cartesia TTS"] = "active" if os.getenv("CARTESIA_API_KEY") else "error"
    statuses["API Server"] = "healthy"
    return {"status": statuses, "timestamp": datetime.now().isoformat()}

# --- Health ---
@api_router.get("/health")
async def health_check():
    return {"status": "ok", "service": "taskbutler"}


# --- /speak: forward text to the agent's TTS via LiveKit data channel -----
@api_router.post("/speak")
async def speak_text(request: Request):
    """Tell the agent in a given LiveKit room to speak the supplied text."""
    try:
        body = await request.json()
    except Exception:
        return {"error": "invalid json body"}

    text = (body.get("text") or "").strip()
    room_name = (body.get("room") or "").strip()
    if not text or not room_name:
        return {"error": "text and room required"}

    try:
        from livekit import api as livekit_api
        lk = livekit_api.LiveKitAPI(
            url=os.getenv("LIVEKIT_URL"),
            api_key=os.getenv("LIVEKIT_API_KEY"),
            api_secret=os.getenv("LIVEKIT_API_SECRET"),
        )
        payload = json.dumps({"type": "speak_request", "text": text}).encode("utf-8")
        await lk.room.send_data(
            livekit_api.SendDataRequest(room=room_name, data=payload)
        )
        return {"status": "sent", "text": text}
    except Exception as e:
        logging.warning("speak forwarding failed: %s", e)
        return {"status": "ok", "note": str(e)}


# --- Memory of You (Phase 3.5) ---
@api_router.get("/memory/me")
async def memory_overview(user_id: str = Query("default")):
    """Return everything TaskButler remembers about a user."""
    from src.memory.vector_store import get_memory
    memory = await get_memory()
    prefs = await memory.get_user_preferences(user_id)
    interactions = await memory.list_recent_interactions(user_id, limit=30)
    todos = await memory.list_todos(user_id, include_done=True)
    return {
        "user_id": user_id,
        "preferences": prefs,
        "interactions": interactions,
        "todos": todos,
        "counts": {
            "preferences": len(prefs),
            "interactions": len(interactions),
            "todos": len(todos),
        },
        "timestamp": datetime.now().isoformat(),
    }


@api_router.delete("/memory/preference")
async def memory_forget_preference(
    user_id: str = Query(...), key: str = Query(...)
):
    from src.memory.vector_store import get_memory
    memory = await get_memory()
    ok = await memory.delete_user_preference(user_id, key)
    if not ok:
        raise HTTPException(status_code=404, detail=f"preference '{key}' not found")
    return {"status": "forgotten", "user_id": user_id, "key": key}


@api_router.delete("/memory/interaction")
async def memory_forget_interaction(
    user_id: str = Query(...), id: str = Query(...)
):
    from src.memory.vector_store import get_memory
    memory = await get_memory()
    ok = await memory.delete_interaction(user_id, id)
    if not ok:
        raise HTTPException(status_code=404, detail="interaction not found")
    return {"status": "forgotten", "user_id": user_id, "id": id}


@api_router.post("/memory/wipe")
async def memory_wipe(user_id: str = Query(...)):
    """Forget EVERYTHING about a user."""
    from src.memory.vector_store import get_memory
    memory = await get_memory()
    deleted = await memory.wipe_user(user_id)
    return {"status": "wiped", "user_id": user_id, "deleted": deleted}


# --- HITL idle expiry: sweep stale checkpoint threads --------------------
# Each /api/chat and /api/chat/resume call updates ``_thread_last_seen``.
# A background task periodically purges threads idle for > HITL_TTL_SECONDS,
# preventing the in-memory MemorySaver from accumulating abandoned
# approval requests indefinitely.
HITL_TTL_SECONDS = int(os.getenv("HITL_TTL_SECONDS", "1800"))      # 30 min
HITL_SWEEP_INTERVAL = int(os.getenv("HITL_SWEEP_INTERVAL", "300")) # 5 min
_thread_last_seen: dict = {}


def _touch_thread(session_id: str) -> None:
    _thread_last_seen[session_id] = datetime.now(timezone.utc)


def _purge_thread(memory, thread_id: str) -> bool:
    """Best-effort removal of a thread's checkpoints from MemorySaver."""
    removed = False
    for attr in ("storage", "writes"):
        bucket = getattr(memory, attr, None)
        if isinstance(bucket, dict) and thread_id in bucket:
            bucket.pop(thread_id, None)
            removed = True
    return removed


async def _hitl_ttl_sweep_loop():
    """Background coroutine: every HITL_SWEEP_INTERVAL seconds, drop any
    thread whose last activity is older than HITL_TTL_SECONDS."""
    from src.agent.graph import get_memory

    while True:
        try:
            await asyncio.sleep(HITL_SWEEP_INTERVAL)
            now = datetime.now(timezone.utc)
            cutoff = now - timedelta(seconds=HITL_TTL_SECONDS)
            stale = [tid for tid, ts in _thread_last_seen.items() if ts < cutoff]
            if not stale:
                continue
            memory = get_memory()
            purged = 0
            for tid in stale:
                if _purge_thread(memory, tid):
                    purged += 1
                _thread_last_seen.pop(tid, None)
            if purged:
                logging.info(
                    "HITL sweep: purged %d/%d stale threads (ttl=%ss)",
                    purged, len(stale), HITL_TTL_SECONDS,
                )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logging.warning("HITL sweep iteration failed: %s", e)


# Include router
app.include_router(api_router)

logger = logging.getLogger(__name__)

# --- Auto-start LiveKit Agent Worker ---
_worker_process = None
_hitl_sweep_task: Optional[asyncio.Task] = None

@app.on_event("startup")
async def start_livekit_worker():
    global _worker_process, _hitl_sweep_task
    try:
        subprocess.run(["bash", "-c", "kill $(lsof -ti:8081) 2>/dev/null"], capture_output=True)
        await asyncio.sleep(1)
        _worker_process = subprocess.Popen(
            ["/root/.venv/bin/python", "-m", "src.main", "start"],
            cwd="/app/backend",
            stdout=open("/var/log/livekit_worker.log", "w"),
            stderr=subprocess.STDOUT,
        )
        logger.info(f"LiveKit agent worker started with PID: {_worker_process.pid}")
    except Exception as e:
        logger.error(f"Failed to start LiveKit agent worker: {e}")

    # Background HITL idle-expiry sweeper.
    _hitl_sweep_task = asyncio.create_task(_hitl_ttl_sweep_loop())
    logger.info(
        "HITL TTL sweep started (ttl=%ss, interval=%ss)",
        HITL_TTL_SECONDS, HITL_SWEEP_INTERVAL,
    )

@app.on_event("shutdown")
async def shutdown_services():
    global _worker_process, _hitl_sweep_task
    if _hitl_sweep_task and not _hitl_sweep_task.done():
        _hitl_sweep_task.cancel()
    if _worker_process:
        _worker_process.terminate()
    client.close()
