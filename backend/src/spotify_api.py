"""TaskButler — Spotify Web API helpers (Environment Orchestrator pillar).

Loads the user's Spotify OAuth credentials from MongoDB (stored under the
``spotify`` provider by ``GoogleOAuthRepo`` — the repo is provider-agnostic),
refreshes the access_token when stale, and exposes high-level helpers used
by the LangGraph tool layer.

Public surface:

    await get_spotify_access_token(user_id) -> str | None
    await play_focus_music(user_id, playlist_uri=...) -> dict
"""

from __future__ import annotations

import base64
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import httpx

from .db.models import UserOAuthCredentials, get_oauth_repo

logger = logging.getLogger(__name__)

_TOKEN_URI = "https://accounts.spotify.com/api/token"
_API_BASE = "https://api.spotify.com/v1"
_DEFAULT_PLAYLIST = "spotify:playlist:37i9dQZF1DWZeKCadgRdKQ"
_PROVIDER = "spotify"


def _basic_auth_header() -> dict[str, str]:
    client_id = os.getenv("SPOTIFY_CLIENT_ID") or ""
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET") or ""
    creds = f"{client_id}:{client_secret}".encode("utf-8")
    encoded = base64.b64encode(creds).decode("utf-8")
    return {"Authorization": f"Basic {encoded}"}


async def _refresh_access_token(record: UserOAuthCredentials) -> Optional[str]:
    """Use the refresh_token to obtain a fresh access_token. Returns the new token."""
    if not record.refresh_token:
        return None
    async with httpx.AsyncClient(timeout=15.0) as http:
        resp = await http.post(
            _TOKEN_URI,
            data={
                "grant_type": "refresh_token",
                "refresh_token": record.refresh_token,
            },
            headers={
                **_basic_auth_header(),
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
    if resp.status_code != 200:
        logger.error("Spotify token refresh failed: %s %s", resp.status_code, resp.text)
        return None
    tok = resp.json()
    new_access = tok.get("access_token")
    expires_in = int(tok.get("expires_in", 3600))
    new_expiry = datetime.now(timezone.utc).replace(microsecond=0)
    new_expiry = new_expiry.fromtimestamp(
        new_expiry.timestamp() + expires_in, tz=timezone.utc
    )

    repo = await get_oauth_repo()
    await repo.update_access_token(
        user_id=record.user_id,
        access_token=new_access,
        access_token_expiry=new_expiry,
        provider=_PROVIDER,
    )
    return new_access


async def get_spotify_access_token(user_id: str) -> Optional[str]:
    """Return a usable access_token, refreshing if necessary."""
    repo = await get_oauth_repo()
    record = await repo.get(user_id, provider=_PROVIDER)
    if record is None:
        return None
    if record.is_access_token_valid():
        return record.access_token
    return await _refresh_access_token(record)


async def play_focus_music(
    user_id: str,
    playlist_uri: str = _DEFAULT_PLAYLIST,
) -> dict:
    """Start playback of a Spotify playlist on the user's active device.

    Returns:
        {
          "playback_started": bool,
          "reason": str,            # "ok" | "no_active_device" | "not_linked"
                                    # | "premium_required" | "<http_status>" ...
          "playlist_uri": str,
          "details": dict,          # raw Spotify response or empty
        }
    """
    access_token = await get_spotify_access_token(user_id)
    if not access_token:
        return {
            "playback_started": False,
            "reason": "not_linked",
            "playlist_uri": playlist_uri,
            "details": {},
        }

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    body = {"context_uri": playlist_uri}

    try:
        async with httpx.AsyncClient(timeout=15.0) as http:
            resp = await http.put(f"{_API_BASE}/me/player/play", headers=headers, json=body)
    except Exception as e:
        logger.warning("Spotify play request failed: %s", e)
        return {
            "playback_started": False,
            "reason": "network_error",
            "playlist_uri": playlist_uri,
            "details": {"error": str(e)},
        }

    # Spotify returns 204 on success, 404 when there is no active device,
    # 403 when the account is non-Premium or the playlist is unavailable.
    if resp.status_code in (200, 202, 204):
        return {
            "playback_started": True,
            "reason": "ok",
            "playlist_uri": playlist_uri,
            "details": {"status_code": resp.status_code},
        }

    if resp.status_code == 404:
        return {
            "playback_started": False,
            "reason": "no_active_device",
            "playlist_uri": playlist_uri,
            "details": _safe_json(resp),
        }

    if resp.status_code == 403:
        return {
            "playback_started": False,
            "reason": "premium_required",
            "playlist_uri": playlist_uri,
            "details": _safe_json(resp),
        }

    return {
        "playback_started": False,
        "reason": str(resp.status_code),
        "playlist_uri": playlist_uri,
        "details": _safe_json(resp),
    }


def _safe_json(resp: httpx.Response) -> dict:
    try:
        return resp.json()
    except Exception:
        return {"text": resp.text[:400]}
