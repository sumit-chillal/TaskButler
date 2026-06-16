"""TaskButler - Browser Automation Engine

A singleton, async Playwright-based browser controller. Designed to be
launched once when the LiveKit worker starts and reused by all browser
tools defined in ``src/agent/browser_tools.py``.

All public methods are async, return structured dicts of the shape:
    {"success": bool, "action": <method-name>, ...result_fields}
On error every method returns:
    {"success": False, "action": <method-name>, "error": <str>}

The engine launches a *persistent* Chromium context (so cookies / sessions
survive process restarts). The user-data directory is read from the
``BROWSER_DATA_DIR`` environment variable.

Headless mode is controlled by ``BROWSER_HEADLESS`` (default ``false``);
in container environments without a display server this should be set
to ``true``.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import threading
from pathlib import Path
from typing import Optional

import nest_asyncio

# Apply nest_asyncio only when the running loop is a stdlib asyncio loop.
# uvicorn defaults to uvloop, which nest_asyncio can't patch — and we don't
# need it there because _run_async dispatches to a *separate* thread loop.
try:
    nest_asyncio.apply()
except (ValueError, RuntimeError) as _na_err:  # uvloop or no running loop
    logging.getLogger(__name__).debug(
        "nest_asyncio.apply skipped: %s", _na_err
    )

logger = logging.getLogger(__name__)


def _project_root() -> Path:
    # backend/src/browser/engine.py -> project root is 3 parents up
    return Path(__file__).resolve().parents[3]


# -------------------------------------------------------------------------
# Dedicated event loop for browser operations running in its own thread.
# This makes _run_async safe to call from any sync context on Windows,
# Mac, and Linux regardless of whether an outer event loop is running.
# -------------------------------------------------------------------------
_browser_loop: Optional[asyncio.AbstractEventLoop] = None
_browser_thread: Optional[threading.Thread] = None
_browser_loop_lock = threading.Lock()


def _get_browser_loop() -> asyncio.AbstractEventLoop:
    global _browser_loop, _browser_thread
    with _browser_loop_lock:
        if _browser_loop is None or not _browser_loop.is_running():
            _browser_loop = asyncio.new_event_loop()
            _browser_thread = threading.Thread(
                target=_browser_loop.run_forever,
                daemon=True,
                name="browser-event-loop",
            )
            _browser_thread.start()
        return _browser_loop


def _run_async(coro):
    """
    Run an async coroutine from a synchronous context.
    Works on Windows, Mac, and Linux regardless of the current event loop state.
    """
    try:
        loop = _get_browser_loop()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=30)
    except TimeoutError:
        return {"success": False, "error": "Browser operation timed out after 30s", "action": "timeout"}
    except Exception as e:
        return {"success": False, "error": str(e), "action": "unknown"}


class BrowserEngine:
    """Async singleton wrapper around a persistent Playwright Chromium context."""

    # Class-level mapping of spoken / casual site names -> URLs.
    # Mutable on purpose: the LLM (or any caller) can extend it at runtime via
    # ``BrowserEngine.SITE_MAP[name] = url``.
    SITE_MAP: dict = {
        "youtube": "https://www.youtube.com",
        "youtube music": "https://music.youtube.com",
        "spotify": "https://open.spotify.com",
        "gmail": "https://mail.google.com",
        "google": "https://www.google.com",
        "google maps": "https://www.google.com/maps",
        "maps": "https://www.google.com/maps",
        "google calendar": "https://calendar.google.com",
        "calendar": "https://calendar.google.com",
        "google drive": "https://drive.google.com",
        "drive": "https://drive.google.com",
        "google docs": "https://docs.google.com",
        "docs": "https://docs.google.com",
        "twitter": "https://twitter.com",
        "x": "https://x.com",
        "linkedin": "https://www.linkedin.com",
        "github": "https://github.com",
        "reddit": "https://www.reddit.com",
        "instagram": "https://www.instagram.com",
        "facebook": "https://www.facebook.com",
        "whatsapp": "https://web.whatsapp.com",
        "amazon": "https://www.amazon.in",
        "flipkart": "https://www.flipkart.com",
        "netflix": "https://www.netflix.com",
        "wikipedia": "https://www.wikipedia.org",
        "chatgpt": "https://chat.openai.com",
        "claude": "https://claude.ai",
        "perplexity": "https://www.perplexity.ai",
    }

    def __init__(self) -> None:
        self._playwright = None
        self._browser = None  # Browser instance (when using launch)
        self._context = None  # BrowserContext
        self._page = None     # Active Page
        self._started: bool = False
        self._lock = asyncio.Lock()

    # ---------------------------------------------------------------------
    # Lifecycle
    # ---------------------------------------------------------------------
    async def start(self):
        if self._started:
            return
        # Lazy import so the module can be imported in environments
        # where playwright isn't available yet (validation step).
        from playwright.async_api import async_playwright

        # Determine headless mode
        headless_env = os.getenv("BROWSER_HEADLESS", "true").lower()
        has_display = bool(os.getenv("DISPLAY")) or sys.platform == "win32"
        headless = not (headless_env == "false" and has_display)

        data_dir = os.getenv("BROWSER_DATA_DIR", "./browser_data")
        os.makedirs(data_dir, exist_ok=True)

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=headless,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-web-security"]
            if headless else ["--start-maximized"]
        )
        self._context = await self._browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        self._page = await self._context.new_page()
        self._started = True
        logger.info(
            "BrowserEngine started (data_dir=%s headless=%s)",
            data_dir, headless,
        )

    async def stop(self) -> dict:
        """Close the browser context and stop Playwright."""
        try:
            await self._safe_cleanup()
            return {"success": True, "action": "stop"}
        except Exception as e:
            logger.error("BrowserEngine.stop failed: %s", e, exc_info=True)
            return {"success": False, "action": "stop", "error": str(e)}

    async def _safe_cleanup(self) -> None:
        try:
            if self._context is not None:
                await self._context.close()
        except Exception:
            pass
        try:
            if self._browser is not None:
                await self._browser.close()
        except Exception:
            pass
        try:
            if self._playwright is not None:
                await self._playwright.stop()
        except Exception:
            pass
        self._context = None
        self._browser = None
        self._playwright = None
        self._page = None
        self._started = False

    # ---------------------------------------------------------------------
    # Internal helpers
    # ---------------------------------------------------------------------
    async def _ensure_page(self):
        if not self._started:
            await self.start()
        if self._page is None or self._page.is_closed():
            self._page = await self._context.new_page()
        return self._page

    @staticmethod
    def _normalize_url(url_or_name: str) -> str:
        u = (url_or_name or "").strip()
        if not u:
            return u
        if u.startswith("http://") or u.startswith("https://"):
            return u
        # Looks like a domain ("example.com")
        if "." in u and " " not in u:
            return "https://" + u
        return u  # bare name; caller will resolve via SITE_MAP

    @staticmethod
    def _classify_page(url: str, title: str) -> str:
        u = (url or "").lower()
        t = (title or "").lower()
        if "youtube.com/watch" in u or "youtu.be/" in u:
            return "video player"
        if "spotify.com" in u and ("/track/" in u or "/album/" in u or "/playlist/" in u):
            return "music player"
        if "/search" in u or "search?" in u or "results" in t or "search" in t:
            return "search results"
        if "mail.google.com" in u:
            return "email" if "compose" not in u else "email composer"
        if "maps.google" in u or "google.com/maps" in u:
            return "map"
        if "docs.google.com" in u or "drive.google.com" in u:
            return "document"
        return "web page"

    # ---------------------------------------------------------------------
    # Navigation
    # ---------------------------------------------------------------------
    async def open_url(self, url: str) -> dict:
        try:
            page = await self._ensure_page()
            target = self._normalize_url(url)
            if not target:
                return {"success": False, "action": "open_url", "error": "empty url"}
            await page.goto(target, wait_until="domcontentloaded", timeout=30000)
            try:
                await page.wait_for_load_state("load", timeout=10000)
            except Exception:
                # Some pages never reach 'load'; domcontentloaded is enough.
                pass
            title = await page.title()
            return {
                "success": True,
                "action": "open_url",
                "url": page.url,
                "title": title,
            }
        except Exception as e:
            logger.error("open_url failed: %s", e)
            return {"success": False, "action": "open_url", "error": str(e)}

    async def open_named_site(self, site_name: str) -> dict:
        try:
            name = (site_name or "").strip().lower()
            if not name:
                return {
                    "success": False,
                    "action": "open_named_site",
                    "error": "empty site name",
                }

            url = self.SITE_MAP.get(name)
            if url is None:
                # Allow callers to pass a raw URL or domain
                normalized = self._normalize_url(site_name)
                if normalized.startswith("http"):
                    url = normalized
                else:
                    # Last-ditch fallback: search Google for the site
                    url = f"https://www.google.com/search?q={name.replace(' ', '+')}"

            result = await self.open_url(url)
            result["action"] = "open_named_site"
            result["site_name"] = name
            return result
        except Exception as e:
            logger.error("open_named_site failed: %s", e)
            return {"success": False, "action": "open_named_site", "error": str(e)}

    async def go_back(self) -> dict:
        try:
            page = await self._ensure_page()
            await page.go_back(wait_until="domcontentloaded", timeout=15000)
            return {
                "success": True,
                "action": "go_back",
                "url": page.url,
                "title": await page.title(),
            }
        except Exception as e:
            return {"success": False, "action": "go_back", "error": str(e)}

    async def scroll(self, direction: str, amount: int = 3) -> dict:
        try:
            page = await self._ensure_page()
            d = (direction or "down").lower()
            sign = -1 if d in ("up", "top") else 1
            # Scroll by `amount` viewport heights
            await page.evaluate(
                "([s, a]) => window.scrollBy(0, s * a * window.innerHeight)",
                [sign, amount],
            )
            return {
                "success": True,
                "action": "scroll",
                "direction": "up" if sign < 0 else "down",
                "amount": amount,
            }
        except Exception as e:
            return {"success": False, "action": "scroll", "error": str(e)}

    # ---------------------------------------------------------------------
    # Element interaction
    # ---------------------------------------------------------------------
    async def click_element(self, selector: str, description: str) -> dict:
        try:
            page = await self._ensure_page()
            target = (selector or description or "").strip()
            if not target:
                return {
                    "success": False,
                    "action": "click_element",
                    "error": "no selector or description",
                }

            # 1) Try as a CSS selector first
            try:
                locator = page.locator(target).first
                await locator.wait_for(state="visible", timeout=3000)
                await locator.click(timeout=3000)
                return {
                    "success": True,
                    "action": "click_element",
                    "method": "css",
                    "selector": target,
                    "description": description,
                }
            except Exception:
                pass

            # 2) Fall back to visible text (Playwright's text= engine)
            text_target = description or selector
            try:
                locator = page.get_by_text(text_target, exact=False).first
                await locator.wait_for(state="visible", timeout=3000)
                await locator.click(timeout=3000)
                return {
                    "success": True,
                    "action": "click_element",
                    "method": "text",
                    "selector": text_target,
                    "description": description,
                }
            except Exception:
                pass

            # 3) Try common roles (button / link)
            for role in ("button", "link"):
                try:
                    locator = page.get_by_role(role, name=text_target).first
                    await locator.wait_for(state="visible", timeout=2000)
                    await locator.click(timeout=2000)
                    return {
                        "success": True,
                        "action": "click_element",
                        "method": f"role:{role}",
                        "selector": text_target,
                        "description": description,
                    }
                except Exception:
                    continue

            return {
                "success": False,
                "action": "click_element",
                "error": f"could not find element matching '{target}'",
                "description": description,
            }
        except Exception as e:
            return {"success": False, "action": "click_element", "error": str(e)}

    async def type_text(self, text: str, selector: Optional[str] = None) -> dict:
        try:
            page = await self._ensure_page()
            if selector:
                locator = page.locator(selector).first
                await locator.wait_for(state="visible", timeout=5000)
                await locator.fill(text)
                field = selector
            else:
                # Type into whatever is currently focused
                await page.keyboard.type(text)
                field = "focused element"
            return {
                "success": True,
                "action": "type_text",
                "text": text,
                "field": field,
            }
        except Exception as e:
            return {"success": False, "action": "type_text", "error": str(e)}

    async def press_key(self, key: str) -> dict:
        try:
            page = await self._ensure_page()
            await page.keyboard.press(key)
            return {"success": True, "action": "press_key", "key": key}
        except Exception as e:
            return {"success": False, "action": "press_key", "error": str(e)}

    async def fill_form_field(self, field_label: str, value: str) -> dict:
        try:
            page = await self._ensure_page()
            label = (field_label or "").strip()
            if not label:
                return {
                    "success": False,
                    "action": "fill_form_field",
                    "error": "empty label",
                }

            # Strategy 1: by accessible label (covers <label>, aria-label, etc.)
            try:
                locator = page.get_by_label(label, exact=False).first
                await locator.wait_for(state="visible", timeout=3000)
                await locator.fill(value)
                return {
                    "success": True,
                    "action": "fill_form_field",
                    "method": "label",
                    "field": label,
                    "value": value,
                }
            except Exception:
                pass

            # Strategy 2: by placeholder
            try:
                locator = page.get_by_placeholder(label, exact=False).first
                await locator.wait_for(state="visible", timeout=3000)
                await locator.fill(value)
                return {
                    "success": True,
                    "action": "fill_form_field",
                    "method": "placeholder",
                    "field": label,
                    "value": value,
                }
            except Exception:
                pass

            # Strategy 3: input/textarea by name / aria-label attribute
            try:
                escaped = label.replace('"', '\\"')
                sel = (
                    f'input[name="{escaped}" i], textarea[name="{escaped}" i], '
                    f'input[aria-label*="{escaped}" i], textarea[aria-label*="{escaped}" i]'
                )
                locator = page.locator(sel).first
                await locator.wait_for(state="visible", timeout=3000)
                await locator.fill(value)
                return {
                    "success": True,
                    "action": "fill_form_field",
                    "method": "attribute",
                    "field": label,
                    "value": value,
                }
            except Exception:
                pass

            return {
                "success": False,
                "action": "fill_form_field",
                "error": f"could not locate field '{label}'",
            }
        except Exception as e:
            return {"success": False, "action": "fill_form_field", "error": str(e)}

    # ---------------------------------------------------------------------
    # Search
    # ---------------------------------------------------------------------
    async def search_on_page(self, query: str, site_context: str = "") -> dict:
        try:
            page = await self._ensure_page()
            ctx = (site_context or "").lower()
            current_url = (page.url or "").lower()

            # Site-specific selector strategies
            site_selectors = {
                "youtube": 'input#search, input[name="search_query"]',
                "spotify": 'input[data-testid="search-input"], input[role="combobox"]',
                "google": 'input[name="q"], textarea[name="q"]',
                "amazon": 'input#twotabsearchtextbox, input[name="field-keywords"]',
                "github": 'input[name="q"], input[aria-label*="Search" i]',
                "wikipedia": 'input[name="search"]',
            }

            chosen_site = None
            for key in site_selectors:
                if key in ctx or key in current_url:
                    chosen_site = key
                    break

            selectors_to_try = []
            if chosen_site:
                selectors_to_try.append(site_selectors[chosen_site])
            # Generic fallbacks
            selectors_to_try.extend([
                'input[type="search"]',
                'input[name="q"]',
                'textarea[name="q"]',
                'input[role="combobox"]',
                'input[aria-label*="Search" i]',
                'input[placeholder*="Search" i]',
            ])

            last_err: Optional[str] = None
            for sel in selectors_to_try:
                try:
                    locator = page.locator(sel).first
                    await locator.wait_for(state="visible", timeout=2500)
                    await locator.click()
                    await locator.fill(query)
                    await page.keyboard.press("Enter")
                    try:
                        await page.wait_for_load_state(
                            "domcontentloaded", timeout=10000
                        )
                    except Exception:
                        pass
                    return {
                        "success": True,
                        "action": "search_on_page",
                        "query": query,
                        "site_context": chosen_site or site_context or "generic",
                        "selector": sel,
                        "url": page.url,
                        "title": await page.title(),
                    }
                except Exception as e:
                    last_err = str(e)
                    continue

            return {
                "success": False,
                "action": "search_on_page",
                "error": f"no search input found ({last_err})",
                "query": query,
            }
        except Exception as e:
            return {"success": False, "action": "search_on_page", "error": str(e)}

    # ---------------------------------------------------------------------
    # Media controls
    # ---------------------------------------------------------------------
    async def media_control(self, action: str) -> dict:
        try:
            page = await self._ensure_page()
            act = (action or "").strip().lower().replace("-", "_")
            url = (page.url or "").lower()

            # Site-specific keyboard shortcuts (best-effort first try)
            shortcut_map = {}
            if "youtube.com" in url:
                shortcut_map = {
                    "play": "k",
                    "pause": "k",
                    "next": "Shift+N",
                    "previous": "Shift+P",
                    "mute": "m",
                    "unmute": "m",
                    "volume_up": "ArrowUp",
                    "volume_down": "ArrowDown",
                }
            elif "spotify.com" in url:
                shortcut_map = {
                    "play": "Space",
                    "pause": "Space",
                    "next": "Control+Right",
                    "previous": "Control+Left",
                    "mute": "Control+Shift+M",
                    "unmute": "Control+Shift+M",
                    "volume_up": "Control+ArrowUp",
                    "volume_down": "Control+ArrowDown",
                }

            if act in shortcut_map:
                try:
                    # Some pages need focus on the body first
                    await page.evaluate("document.body && document.body.focus && document.body.focus()")
                    await page.keyboard.press(shortcut_map[act])
                    return {
                        "success": True,
                        "action": "media_control",
                        "media_action": act,
                        "method": "keyboard_shortcut",
                        "key": shortcut_map[act],
                    }
                except Exception:
                    pass  # fall through to JS

            # Generic HTML5 media element control via JS dispatch (no eval).
            if act in ("play", "pause", "mute", "unmute", "volume_up", "volume_down"):
                ok = await page.evaluate(
                    """(action) => {
                        const els = Array.from(document.querySelectorAll('video, audio'));
                        if (els.length === 0) return false;
                        const handlers = {
                            play:        (el) => el.play(),
                            pause:       (el) => el.pause(),
                            mute:        (el) => { el.muted = true; },
                            unmute:      (el) => { el.muted = false; },
                            volume_up:   (el) => { el.volume = Math.min(1, (el.volume || 0) + 0.1); },
                            volume_down: (el) => { el.volume = Math.max(0, (el.volume || 0) - 0.1); },
                        };
                        const fn = handlers[action];
                        if (!fn) return false;
                        els.forEach(fn);
                        return true;
                    }""",
                    act,
                )
                return {
                    "success": bool(ok),
                    "action": "media_control",
                    "media_action": act,
                    "method": "html5_media",
                    "error": None if ok else "no <video>/<audio> element found",
                }

            if act in ("next", "previous"):
                # Generic media key
                key = "MediaTrackNext" if act == "next" else "MediaTrackPrevious"
                try:
                    await page.keyboard.press(key)
                    return {
                        "success": True,
                        "action": "media_control",
                        "media_action": act,
                        "method": "media_key",
                        "key": key,
                    }
                except Exception as e:
                    return {
                        "success": False,
                        "action": "media_control",
                        "media_action": act,
                        "error": str(e),
                    }

            return {
                "success": False,
                "action": "media_control",
                "error": f"unsupported media action '{action}'",
            }
        except Exception as e:
            return {"success": False, "action": "media_control", "error": str(e)}

    # ---------------------------------------------------------------------
    # Page introspection
    # ---------------------------------------------------------------------
    async def get_page_context(self) -> dict:
        try:
            page = await self._ensure_page()
            url = page.url
            title = await page.title()
            return {
                "success": True,
                "action": "get_page_context",
                "url": url,
                "title": title,
                "page_type": self._classify_page(url, title),
            }
        except Exception as e:
            return {"success": False, "action": "get_page_context", "error": str(e)}

    async def get_visible_text(self, max_chars: int = 2000) -> dict:
        try:
            page = await self._ensure_page()
            text = await page.evaluate(
                """() => {
                    const body = document.body;
                    if (!body) return '';
                    return (body.innerText || '').replace(/\\s+/g, ' ').trim();
                }"""
            )
            truncated = text[: max_chars] if isinstance(text, str) else ""
            return {
                "success": True,
                "action": "get_visible_text",
                "url": page.url,
                "title": await page.title(),
                "text": truncated,
                "truncated": isinstance(text, str) and len(text) > max_chars,
                "char_count": len(text or ""),
            }
        except Exception as e:
            return {"success": False, "action": "get_visible_text", "error": str(e)}


# -------------------------------------------------------------------------
# Singleton accessor
# -------------------------------------------------------------------------
_browser_engine: Optional[BrowserEngine] = None
_singleton_lock = asyncio.Lock()


async def get_browser_engine() -> BrowserEngine:
    """Lazy singleton: creates and starts the engine on first call."""
    global _browser_engine
    if _browser_engine is not None and _browser_engine._started:
        return _browser_engine

    async with _singleton_lock:
        if _browser_engine is None:
            _browser_engine = BrowserEngine()
        if not _browser_engine._started:
            await _browser_engine.start()
    return _browser_engine
