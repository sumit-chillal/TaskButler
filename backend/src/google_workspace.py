"""TaskButler — Google Workspace API helpers.

Builds authorised google-api-python-client services using the OAuth
credentials stored in MongoDB by ``src.db.models.GoogleOAuthRepo``.

Public helpers:

    await get_google_credentials(user_id)   -> google.oauth2.Credentials | None
    await send_gmail(user_id, to, subject, body) -> dict
    await insert_calendar_event(user_id, ...)    -> dict
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
from datetime import datetime, timezone
from email.mime.text import MIMEText
from typing import Optional

from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .db.models import GoogleOAuthRepo, UserOAuthCredentials, get_oauth_repo

logger = logging.getLogger(__name__)

_TOKEN_URI = "https://oauth2.googleapis.com/token"


async def get_google_credentials(user_id: str) -> Optional[Credentials]:
    """Load stored credentials, refresh if needed, return a usable Credentials."""
    repo: GoogleOAuthRepo = await get_oauth_repo()
    record: Optional[UserOAuthCredentials] = await repo.get(user_id)
    if record is None or not record.refresh_token:
        return None

    creds = Credentials(
        token=record.access_token,
        refresh_token=record.refresh_token,
        token_uri=_TOKEN_URI,
        client_id=os.getenv("GOOGLE_CLIENT_ID"),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
        scopes=record.scopes or None,
        expiry=record.access_token_expiry,
    )

    if not record.is_access_token_valid():
        # Run the blocking refresh() call off the event loop.
        await asyncio.to_thread(creds.refresh, GoogleRequest())
        new_expiry = creds.expiry
        if new_expiry and new_expiry.tzinfo is None:
            new_expiry = new_expiry.replace(tzinfo=timezone.utc)
        await repo.update_access_token(
            user_id=user_id,
            access_token=creds.token,
            access_token_expiry=new_expiry or datetime.now(timezone.utc),
        )
    return creds


async def send_gmail(user_id: str, to: str, subject: str, body: str) -> dict:
    """Send an email through gmail.users.messages.send. Returns API response."""
    creds = await get_google_credentials(user_id)
    if creds is None:
        return {"success": False, "error": "google_not_linked", "step": "credentials"}

    def _send() -> dict:
        service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        return (
            service.users()
            .messages()
            .send(userId="me", body={"raw": raw})
            .execute()
        )

    try:
        resp = await asyncio.to_thread(_send)
        return {
            "success": True,
            "message_id": resp.get("id"),
            "thread_id": resp.get("threadId"),
            "label_ids": resp.get("labelIds", []),
        }
    except HttpError as e:
        logger.error("Gmail send failed: %s", e)
        return {"success": False, "error": str(e), "step": "gmail.send"}


async def insert_calendar_event(
    user_id: str,
    summary: str,
    start_iso: str,
    end_iso: str,
    description: str = "",
    calendar_id: str = "primary",
    timezone_name: str = "UTC",
) -> dict:
    """Insert an event via events.insert with clean ISO 8601 timestamps."""
    creds = await get_google_credentials(user_id)
    if creds is None:
        return {"success": False, "error": "google_not_linked", "step": "credentials"}

    body = {
        "summary": summary,
        "description": description,
        "start": {"dateTime": start_iso, "timeZone": timezone_name},
        "end": {"dateTime": end_iso, "timeZone": timezone_name},
    }

    def _insert() -> dict:
        service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        return (
            service.events()
            .insert(calendarId=calendar_id, body=body)
            .execute()
        )

    try:
        resp = await asyncio.to_thread(_insert)
        return {
            "success": True,
            "event_id": resp.get("id"),
            "html_link": resp.get("htmlLink"),
            "status": resp.get("status"),
        }
    except HttpError as e:
        logger.error("Calendar insert failed: %s", e)
        return {"success": False, "error": str(e), "step": "calendar.insert"}
