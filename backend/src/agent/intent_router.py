"""
Intent Router — classifies voice commands using regex pattern matching.
No LLM required. Runs in <1ms.
"""
import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class Intent:
    category: str          # "browser" or "agent"
    action: str            # specific action within category
    params: dict           # extracted parameters


# Sites recognized for direct browser navigation
# Stored as module-level dict so it can be extended without code changes
KNOWN_SITES = {
    "youtube": "https://www.youtube.com",
    "spotify": "https://open.spotify.com",
    "gmail": "https://mail.google.com",
    "google": "https://www.google.com",
    "google maps": "https://maps.google.com",
    "maps": "https://maps.google.com",
    "google flights": "https://www.google.com/travel/flights",
    "flights": "https://www.google.com/travel/flights",
    "google calendar": "https://calendar.google.com",
    "calendar": "https://calendar.google.com",
    "amazon": "https://www.amazon.in",
    "twitter": "https://twitter.com",
    "x": "https://twitter.com",
    "instagram": "https://www.instagram.com",
    "whatsapp": "https://web.whatsapp.com",
    "netflix": "https://www.netflix.com",
    "zomato": "https://www.zomato.com",
    "swiggy": "https://www.swiggy.com",
    "ola": "https://www.olacabs.com",
    "uber": "https://www.uber.com",
    "github": "https://www.github.com",
    "linkedin": "https://www.linkedin.com",
    "reddit": "https://www.reddit.com",
}

# Patterns for browser commands — ordered by specificity (most specific first)
_BROWSER_PATTERNS = [
    # Play X on Y platform
    (r"(?:play|put on|start playing)\s+(.+?)\s+(?:on|in)\s+(\w+)", "play_on_platform",
     lambda m: {"query": m.group(1).strip(), "site": m.group(2).strip()}),
    # Play X (implies YouTube or current platform)
    (r"^(?:play|put on)\s+(.+)$", "play",
     lambda m: {"query": m.group(1).strip()}),
    # Open/Go to/Launch site
    (r"(?:open|go to|launch|navigate to|take me to|show me)\s+(.+)", "open_site",
     lambda m: {"site": m.group(1).strip()}),
    # Search X on Y
    (r"search(?:\s+for)?\s+(.+?)\s+on\s+(\w+)", "search_on_site",
     lambda m: {"query": m.group(1).strip(), "site": m.group(2).strip()}),
    # Search X (generic)
    (r"(?:search|look up|find)\s+(.+)", "search",
     lambda m: {"query": m.group(1).strip()}),
    # Go back (must match BEFORE the "previous|back" media pattern)
    (r"(?:^|\b)go\s+back(?:\b|$)", "go_back",
     lambda m: {}),
    (r"^previous\s+page$", "go_back",
     lambda m: {}),
    # Media controls
    (r"^(pause|stop|resume|play|mute|unmute)\b", "media_control",
     lambda m: {"action": m.group(1).lower()}),
    (r"(?:next|skip)(?:\s+song|\s+track)?", "media_control",
     lambda m: {"action": "next"}),
    (r"(?:previous|prev)(?:\s+song|\s+track)?", "media_control",
     lambda m: {"action": "previous"}),
    (r"volume\s+(up|down|increase|decrease)", "media_control",
     lambda m: {"action": f"volume_{m.group(1).replace('increase','up').replace('decrease','down')}"}),
    # Scroll
    (r"scroll\s+(up|down)", "scroll",
     lambda m: {"direction": m.group(1)}),
    # Click
    (r"click\s+(?:on\s+)?(.+)", "click",
     lambda m: {"target": m.group(1).strip()}),
    # Type
    (r"type\s+(.+)", "type_text",
     lambda m: {"text": m.group(1).strip()}),
]

# Commands that always go to the LLM agent regardless of wording
_AGENT_KEYWORDS = [
    "email", "send", "mail", "weather", "temperature",
    "book", "flight", "restaurant", "table", "reservation",
    "alarm", "reminder", "calendar event", "schedule", "meeting",
    "todo", "task", "add to my list", "remember",
    "summarise", "summary", "recap", "what did we",
    "order a cab", "order a ride", "get me a cab",
]


def classify(utterance: str) -> Intent:
    """
    Classify a voice utterance into browser or agent category.
    Returns Intent with category, action, and extracted params.
    """
    text = utterance.lower().strip()
    text = re.sub(r"[^a-z0-9 ']+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    # Check agent keywords first — these always go to LLM
    for keyword in _AGENT_KEYWORDS:
        if keyword in text:
            return Intent(category="agent", action="task", params={"utterance": utterance})

    # Check browser patterns
    for pattern, action, extractor in _BROWSER_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            params = extractor(match)
            return Intent(category="browser", action=action, params=params)

    # Default: send to agent
    return Intent(category="agent", action="conversation", params={"utterance": utterance})
