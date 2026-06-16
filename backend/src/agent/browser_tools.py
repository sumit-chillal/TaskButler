"""TaskButler - Browser Automation Tools (LangChain)

These tools wrap the singleton ``BrowserEngine`` so the LangGraph ReAct
agent can drive a real Chromium browser via voice or text commands.

The return-format mirrors the existing tool pattern in
``src/agents/tools.py`` exactly so the frontend ``ToolCard`` renderer keeps
working without changes:

    {
        "tool":      <tool-name>,
        "status":    "success" | "error",
        "icon":      <lucide icon name>,
        "title":     <short human-readable line>,
        "details":   {...},
        "timestamp": <ISO-8601 string>,
    }
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from ..browser.engine import get_browser_engine

logger = logging.getLogger(__name__)


# -------------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------------
def _now_iso() -> str:
    return datetime.now().isoformat()


def _success_card(
    *, tool_name: str, icon: str, title: str, details: dict
) -> dict:
    return {
        "tool": tool_name,
        "status": "success",
        "icon": icon,
        "title": title,
        "details": details,
        "timestamp": _now_iso(),
    }


def _error_card(tool_name: str, error: Exception | str) -> dict:
    err = error if isinstance(error, str) else str(error)
    logger.error("Browser tool '%s' failed: %s", tool_name, err)
    return {
        "tool": tool_name,
        "status": "error",
        "icon": "alert-circle",
        "title": "Browser action failed",
        "details": {"error": err},
        "timestamp": _now_iso(),
    }


def _run_async(coro):
    """Run an async coroutine from a sync LangChain tool body.

    LangChain tools may be invoked from either a synchronous or an asyncio
    context. ``asyncio.run`` raises if a loop is already running, so we
    detect that case and run in a fresh thread.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is None or not loop.is_running():
        return asyncio.run(coro)

    # Running inside an event loop -> run on a separate thread
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        future = ex.submit(asyncio.run, coro)
        return future.result()


# -------------------------------------------------------------------------
# Tool: open_website
# -------------------------------------------------------------------------
class OpenWebsiteInput(BaseModel):
    site_name: str = Field(..., description="The site name or URL the user mentioned")


@tool(args_schema=OpenWebsiteInput)
def open_website(site_name: str) -> dict:
    """Opens any website or web application in the browser. Use when the user says open, go to, visit, launch, or navigate to any website or app name."""
    try:
        async def _run():
            engine = await get_browser_engine()
            return await engine.open_named_site(site_name)

        result = _run_async(_run())
        if not result.get("success"):
            return _error_card("open_website", result.get("error", "unknown error"))

        return _success_card(
            tool_name="open_website",
            icon="globe",
            title=f"Opened {site_name}",
            details={
                "site": site_name,
                "url": result.get("url", ""),
                "page_title": result.get("title", ""),
            },
        )
    except Exception as e:
        return _error_card("open_website", e)


# -------------------------------------------------------------------------
# Tool: search_web_or_app
# -------------------------------------------------------------------------
class SearchWebOrAppInput(BaseModel):
    query: str = Field(..., description="What to search for")
    site_context: str = Field(
        default="",
        description="Optional site to search on (e.g. youtube, spotify, google)",
    )


@tool(args_schema=SearchWebOrAppInput)
def search_web_or_app(query: str, site_context: str = "") -> dict:
    """Searches for something on the current website or in a new browser tab. Use when the user says search for, find, look up, play (for music/video), or show me something specific."""
    try:
        async def _run():
            engine = await get_browser_engine()
            ctx_lower = (site_context or "").lower().strip()
            if ctx_lower:
                page_ctx = await engine.get_page_context()
                current = (page_ctx.get("url") or "").lower() if page_ctx.get("success") else ""
                if ctx_lower not in current:
                    open_res = await engine.open_named_site(ctx_lower)
                    if not open_res.get("success"):
                        return open_res
            return await engine.search_on_page(query, site_context=site_context or "")

        result = _run_async(_run())
        if not result.get("success"):
            return _error_card("search_web_or_app", result.get("error", "search failed"))

        target = site_context or "current page"
        return _success_card(
            tool_name="search_web_or_app",
            icon="search",
            title=f"Searched '{query}' on {target}",
            details={
                "query": query,
                "site_context": result.get("site_context", target),
                "url": result.get("url", ""),
                "page_title": result.get("title", ""),
            },
        )
    except Exception as e:
        return _error_card("search_web_or_app", e)


# -------------------------------------------------------------------------
# Tool: control_media_playback
# -------------------------------------------------------------------------
class ControlMediaInput(BaseModel):
    action: str = Field(
        ...,
        description=(
            "One of: play, pause, next, previous, mute, unmute, volume_up, volume_down"
        ),
    )


@tool(args_schema=ControlMediaInput)
def control_media_playback(action: str) -> dict:
    """Controls media playback in the browser - play, pause, skip, mute, adjust volume. Use when the user says pause, play, stop, next song, previous, mute, unmute."""
    try:
        async def _run():
            engine = await get_browser_engine()
            return await engine.media_control(action)

        result = _run_async(_run())
        if not result.get("success"):
            return _error_card(
                "control_media_playback", result.get("error", "media control failed")
            )

        return _success_card(
            tool_name="control_media_playback",
            icon="play-circle",
            title=f"Media: {result.get('media_action', action)}",
            details={
                "action": result.get("media_action", action),
                "method": result.get("method", "unknown"),
                "key": result.get("key"),
            },
        )
    except Exception as e:
        return _error_card("control_media_playback", e)


# -------------------------------------------------------------------------
# Tool: click_on_page
# -------------------------------------------------------------------------
class ClickOnPageInput(BaseModel):
    target: str = Field(
        ..., description="What to click, described in natural language or as a CSS selector"
    )


@tool(args_schema=ClickOnPageInput)
def click_on_page(target: str) -> dict:
    """Clicks a specific element, button, or link on the current web page. Use when the user says click on, press, select, or tap something specific on screen."""
    try:
        async def _run():
            engine = await get_browser_engine()
            return await engine.click_element(selector=target, description=target)

        result = _run_async(_run())
        if not result.get("success"):
            return _error_card("click_on_page", result.get("error", "click failed"))

        return _success_card(
            tool_name="click_on_page",
            icon="mouse-pointer-click",
            title=f"Clicked '{target}'",
            details={
                "target": target,
                "method": result.get("method", "unknown"),
                "selector": result.get("selector", target),
            },
        )
    except Exception as e:
        return _error_card("click_on_page", e)


# -------------------------------------------------------------------------
# Tool: type_on_page
# -------------------------------------------------------------------------
class TypeOnPageInput(BaseModel):
    text: str = Field(..., description="The text to type")
    field_description: str = Field(
        default="",
        description=(
            "Optional CSS selector or natural-language description of which field to type into"
        ),
    )


@tool(args_schema=TypeOnPageInput)
def type_on_page(text: str, field_description: str = "") -> dict:
    """Types text into a form field, search box, or text area on the current page. Use for filling in forms, composing text, or entering data."""
    try:
        async def _run():
            engine = await get_browser_engine()
            sel: Optional[str] = field_description.strip() or None
            # If field_description doesn't look like a CSS selector but a label,
            # prefer fill_form_field which handles labels/placeholders.
            if sel and not any(c in sel for c in ("#", ".", "[", ">", "input", "textarea")):
                form_res = await engine.fill_form_field(field_label=sel, value=text)
                if form_res.get("success"):
                    return form_res
            return await engine.type_text(text, selector=sel)

        result = _run_async(_run())
        if not result.get("success"):
            return _error_card("type_on_page", result.get("error", "typing failed"))

        return _success_card(
            tool_name="type_on_page",
            icon="keyboard",
            title=f"Typed into {result.get('field', field_description or 'page')}",
            details={
                "text": text,
                "field": result.get("field", field_description or "focused element"),
                "method": result.get("method"),
            },
        )
    except Exception as e:
        return _error_card("type_on_page", e)


# -------------------------------------------------------------------------
# Tool: navigate_browser
# -------------------------------------------------------------------------
class NavigateBrowserInput(BaseModel):
    action: str = Field(
        ...,
        description="One of: back, scroll_up, scroll_down, refresh",
    )


@tool(args_schema=NavigateBrowserInput)
def navigate_browser(action: str) -> dict:
    """Controls browser navigation - go back, scroll up, scroll down, refresh page. Use when the user says go back, scroll down, scroll up, or refresh."""
    try:
        act = (action or "").strip().lower().replace("-", "_")

        async def _run():
            engine = await get_browser_engine()
            if act == "back":
                return await engine.go_back()
            if act == "scroll_up":
                return await engine.scroll(direction="up", amount=2)
            if act == "scroll_down":
                return await engine.scroll(direction="down", amount=2)
            if act == "refresh":
                page = await engine._ensure_page()
                try:
                    await page.reload(wait_until="domcontentloaded", timeout=15000)
                    return {
                        "success": True,
                        "action": "refresh",
                        "url": page.url,
                        "title": await page.title(),
                    }
                except Exception as e:
                    return {"success": False, "action": "refresh", "error": str(e)}
            return {
                "success": False,
                "action": "navigate_browser",
                "error": f"unsupported navigation action '{action}'",
            }

        result = _run_async(_run())
        if not result.get("success"):
            return _error_card(
                "navigate_browser", result.get("error", "navigation failed")
            )

        return _success_card(
            tool_name="navigate_browser",
            icon="navigation",
            title=f"Navigation: {act}",
            details={
                "action": act,
                "url": result.get("url"),
                "page_title": result.get("title"),
                "direction": result.get("direction"),
                "amount": result.get("amount"),
            },
        )
    except Exception as e:
        return _error_card("navigate_browser", e)


# -------------------------------------------------------------------------
# Tool: read_current_page
# -------------------------------------------------------------------------
class ReadCurrentPageInput(BaseModel):
    pass


@tool(args_schema=ReadCurrentPageInput)
def read_current_page() -> dict:
    """Reads and summarizes what is currently visible on the browser page. Use when the user asks what's on the screen, what does it say, or what are the results."""
    try:
        async def _run():
            engine = await get_browser_engine()
            ctx = await engine.get_page_context()
            text = await engine.get_visible_text(max_chars=2000)
            return ctx, text

        ctx, text = _run_async(_run())
        if not text.get("success"):
            return _error_card("read_current_page", text.get("error", "unable to read page"))

        excerpt = text.get("text", "")
        return _success_card(
            tool_name="read_current_page",
            icon="file-text",
            title=f"Read page: {text.get('title') or 'Untitled'}",
            details={
                "url": text.get("url", ""),
                "page_title": text.get("title", ""),
                "page_type": ctx.get("page_type") if ctx.get("success") else "web page",
                "excerpt": excerpt,
                "truncated": text.get("truncated", False),
                "char_count": text.get("char_count", 0),
                "summary_instruction": (
                    "Summarise the excerpt in 2-3 short, conversational sentences."
                ),
            },
        )
    except Exception as e:
        return _error_card("read_current_page", e)


# -------------------------------------------------------------------------
# Aggregate
# -------------------------------------------------------------------------
ALL_BROWSER_TOOLS = [
    open_website,
    search_web_or_app,
    control_media_playback,
    click_on_page,
    type_on_page,
    navigate_browser,
    read_current_page,
]
