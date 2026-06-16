"""TaskButler Agent package.

Houses the LangGraph ReAct agent definition (``graph.py``), the system
prompt (``prompts.py``), the existing capability tools (``tools.py``) and
the browser-automation tools (``browser_tools.py``).

Phase 2: existing tool stubs were upgraded to drive a real Chromium
browser via ``src/browser/engine.py`` and a persistent ChromaDB-backed
todo store (``todo_store.py``).
"""
