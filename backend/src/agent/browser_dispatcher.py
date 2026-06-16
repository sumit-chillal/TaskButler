"""
Browser Dispatcher — executes browser commands directly.
Takes an Intent from the router and executes it immediately.
No LLM. No LangGraph. Direct Playwright calls.
"""
from datetime import datetime
import traceback

from src.agent.intent_router import Intent, KNOWN_SITES


# ---------------------------------------------------------------------------
# Spoken-confirmation messages keyed by action.
# ---------------------------------------------------------------------------
_MEDIA_CONTROL_MESSAGES = {
    "pause": "Paused.", "play": "Playing.", "next": "Next track.",
    "previous": "Previous track.", "mute": "Muted.", "unmute": "Unmuted.",
    "volume_up": "Volume up.", "volume_down": "Volume down.",
}


def _find_url(site_name: str) -> str:
    name = site_name.lower().strip()
    if name in KNOWN_SITES:
        return KNOWN_SITES[name]
    for key, url in KNOWN_SITES.items():
        if key in name or name in key:
            return url
    if "." in name:
        return f"https://{name}" if not name.startswith("http") else name
    return f"https://www.google.com/search?q={name.replace(' ', '+')}"


def _spoken_confirmation(action: str, params: dict) -> str:
    """Generate a natural spoken confirmation for a browser action."""
    if action == "open_site":
        return f"Opening {params.get('site', 'that page')} now."
    if action == "play":
        return f"Playing {params.get('query', 'that')} now."
    if action == "play_on_platform":
        return f"Playing {params.get('query', 'that')} on {params.get('site', 'there')}."
    if action == "search":
        return f"Searching for {params.get('query', 'that')}."
    if action == "search_on_site":
        return f"Searching {params.get('query', 'that')} on {params.get('site', 'there')}."
    if action == "media_control":
        a = params.get("action", "")
        return _MEDIA_CONTROL_MESSAGES.get(a, f"Done — {a}.")
    if action == "scroll":
        return f"Scrolling {params.get('direction', 'down')}."
    if action == "go_back":
        return "Going back."
    if action == "click":
        return f"Clicking {params.get('target', 'that')}."
    if action == "type_text":
        return "Typing that now."
    return "Done."


# ---------------------------------------------------------------------------
# Per-action runners. Each takes (engine, run_async, params) and returns the
# Playwright engine result dict (or None for actions with no result).
# ---------------------------------------------------------------------------
def _run_open_site(engine, run, params):
    return run(engine.open_named_site(params.get("site", "")))


def _run_play(engine, run, params):
    query = params.get("query", "")
    ctx = run(engine.get_page_context())
    current_url = (ctx or {}).get("url", "")
    if "youtube" in current_url:
        return run(engine.search_on_page(query, "youtube"))
    if "spotify" in current_url:
        return run(engine.search_on_page(query, "spotify"))
    run(engine.open_named_site("youtube"))
    return run(engine.search_on_page(query, "youtube"))


def _run_play_on_platform(engine, run, params):
    query = params.get("query", "")
    site = params.get("site", "youtube")
    run(engine.open_named_site(site))
    return run(engine.search_on_page(query, site))


def _run_search(engine, run, params):
    return run(engine.search_on_page(params.get("query", "")))


def _run_search_on_site(engine, run, params):
    site = params.get("site", "")
    query = params.get("query", "")
    run(engine.open_named_site(site))
    return run(engine.search_on_page(query, site))


def _run_media_control(engine, run, params):
    return run(engine.media_control(params.get("action", "play")))


def _run_scroll(engine, run, params):
    return run(engine.scroll(params.get("direction", "down")))


def _run_go_back(engine, run, _params):
    return run(engine.go_back())


def _run_click(engine, run, params):
    target = params.get("target", "")
    return run(engine.click_element(target, target))


def _run_type_text(engine, run, params):
    return run(engine.type_text(params.get("text", "")))


_ACTION_HANDLERS = {
    "open_site": _run_open_site,
    "play": _run_play,
    "play_on_platform": _run_play_on_platform,
    "search": _run_search,
    "search_on_site": _run_search_on_site,
    "media_control": _run_media_control,
    "scroll": _run_scroll,
    "go_back": _run_go_back,
    "click": _run_click,
    "type_text": _run_type_text,
}


def _build_tool_card(action: str, params: dict, result: dict, spoken: str) -> dict:
    return {
        "tool": f"browser_{action}",
        "status": "success" if (result or {}).get("success", True) else "error",
        "icon": "globe",
        "title": spoken.rstrip("."),
        "details": {**params, **(result or {})},
        "timestamp": datetime.now().isoformat(),
    }


def execute(intent: Intent) -> dict:
    """
    Execute a browser intent synchronously.
    Returns: {success, spoken_text, tool_card}
    """
    from src.browser.engine import _run_async, get_browser_engine

    action = intent.action
    params = intent.params
    spoken = _spoken_confirmation(action, params)

    handler = _ACTION_HANDLERS.get(action)
    if handler is None:
        return {
            "success": False,
            "spoken_text": "I'm not sure how to do that yet.",
            "tool_card": None,
            "error": f"unknown browser action: {action}",
        }

    try:
        engine = _run_async(get_browser_engine())
        result = handler(engine, _run_async, params)

        if result and not result.get("success", True):
            spoken = f"Sorry, I couldn't do that. {result.get('error', '')}"

        return {
            "success": True,
            "spoken_text": spoken,
            "tool_card": _build_tool_card(action, params, result or {}, spoken),
        }
    except Exception as e:
        traceback.print_exc()
        return {
            "success": False,
            "spoken_text": "I couldn't do that right now.",
            "tool_card": None,
            "error": str(e),
        }
