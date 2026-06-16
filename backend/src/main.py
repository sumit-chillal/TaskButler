"""TaskButler - Entry Point

Starts the LiveKit worker and ensures the singleton ``BrowserEngine``
is initialised so the browser-automation tools can drive a real browser
during a session.

This module can be invoked as:
    python -m src.main start      # starts the LiveKit agent worker
    python -m src.main dev        # same (alias)
"""

import sys
import asyncio

# Windows requires ProactorEventLoop for subprocess and Playwright compatibility
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import atexit
import logging
import os
import threading
from dotenv import load_dotenv
load_dotenv()

from livekit.agents import WorkerOptions, cli
from src.livekit.pipeline import TaskButlerAgent
from src.browser.engine import get_browser_engine, _run_async

logger = logging.getLogger(__name__)


def _bootstrap_browser_in_background() -> None:
    """
    Pre-warm the browser engine on the dedicated browser loop so the first
    voice command is instant. Runs in a daemon thread so it does not block
    the LiveKit CLI startup.
    """
    def _start():
        try:
            _run_async(get_browser_engine())
            logger.info("BrowserEngine ready (singleton initialised)")
        except Exception as e:
            logger.warning("BrowserEngine could not start at boot: %s", e)

    t = threading.Thread(target=_start, daemon=True, name="browser-bootstrap")
    t.start()


def _shutdown_browser_sync() -> None:
    """atexit hook: close the browser context cleanly on process exit."""
    try:
        from src.browser import engine as engine_mod
        be = engine_mod._browser_engine
        if be is None or not be._started:
            return
        try:
            _run_async(be.stop())
        except Exception as e:
            logger.warning("Browser shutdown hook failed: %s", e)
    except Exception:
        pass


def main():
    """Entry point: starts LiveKit worker and the browser engine."""
    # Pre-warm the browser engine on the dedicated browser loop in the background.
    _bootstrap_browser_in_background()

    atexit.register(_shutdown_browser_sync)

    agent = TaskButlerAgent()
    # Pick the agent's HTTP health-check port from env so it does not collide
    # with the FastAPI server on 8001 or any other supervisor program. Use
    # port 0 by default to let the OS auto-assign a free port.
    agent_port = int(os.getenv("LIVEKIT_AGENT_PORT", "0"))
    try:
        cli.run_app(
            WorkerOptions(
                entrypoint_fnc=agent.entrypoint,
                ws_url=os.getenv("LIVEKIT_URL"),
                api_key=os.getenv("LIVEKIT_API_KEY"),
                api_secret=os.getenv("LIVEKIT_API_SECRET"),
                port=agent_port,
            )
        )
    finally:
        _shutdown_browser_sync()


if __name__ == "__main__":
    main()
