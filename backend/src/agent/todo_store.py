"""TaskButler - Persistent Todo Store

Phase 2 stub: a JSON-file-backed todo store with the same interface that
will be used in Phase 3 once ChromaDB is wired in. The class is designed
to be hot-swapped \u2014 only the constructor and the four public methods
(``add``, ``list_all``, ``complete``, ``delete``) need to be re-implemented
on top of ChromaDB; the tool layer is unchanged.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DEFAULT_PATH = Path(__file__).resolve().parent / "todo_store.json"


class TodoStore:
    """File-backed persistent todo list (single-process safe via threading.Lock)."""

    def __init__(self, path: Optional[str] = None) -> None:
        self._path = Path(path or os.getenv("TODO_STORE_PATH") or _DEFAULT_PATH)
        self._lock = threading.Lock()
        self._items: list[dict] = []
        self._load()

    # ---- IO -------------------------------------------------------------
    def _load(self) -> None:
        try:
            if self._path.exists():
                with self._path.open("r", encoding="utf-8") as fh:
                    data = json.load(fh)
                if isinstance(data, list):
                    self._items = data
        except Exception as e:
            logger.warning("TodoStore load failed (%s); starting fresh", e)
            self._items = []

    def _flush(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(self._path.suffix + ".tmp")
            with tmp.open("w", encoding="utf-8") as fh:
                json.dump(self._items, fh, indent=2, ensure_ascii=False)
            tmp.replace(self._path)
        except Exception as e:
            logger.error("TodoStore flush failed: %s", e)

    # ---- Public API -----------------------------------------------------
    def add(self, task: str) -> dict:
        with self._lock:
            item = {
                "id": uuid.uuid4().hex[:8],
                "task": task,
                "done": False,
                "created": datetime.now().isoformat(),
            }
            self._items.append(item)
            self._flush()
            return item

    def list_all(self) -> list[dict]:
        with self._lock:
            return list(self._items)

    def complete(self, *, task: str = "", task_id: str = "") -> Optional[dict]:
        with self._lock:
            target = self._find(task=task, task_id=task_id)
            if target is None:
                return None
            target["done"] = True
            target["completed"] = datetime.now().isoformat()
            self._flush()
            return target

    def delete(self, *, task: str = "", task_id: str = "") -> Optional[dict]:
        with self._lock:
            target = self._find(task=task, task_id=task_id)
            if target is None:
                return None
            self._items = [i for i in self._items if i["id"] != target["id"]]
            self._flush()
            return target

    def count(self) -> int:
        with self._lock:
            return len(self._items)

    # ---- Helpers --------------------------------------------------------
    def _find(self, *, task: str, task_id: str) -> Optional[dict]:
        for item in self._items:
            if task_id and item["id"] == task_id:
                return item
            if task and item["task"].lower() == task.lower():
                return item
        return None


# Singleton accessor (matches the Phase 3 ChromaDB-backed implementation)
_store: Optional["TodoStore"] = None


def get_todo_store() -> TodoStore:
    """Lazy singleton: creates the JSON-backed store on first call."""
    global _store
    if _store is None:
        _store = TodoStore()
    return _store
