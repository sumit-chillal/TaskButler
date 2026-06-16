"""TaskButler - ChromaDB-backed Vector Memory

A persistent memory layer that augments LangGraph's in-process
``MemorySaver`` checkpointer. Three collections:

* ``interactions`` - conversation turns (semantic recall)
* ``preferences``  - per-user named preferences
* ``todos``        - persistent todo items (used by ``manage_todo``)

ChromaDB's Python client is synchronous; every blocking call is wrapped
in ``asyncio.to_thread`` to keep the LiveKit event loop responsive.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import chromadb
from chromadb.utils import embedding_functions

logger = logging.getLogger(__name__)

DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TaskButlerMemory:
    """Persistent vector memory backed by ChromaDB."""

    def __init__(self, persist_dir: Optional[str] = None,
                 embedding_model: Optional[str] = None) -> None:
        self._persist_dir = persist_dir
        self._embedding_model = embedding_model
        self._client = None
        self._embedding_fn = None
        self._interactions = None
        self._preferences = None
        self._todos = None
        self._initialized = False
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def initialize(self) -> None:
        if self._initialized:
            return
        async with self._lock:
            if self._initialized:
                return
            persist_dir = (
                self._persist_dir
                or os.getenv("CHROMA_PERSIST_DIR")
                or str(Path(__file__).resolve().parents[3] / "chroma_db")
            )
            model = (
                self._embedding_model
                or os.getenv("EMBEDDING_MODEL")
                or DEFAULT_EMBEDDING_MODEL
            )
            Path(persist_dir).mkdir(parents=True, exist_ok=True)
            try:
                await asyncio.to_thread(self._init_sync, persist_dir, model)
                self._initialized = True
                logger.info(
                    "TaskButlerMemory ready (persist_dir=%s, model=%s)",
                    persist_dir, model,
                )
            except Exception as e:
                logger.error("TaskButlerMemory init failed: %s", e, exc_info=True)
                raise

    def _init_sync(self, persist_dir: str, model: str) -> None:
        self._client = chromadb.PersistentClient(path=persist_dir)
        self._embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=model
        )
        for coll_name, attr in (
            ("interactions", "_interactions"),
            ("preferences", "_preferences"),
            ("todos", "_todos"),
        ):
            coll = self._client.get_or_create_collection(
                name=coll_name,
                embedding_function=self._embedding_fn,
                metadata={"hnsw:space": "cosine"},
            )
            setattr(self, attr, coll)

    # ------------------------------------------------------------------
    # Interactions
    # ------------------------------------------------------------------
    async def store_interaction(
        self,
        session_id: str,
        user_id: str,
        role: str,
        content: str,
        metadata: Optional[dict] = None,
    ) -> str:
        await self.initialize()
        if not content or not content.strip():
            return ""
        meta: dict[str, Any] = {
            "session_id": session_id,
            "user_id": user_id,
            "role": role,
            "timestamp": _now_iso(),
        }
        if metadata:
            for k, v in metadata.items():
                if isinstance(v, (list, tuple, set)):
                    meta[k] = ",".join(str(x) for x in v)
                elif isinstance(v, (str, int, float, bool)) or v is None:
                    meta[k] = v
                else:
                    meta[k] = str(v)
        doc_id = uuid.uuid4().hex
        await asyncio.to_thread(
            self._interactions.add,
            ids=[doc_id], documents=[content], metadatas=[meta],
        )
        return doc_id

    async def retrieve_relevant_context(
        self, query: str, user_id: str, n_results: int = 5,
    ) -> list[dict]:
        await self.initialize()
        if not query.strip():
            return []
        try:
            res = await asyncio.to_thread(
                self._interactions.query,
                query_texts=[query],
                n_results=n_results,
                where={"user_id": user_id},
            )
        except Exception as e:
            logger.warning("retrieve_relevant_context failed: %s", e)
            return []
        out: list[dict] = []
        docs = (res.get("documents") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]
        for d, m, dist in zip(docs, metas, dists):
            out.append({"content": d, "metadata": m or {}, "distance": dist})
        return out

    # ------------------------------------------------------------------
    # Preferences
    # ------------------------------------------------------------------
    async def store_user_preference(
        self, user_id: str, preference_key: str, preference_value: str,
    ) -> None:
        await self.initialize()
        doc_id = f"{user_id}::{preference_key}"
        meta = {
            "user_id": user_id,
            "key": preference_key,
            "value": preference_value,
            "timestamp": _now_iso(),
        }
        await asyncio.to_thread(
            self._preferences.upsert,
            ids=[doc_id],
            documents=[f"{preference_key}: {preference_value}"],
            metadatas=[meta],
        )

    async def get_user_preferences(self, user_id: str) -> dict:
        await self.initialize()
        try:
            res = await asyncio.to_thread(
                self._preferences.get, where={"user_id": user_id}
            )
        except Exception as e:
            logger.warning("get_user_preferences failed: %s", e)
            return {}
        prefs: dict[str, str] = {}
        for m in (res.get("metadatas") or []):
            if m and m.get("key"):
                prefs[m["key"]] = m.get("value", "")
        return prefs

    # ------------------------------------------------------------------
    # Todos
    # ------------------------------------------------------------------
    async def store_todo(
        self, user_id: str, task: str, metadata: Optional[dict] = None,
    ) -> str:
        await self.initialize()
        task_id = uuid.uuid4().hex[:8]
        meta: dict[str, Any] = {
            "user_id": user_id,
            "task_id": task_id,
            "task": task,
            "done": False,
            "created": _now_iso(),
        }
        if metadata:
            for k, v in metadata.items():
                if isinstance(v, (list, tuple, set)):
                    meta[k] = ",".join(str(x) for x in v)
                elif isinstance(v, (str, int, float, bool)) or v is None:
                    meta[k] = v
                else:
                    meta[k] = str(v)
        await asyncio.to_thread(
            self._todos.add, ids=[task_id], documents=[task], metadatas=[meta]
        )
        return task_id

    async def list_todos(
        self, user_id: str, include_done: bool = False,
    ) -> list[dict]:
        await self.initialize()
        where: dict[str, Any]
        if include_done:
            where = {"user_id": user_id}
        else:
            where = {"$and": [{"user_id": user_id}, {"done": False}]}
        try:
            res = await asyncio.to_thread(self._todos.get, where=where)
        except Exception as e:
            logger.warning("list_todos failed: %s", e)
            return []
        out = []
        for tid, doc, meta in zip(
            res.get("ids") or [],
            res.get("documents") or [],
            res.get("metadatas") or [],
        ):
            row = {"id": tid, "task": doc}
            if meta:
                row.update(meta)
            out.append(row)
        return out

    async def mark_todo_done(self, user_id: str, task_id: str) -> bool:
        await self.initialize()
        try:
            res = await asyncio.to_thread(self._todos.get, ids=[task_id])
            if not (res.get("ids") or []):
                return False
            meta = ((res.get("metadatas") or [{}]) or [{}])[0] or {}
            if meta.get("user_id") != user_id:
                return False
            meta["done"] = True
            meta["completed"] = _now_iso()
            await asyncio.to_thread(
                self._todos.update, ids=[task_id], metadatas=[meta]
            )
            return True
        except Exception as e:
            logger.warning("mark_todo_done failed: %s", e)
            return False

    async def delete_todo(self, user_id: str, task_id: str) -> bool:
        await self.initialize()
        try:
            res = await asyncio.to_thread(self._todos.get, ids=[task_id])
            if not (res.get("ids") or []):
                return False
            meta = ((res.get("metadatas") or [{}]) or [{}])[0] or {}
            if meta.get("user_id") != user_id:
                return False
            await asyncio.to_thread(self._todos.delete, ids=[task_id])
            return True
        except Exception as e:
            logger.warning("delete_todo failed: %s", e)
            return False


    async def delete_user_preference(self, user_id: str, preference_key: str) -> bool:
        """Forget a single named preference for a user. Returns True if removed."""
        await self.initialize()
        doc_id = f"{user_id}::{preference_key}"
        try:
            res = await asyncio.to_thread(self._preferences.get, ids=[doc_id])
            if not (res.get("ids") or []):
                return False
            await asyncio.to_thread(self._preferences.delete, ids=[doc_id])
            return True
        except Exception as e:
            logger.warning("delete_user_preference failed: %s", e)
            return False

    async def list_recent_interactions(
        self, user_id: str, limit: int = 20,
    ) -> list[dict]:
        """Return the most recent stored interactions for a user, newest first."""
        await self.initialize()
        try:
            res = await asyncio.to_thread(
                self._interactions.get, where={"user_id": user_id}
            )
        except Exception as e:
            logger.warning("list_recent_interactions failed: %s", e)
            return []
        rows = []
        for tid, doc, meta in zip(
            res.get("ids") or [],
            res.get("documents") or [],
            res.get("metadatas") or [],
        ):
            rows.append({"id": tid, "content": doc, **(meta or {})})
        rows.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
        return rows[:limit]

    async def delete_interaction(self, user_id: str, interaction_id: str) -> bool:
        """Forget a single past interaction by id."""
        await self.initialize()
        try:
            res = await asyncio.to_thread(
                self._interactions.get, ids=[interaction_id]
            )
            if not (res.get("ids") or []):
                return False
            meta = ((res.get("metadatas") or [{}]) or [{}])[0] or {}
            if meta.get("user_id") != user_id:
                return False
            await asyncio.to_thread(
                self._interactions.delete, ids=[interaction_id]
            )
            return True
        except Exception as e:
            logger.warning("delete_interaction failed: %s", e)
            return False

    async def wipe_user(self, user_id: str) -> dict:
        """Forget EVERYTHING for a user (preferences + interactions + todos)."""
        await self.initialize()
        deleted = {"preferences": 0, "interactions": 0, "todos": 0}
        for attr, key in (
            ("_preferences", "preferences"),
            ("_interactions", "interactions"),
            ("_todos", "todos"),
        ):
            coll = getattr(self, attr)
            try:
                res = await asyncio.to_thread(coll.get, where={"user_id": user_id})
                ids = res.get("ids") or []
                if ids:
                    await asyncio.to_thread(coll.delete, ids=ids)
                    deleted[key] = len(ids)
            except Exception as e:
                logger.warning("wipe_user %s failed: %s", key, e)
        return deleted


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------
_memory: Optional[TaskButlerMemory] = None
_singleton_lock = asyncio.Lock()


async def get_memory() -> TaskButlerMemory:
    global _memory
    if _memory is not None and _memory._initialized:
        return _memory
    async with _singleton_lock:
        if _memory is None:
            _memory = TaskButlerMemory()
        if not _memory._initialized:
            await _memory.initialize()
    return _memory
