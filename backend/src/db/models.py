"""TaskButler — MongoDB schema for OAuth credentials.

Stores Google OAuth tokens per ``user_id``. Both ``refresh_token`` and
``access_token`` are encrypted at rest with Fernet (symmetric AES-128).
The encryption key is derived from ``AUTH_SECRET`` so credentials remain
unreadable even if the Mongo dump leaks, provided ``AUTH_SECRET`` itself
is rotated and kept out of version control.

Public surface:

    UserOAuthCredentials             — Pydantic model returned to callers
    GoogleOAuthRepo                  — async repo wrapping the Mongo collection
        await repo.upsert(user_id, payload)
        await repo.get(user_id)               -> UserOAuthCredentials | None
        await repo.delete(user_id)            -> bool
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
from datetime import datetime, timezone
from typing import List, Optional

from cryptography.fernet import Fernet, InvalidToken
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Encryption helpers — Fernet key derived deterministically from AUTH_SECRET.
# ---------------------------------------------------------------------------
def _derive_fernet_key(secret: str) -> bytes:
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _fernet() -> Fernet:
    secret = os.getenv("AUTH_SECRET")
    if not secret:
        raise RuntimeError(
            "AUTH_SECRET must be set in the environment to encrypt OAuth tokens."
        )
    return Fernet(_derive_fernet_key(secret))


def _encrypt(plain: Optional[str]) -> Optional[str]:
    if not plain:
        return None
    return _fernet().encrypt(plain.encode("utf-8")).decode("utf-8")


def _decrypt(cipher: Optional[str]) -> Optional[str]:
    if not cipher:
        return None
    try:
        return _fernet().decrypt(cipher.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        logger.error("Failed to decrypt token — AUTH_SECRET may have rotated.")
        return None


# ---------------------------------------------------------------------------
# Pydantic schema
# ---------------------------------------------------------------------------
class UserOAuthCredentials(BaseModel):
    """OAuth credentials for a single user (Google Workspace).

    Tokens are stored encrypted in Mongo and decrypted lazily on read.
    ``access_token_expiry`` is a UTC datetime; callers should treat the
    record as stale if ``datetime.now(timezone.utc) >= access_token_expiry``
    and refresh via the ``refresh_token``.
    """

    user_id: str = Field(..., description="Stable application user id")
    provider: str = Field(default="google", description="OAuth provider name")
    email: Optional[str] = Field(default=None)
    scopes: List[str] = Field(default_factory=list)
    access_token: Optional[str] = Field(default=None)
    refresh_token: Optional[str] = Field(default=None)
    access_token_expiry: Optional[datetime] = Field(default=None)
    token_type: str = Field(default="Bearer")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def is_access_token_valid(self, slack_seconds: int = 60) -> bool:
        """Return True when the cached access_token has > slack_seconds left."""
        if not self.access_token or not self.access_token_expiry:
            return False
        now = datetime.now(timezone.utc)
        exp = self.access_token_expiry
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return (exp - now).total_seconds() > slack_seconds


# ---------------------------------------------------------------------------
# Mongo repository
# ---------------------------------------------------------------------------
class GoogleOAuthRepo:
    COLLECTION = "user_oauth_credentials"

    def __init__(self, mongo_url: Optional[str] = None, db_name: Optional[str] = None) -> None:
        url = mongo_url or os.getenv("MONGO_URL")
        if not url:
            raise RuntimeError("MONGO_URL must be set.")
        self._client = AsyncIOMotorClient(url)
        self._db = self._client[db_name or os.getenv("DB_NAME", "taskbutler")]
        self._col: AsyncIOMotorCollection = self._db[self.COLLECTION]

    async def ensure_indexes(self) -> None:
        # Drop a legacy single-field unique index on user_id if present —
        # we now key on (user_id, provider) so the same user can link
        # multiple providers (e.g. google + spotify).
        try:
            existing = await self._col.index_information()
            if "user_id_1" in existing and existing["user_id_1"].get("unique"):
                await self._col.drop_index("user_id_1")
        except Exception as e:
            logger.warning("index reconcile skipped: %s", e)
        await self._col.create_index(
            [("user_id", 1), ("provider", 1)], unique=True, name="user_provider_uniq"
        )
        await self._col.create_index("provider")

    async def upsert(self, creds: UserOAuthCredentials) -> None:
        doc = creds.model_dump()
        doc["access_token"] = _encrypt(creds.access_token)
        doc["refresh_token"] = _encrypt(creds.refresh_token)
        doc["updated_at"] = datetime.now(timezone.utc)
        # _id is the natural user_id+provider composite for easy lookup.
        await self._col.update_one(
            {"user_id": creds.user_id, "provider": creds.provider},
            {"$set": doc, "$setOnInsert": {"created_at": doc.get("created_at")}},
            upsert=True,
        )

    async def get(self, user_id: str, provider: str = "google") -> Optional[UserOAuthCredentials]:
        doc = await self._col.find_one(
            {"user_id": user_id, "provider": provider}, projection={"_id": 0}
        )
        if not doc:
            return None
        doc["access_token"] = _decrypt(doc.get("access_token"))
        doc["refresh_token"] = _decrypt(doc.get("refresh_token"))
        return UserOAuthCredentials(**doc)

    async def update_access_token(
        self,
        user_id: str,
        access_token: str,
        access_token_expiry: datetime,
        provider: str = "google",
    ) -> None:
        await self._col.update_one(
            {"user_id": user_id, "provider": provider},
            {
                "$set": {
                    "access_token": _encrypt(access_token),
                    "access_token_expiry": access_token_expiry,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )

    async def delete(self, user_id: str, provider: str = "google") -> bool:
        res = await self._col.delete_one(
            {"user_id": user_id, "provider": provider}
        )
        return res.deleted_count > 0


# Singleton — Mongo client is connection-pool friendly, but we keep one
# repo per *event loop* because ``AsyncIOMotorClient`` binds to whichever
# loop is running at construction time. Reusing it from a different loop
# raises "Event loop is closed" — which surfaces in our sync tool wrapper
# (``_run_async``) that spins up a fresh loop per invocation.
import asyncio as _asyncio

_repo_per_loop: dict = {}


async def get_oauth_repo() -> GoogleOAuthRepo:
    loop = _asyncio.get_running_loop()
    repo = _repo_per_loop.get(id(loop))
    if repo is None:
        repo = GoogleOAuthRepo()
        await repo.ensure_indexes()
        _repo_per_loop[id(loop)] = repo
    return repo
