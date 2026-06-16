"""TaskButler - Data Channel Event Publisher

Publishes structured events over the LiveKit data channel so the frontend
can update its UI in real time (tool activity, transcripts, agent state).
"""

import json
import re
import logging
from datetime import datetime
from livekit import rtc

logger = logging.getLogger(__name__)


def _clean_for_publish(text: str) -> str:
    """Strip tool-call markup, JSON blobs, and technical syntax before publishing."""
    if not text:
        return ""
    # Remove angle-bracket tags (e.g., <function=...>)
    text = re.sub(r'<[^>]+>', '', text)
    # Remove standalone JSON blobs (entire line is JSON)
    text = re.sub(r'^\s*\{[^}]*\}\s*$', '', text, flags=re.MULTILINE)
    # Remove function call notation
    text = re.sub(r'\bToolMessage\b.*', '', text)
    # Collapse multiple spaces/newlines
    text = re.sub(r'\s+', ' ', text).strip()
    return text


class EventPublisher:
    """Publishes events over the LiveKit data channel to the frontend."""

    def __init__(self, room: rtc.Room):
        self.room = room

    async def _publish(self, payload: dict) -> None:
        """Encode and publish a JSON payload over the data channel."""
        try:
            data = json.dumps(payload).encode("utf-8")
            await self.room.local_participant.publish_data(data, reliable=True)
        except Exception as e:
            logger.warning(f"EventPublisher._publish failed: {e}")

    async def publish_tool_start(self, tool_name: str, tool_input: dict) -> None:
        """Notify frontend that a tool call has started."""
        await self._publish({
            "type": "tool_start",
            "tool": tool_name,
            "input": tool_input,
            "timestamp": datetime.now().isoformat(),
        })

    async def publish_tool_result(self, tool_name: str, result: dict) -> None:
        """Notify frontend of a completed tool result."""
        await self._publish({
            "type": "tool_result",
            "tool": tool_name,
            "result": result,
            "timestamp": datetime.now().isoformat(),
        })

    async def publish_transcript(self, role: str, text: str) -> None:
        """Publish a cleaned transcript message."""
        cleaned = _clean_for_publish(text)
        if not cleaned:
            return
        await self._publish({
            "type": "transcript",
            "role": role,
            "text": cleaned,
            "timestamp": datetime.now().isoformat(),
        })

    async def publish_agent_state(self, state: str) -> None:
        """Publish agent state change (idle, listening, thinking, speaking)."""
        await self._publish({
            "type": "agent_state",
            "state": state,
            "timestamp": datetime.now().isoformat(),
        })
