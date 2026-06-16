# TaskButler — Product Requirements Document

## Original Problem Statement

Refactor TaskButler (LiveKit-based voice agent) to fix three core problems:
1. **LLM bottleneck** — every voice command (even trivial ones) goes through a 70B model.
2. **Browser automation fails on Windows** — Playwright + sync wrapper conflicts with ProactorEventLoop.
3. **Single-brain architecture** — the LLM does intent classification, tool selection, and summarization all at once.

Solution: split-brain architecture with regex-based **Intent Router** and direct **Browser Dispatcher** for fast paths, fast 8B Groq model for complex tasks.

## User Personas

- **Power user** wanting hands-free control over web apps (YouTube, Spotify, Gmail, Maps, Flights, etc.) by voice.
- **Developer** running TaskButler locally on Windows + VS Code without depending on Emergent or any managed cloud sandbox.

## Core Requirements (static)

- Sub-second response for browser commands (open / play / pause / scroll / search).
- Fast LLM (Groq 8B) for the 8 core agent tools: send_email, search_restaurants, order_ride, book_flight, add_calendar_event, set_alarm, manage_todo, get_weather.
- Real-time transcript and tool-card streaming over LiveKit data channel.
- Typed-chat input voiced back through the agent (text → /speak → TTS).
- Session summary surfaces on voice disconnect when conversation ≥ 2 messages.
- Runs entirely on a developer's Windows laptop with no Emergent infrastructure.

## Architecture

```
Mic → Deepgram STT (~200 ms)
        │
        ▼
   Intent Router (regex, <1 ms)
   ├── BROWSER → Browser Dispatcher → Playwright (dedicated thread loop) → Cartesia TTS
   └── AGENT   → LangGraph 8B Groq → Tool → Cartesia TTS

Frontend (Next.js + LiveKit-client) ── /token, /speak, data channel ── Backend (FastAPI + livekit-agents)
```

## What's Been Implemented

### Phase 1 (initial setup)
- Cloned `sumit-chillal/voice-agent` into `/app`.
- Added `nest_asyncio`, `aiofiles`.
- Set Windows ProactorEventLoop policy at top of `src/main.py`.
- Replaced `_run_async` with dedicated thread-loop implementation in `src/browser/engine.py`.
- Rewrote `BrowserEngine.start()` to use `chromium.launch + new_context` with display/headless detection.
- Created `src/agent/intent_router.py` (regex classifier, <1 ms).
- Created `src/agent/browser_dispatcher.py` (direct Playwright dispatch, no LLM).

### Phase 2 (split-brain wiring)
- Removed `ALL_BROWSER_TOOLS` from LangGraph; only 8 core tools registered.
- Default model → `llama3-groq-8b-8192-tool-use-preview`; `max_tokens=512`; temperature 0.2.
- Added intent routing at top of `LangGraphLLMStream._run()` — browser intents bypass LLM entirely.
- Updated `src/agent/prompts.py` — removed all 7 browser tool descriptions; added "never describe what you're about to call" rule.
- Updated `src/agent/tools.py` to share the engine's thread-loop `_run_async`.
- Updated `src/main.py` bootstrap to start browser engine in a daemon thread (non-blocking).
- Added `backend/.env` (real keys) + `backend/.env.example` (template) with `GROQ_MAX_TOKENS=512`.

### Phase 3 (frontend wiring + /speak)
- Tightened transcript sanitization in `lib/useTaskButler.ts` (function/tool tags only).
- Added `/speak` POST endpoint in `src/api.py` using `livekit_api.LiveKitAPI.room.send_data`.
- Added `data_received` handler in pipeline.py that listens for `speak_request` and calls `session.say(text)`.
- Frontend `sendTextMessage` now POSTs to `/speak` after `/chat` reply (best-effort, non-blocking).
- Added `showSummary`/`setShowSummary`/`sessionSummaryText` to the `useTaskButler` hook with auto-trigger on voice disconnect with ≥2 messages.
- Added overlay rendering of `ConversationSummary` in `app/page.tsx`.
- Tightened intent router patterns: "pause the song", "go back" now classified correctly (13/13).

### Phase 4 (Emergent independence + Windows setup guide)
- Confirmed zero Emergent-specific imports / URLs / SDKs anywhere in source.
- Confirmed no API keys hardcoded in source.
- Confirmed `.env*` files gitignored at root.
- Added `backend/browser_data/`, `backend/chroma_data/`, runtime logs to root `.gitignore`.
- Created `frontend/.env.local.example` (matching `setup` guide).
- Wrote `/app/LOCAL_SETUP.md` with 11 sections covering account setup, software, clone, backend setup, frontend setup, VS Code config, run/verify/stop, error catalogue, env reference, architecture explainer.

## Validation Summary (all phases)

- Backend compile across all `src/**/*.py`: PASS
- Imports (8 modules): 8/8 PASS
- Intent router accuracy: 13/13 PASS, plus Phase 1 regression 8/8 PASS
- Core tools registered: 8/8 PASS
- API routes present: `/health`, `/token`, `/speak` — 3/3 PASS
- Frontend `npm run build`: exit 0
- Frontend structural checks (DataReceived, handlers, /speak, showSummary, sessionRef, etc.): 9/9 PASS
- No Emergent refs in src: PASS
- Windows ProactorEventLoop policy in main.py: PASS
- Fast model default + max_tokens: PASS
- LOCAL_SETUP.md 11 sections: PASS
- `.env` gitignored: PASS

## Known Gaps / Backlog

- **P1**: Backend `api.py` does not implement `/chat`, `/auth/login`, `/status`, `/summarise`, `/conversation/history`, `/conversation/save`, `/set-voice` — frontend calls them with graceful catch-blocks. Typed chat through `/api/chat` will fail until these are added.
- **P2**: `manage_todo`'s ChromaDB-backed `mem.store_todo` / `mark_todo_done` / `delete_todo` may not exist yet on the memory module — fallback to JSON `TodoStore` is wired and works.
- **P2**: Persistent browser context (cookies across restarts) was traded for ephemeral `chromium.launch` per Phase 1 spec — re-introduce with `launch_persistent_context` if cookie persistence is required again.
- **P3**: The LiveKit `/token` endpoint currently returns the URL via env; could be moved to room-aware metadata for multi-tenant deploys.

## Next Tasks

- (P1) Add stub `/chat`, `/auth/login`, `/status`, `/summarise`, `/conversation/*`, `/set-voice` endpoints in `api.py` to make typed-chat functional.
- (P1) Wire `/chat` to dispatch through the same Intent Router so typed browser commands also bypass the LLM.
- (P2) Add concurrency cap / queue to the dedicated browser loop for safety under bursty input.
- (P3) Add Pytest suite running the intent router + dispatcher in CI.

## Last Updated

2026-01 — Phase 4 final validation complete.
