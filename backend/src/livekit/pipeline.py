"""TaskButler - LiveKit Voice Pipeline

Implements the full voice pipeline:
  Deepgram STT -> LangGraph Agent (via custom LLM wrapper) -> Cartesia TTS

The LangGraphLLM class wraps the LangGraph ReAct agent to conform to
the livekit-agents LLM interface, streaming text tokens and publishing
tool events over the data channel.
"""

import os
import json
import asyncio
import logging
from typing import Any

from livekit import agents, rtc
from livekit.agents import (
    Agent,
    AgentSession,
    AutoSubscribe,
    JobContext,
    WorkerOptions,
    llm,
    function_tool,
    RunContext,
)
from livekit.agents.llm import (
    ChatContext,
    ChatChunk,
    ChoiceDelta,
    FunctionToolCall,
    LLM,
    LLMStream,
    Tool,
    ChatMessage,
)
from livekit.agents import stt, tts, vad, APIConnectOptions, DEFAULT_API_CONNECT_OPTIONS
from livekit.plugins import deepgram, cartesia, silero

from ..agent.graph import get_agent
from ..agent.prompts import TASKBUTLER_SYSTEM_PROMPT
from ..agent.runtime_context import current_user_id
from ..memory.preferences import detect_preferences
from ..memory.vector_store import get_memory
from ..utils.text_filters import clean_tts_text
from .events import EventPublisher

logger = logging.getLogger(__name__)

# Timeout for LLM API calls (seconds)
LLM_TIMEOUT = 15.0


class LangGraphLLMStream(LLMStream):
    """Custom LLMStream that runs the LangGraph agent and streams results."""

    def __init__(
        self,
        llm_instance: "LangGraphLLM",
        *,
        chat_ctx: ChatContext,
        tools: list[Tool],
        conn_options: APIConnectOptions,
        publisher: EventPublisher | None,
        session_id: str,
        user_id: str = "default",
    ):
        super().__init__(
            llm=llm_instance,
            chat_ctx=chat_ctx,
            tools=tools,
            conn_options=conn_options,
        )
        self._publisher = publisher
        self._session_id = session_id
        self._user_id = user_id

    def _convert_chat_ctx_to_messages(self, chat_ctx: ChatContext) -> list:
        """Convert LiveKit ChatContext to LangGraph-compatible message tuples."""
        messages = []
        for item in chat_ctx.items:
            if isinstance(item, ChatMessage):
                role = item.role
                text = item.text_content or ""
                if role == "system" or role == "developer":
                    messages.append(("system", text))
                elif role == "user":
                    messages.append(("user", text))
                elif role == "assistant":
                    messages.append(("assistant", text))
        return messages

    async def _run(self) -> None:
        """Run the LangGraph agent and stream chunks back with timeout protection."""
        _user_token = current_user_id.set(self._user_id)
        try:
            messages = self._convert_chat_ctx_to_messages(self._chat_ctx)
            if not messages:
                return

            # Identify the latest user utterance for memory storage / context
            last_user_message = next(
                (txt for role, txt in reversed(messages) if role == "user"),
                "",
            )

            # ---- Phase 2: Intent routing — bypass LLM for browser commands ----
            if last_user_message.strip():
                from src.agent.intent_router import classify
                from src.agent.browser_dispatcher import execute as browser_execute

                intent = classify(last_user_message)
                if intent.category == "browser":
                    request_id = f"router-{self._session_id}"

                    # Publish user transcript and thinking state
                    if self._publisher:
                        try:
                            await self._publisher.publish_transcript("user", last_user_message)
                        except Exception as e:
                            logger.warning(f"Failed to publish user transcript: {e}")
                        try:
                            await self._publisher.publish_agent_state("thinking")
                        except Exception:
                            pass

                    # Execute the browser intent on the dedicated browser loop.
                    # browser_execute() is sync and uses _run_async internally.
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(None, browser_execute, intent)

                    spoken = result.get("spoken_text", "Done.")
                    tool_card = result.get("tool_card")

                    # Publish tool result so the frontend ToolCard renders
                    if self._publisher and tool_card:
                        tool_name = tool_card.get("tool", f"browser_{intent.action}")
                        try:
                            await self._publisher.publish_tool_result(tool_name, tool_card)
                        except Exception as e:
                            logger.warning(f"Failed to publish browser tool result: {e}")

                    # Stream the spoken confirmation to TTS
                    self._event_ch.send_nowait(ChatChunk(
                        id=request_id,
                        delta=ChoiceDelta(role="assistant", content=spoken),
                    ))

                    # Publish assistant transcript
                    if self._publisher:
                        try:
                            await self._publisher.publish_transcript("assistant", spoken)
                        except Exception as e:
                            logger.warning(f"Failed to publish transcript: {e}")

                    # Persist this turn to memory
                    try:
                        memory = await get_memory()
                        await memory.store_interaction(
                            session_id=self._session_id,
                            user_id=self._user_id,
                            role="user",
                            content=last_user_message,
                        )
                        await memory.store_interaction(
                            session_id=self._session_id,
                            user_id=self._user_id,
                            role="assistant",
                            content=spoken,
                            metadata={"router": "browser", "action": intent.action},
                        )
                    except Exception as e:
                        logger.warning("Memory persistence skipped (router): %s", e)

                    return  # Do NOT fall through to LangGraph

            # Publish user transcript immediately so the frontend shows it
            if self._publisher and last_user_message:
                try:
                    await self._publisher.publish_transcript("user", last_user_message)
                except Exception as e:
                    logger.warning(f"Failed to publish user transcript: {e}")
                try:
                    await self._publisher.publish_agent_state("thinking")
                except Exception:
                    pass

            # ---- Phase 3: pull relevant past context from vector memory ----
            memory = None
            try:
                memory = await get_memory()
                if last_user_message:
                    ctx_hits = await memory.retrieve_relevant_context(
                        query=last_user_message,
                        user_id=self._user_id,
                        n_results=5,
                    )
                    if ctx_hits:
                        ctx_lines = "\n".join(
                            f"- ({h['metadata'].get('role', '?')}): {h['content']}"
                            for h in ctx_hits
                        )
                        prefs = await memory.get_user_preferences(self._user_id)
                        pref_line = (
                            "Known user preferences: "
                            + ", ".join(f"{k}={v}" for k, v in prefs.items())
                            if prefs else ""
                        )
                        sys_note = (
                            "Relevant context from past conversations:\n"
                            + ctx_lines
                            + (f"\n{pref_line}" if pref_line else "")
                        )
                        # Insert as a system note immediately before the latest user msg
                        messages = [("system", sys_note)] + messages
            except Exception as e:
                logger.warning("Memory context retrieval skipped: %s", e)

            agent = get_agent()
            config = {"configurable": {"thread_id": self._session_id}}

            request_id = f"langgraph-{self._session_id}"
            full_response = ""
            last_tool_title: str | None = None

            async def _stream_agent():
                nonlocal full_response, last_tool_title
                async for event in agent.astream_events(
                    {"messages": messages},
                    config=config,
                    version="v2"
                ):
                    kind = event["event"]

                    # Stream text content (filter out function call syntax)
                    if kind == "on_chat_model_stream":
                        chunk_data = event["data"]["chunk"]
                        content = chunk_data.content if hasattr(chunk_data, 'content') else ""
                        if content:
                            filtered_content = clean_tts_text(content)
                            if filtered_content and not filtered_content.isspace():
                                full_response += filtered_content
                                chat_chunk = ChatChunk(
                                    id=request_id,
                                    delta=ChoiceDelta(
                                        role="assistant",
                                        content=filtered_content,
                                    ),
                                )
                                self._event_ch.send_nowait(chat_chunk)

                    # Tool call started
                    elif kind == "on_tool_start":
                        tool_name = event["name"]
                        tool_input = event["data"].get("input", {})
                        logger.info(f"Tool call started: {tool_name} | Input: {tool_input}")

                        if self._publisher:
                            try:
                                await self._publisher.publish_tool_start(tool_name, tool_input)
                            except Exception as e:
                                logger.warning(f"Failed to publish tool_start: {e}")

                    # Tool call completed
                    elif kind == "on_tool_end":
                        tool_name = event["name"]
                        output = event["data"].get("output", "")

                        # Parse the tool result
                        result = {}
                        if hasattr(output, 'content'):
                            try:
                                result = json.loads(output.content) if isinstance(output.content, str) else output.content
                            except (json.JSONDecodeError, TypeError):
                                result = {"raw": str(output.content)}
                        elif isinstance(output, dict):
                            result = output
                        else:
                            try:
                                result = json.loads(str(output)) if isinstance(str(output), str) else output
                            except Exception:
                                result = {"raw": str(output)}

                        if isinstance(result, dict) and result.get("title"):
                            last_tool_title = result["title"]

                        logger.info(f"Tool call completed: {tool_name} | Status: {result.get('status', 'unknown')}")

                        if self._publisher:
                            try:
                                await self._publisher.publish_tool_result(tool_name, result)
                            except Exception as e:
                                logger.warning(f"Failed to publish tool_result: {e}")

            # Run with timeout protection
            try:
                await asyncio.wait_for(_stream_agent(), timeout=LLM_TIMEOUT)
            except asyncio.TimeoutError:
                logger.error(f"LLM call timed out after {LLM_TIMEOUT}s")
                timeout_chunk = ChatChunk(
                    id=request_id,
                    delta=ChoiceDelta(
                        role="assistant",
                        content="I'm sorry, I'm having some trouble right now. Please try again.",
                    ),
                )
                self._event_ch.send_nowait(timeout_chunk)
                full_response = "I'm sorry, I'm having some trouble right now. Please try again."

            # Phase 3 fallback: if the LLM emitted no clean text but a tool ran,
            # speak a brief confirmation so the user isn't left in silence.
            if not full_response.strip() and last_tool_title:
                fallback = f"Done. {last_tool_title}."
                self._event_ch.send_nowait(ChatChunk(
                    id=request_id,
                    delta=ChoiceDelta(role="assistant", content=fallback),
                ))
                full_response = fallback

            # Final sanitize pass on the accumulated transcript text in case
            # the model emitted multi-chunk tool-call markup that slipped past
            # the per-chunk filter (we cannot strip from already-spoken TTS,
            # but we can clean the published transcript).
            from ..utils.text_filters import sanitize_transcript_text
            full_response = sanitize_transcript_text(full_response)

            # Publish full transcript after stream completes
            if self._publisher and full_response:
                try:
                    await self._publisher.publish_transcript("assistant", full_response)
                except Exception as e:
                    logger.warning(f"Failed to publish transcript: {e}")

            # ---- Phase 3: persist this turn + auto-detect user preferences ----
            if memory is not None:
                try:
                    if last_user_message:
                        await memory.store_interaction(
                            session_id=self._session_id,
                            user_id=self._user_id,
                            role="user",
                            content=last_user_message,
                        )
                        # Auto-detect & store preferences uttered by the user
                        prefs = detect_preferences(last_user_message)
                        for k, v in prefs.items():
                            await memory.store_user_preference(self._user_id, k, v)
                    if full_response:
                        await memory.store_interaction(
                            session_id=self._session_id,
                            user_id=self._user_id,
                            role="assistant",
                            content=full_response,
                            metadata={"tool": last_tool_title} if last_tool_title else None,
                        )
                except Exception as e:
                    logger.warning("Memory persistence skipped: %s", e)

        except Exception as e:
            logger.error(f"LangGraph stream error: {e}", exc_info=True)

            # Check for rate limit or context length error
            error_message = str(e).lower()
            if "rate limit" in error_message or "429" in error_message:
                error_chunk = ChatChunk(
                    id="error",
                    delta=ChoiceDelta(
                        role="assistant",
                        content="I've reached my API rate limit. Please try again in a minute.",
                    ),
                )
            elif "context_length" in error_message or "maximum context" in error_message or "too many tokens" in error_message:
                # Reset session to avoid perpetual context overflow
                import time
                self._session_id = f"{self._session_id}-{int(time.time())}"
                error_chunk = ChatChunk(
                    id="error",
                    delta=ChoiceDelta(
                        role="assistant",
                        content="Our conversation got too long. I've started fresh — go ahead and ask me anything!",
                    ),
                )
            else:
                error_chunk = ChatChunk(
                    id="error",
                    delta=ChoiceDelta(
                        role="assistant",
                        content="I had a hiccup processing that. Could you try again?",
                    ),
                )
            self._event_ch.send_nowait(error_chunk)
        finally:
            current_user_id.reset(_user_token)


class LangGraphLLM(LLM):
    """Custom LLM wrapper that routes requests through the LangGraph agent."""

    def __init__(self, publisher: EventPublisher | None = None, session_id: str = "default", user_id: str = "default"):
        super().__init__()
        self._publisher = publisher
        self._session_id = session_id
        self._user_id = user_id

    @property
    def model(self) -> str:
        return os.getenv("GROQ_MODEL", "llama3-groq-8b-8192-tool-use-preview")

    @property
    def provider(self) -> str:
        return "groq-langgraph"

    def chat(
        self,
        *,
        chat_ctx: ChatContext,
        tools: list[Tool] | None = None,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
        parallel_tool_calls: Any = None,
        tool_choice: Any = None,
        extra_kwargs: Any = None,
    ) -> LLMStream:
        """Create a new LLMStream that runs the LangGraph agent."""
        return LangGraphLLMStream(
            llm_instance=self,
            chat_ctx=chat_ctx,
            tools=tools or [],
            conn_options=conn_options,
            publisher=self._publisher,
            session_id=self._session_id,
            user_id=self._user_id,
        )

    async def aclose(self) -> None:
        pass


class TaskButlerAgent:
    """Main LiveKit agent entrypoint."""

    async def entrypoint(self, ctx: JobContext):
        """Called when a participant joins a LiveKit room."""
        await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

        publisher = EventPublisher(ctx.room)

        # Read voice_gender from room metadata or participant metadata
        voice_gender = "female"
        try:
            # Wait for a remote participant to join and read their metadata
            import json as _json
            # Check room metadata first
            if ctx.room.metadata:
                meta = _json.loads(ctx.room.metadata)
                voice_gender = meta.get("voice_gender", "female")
            else:
                # Fall back to checking participant metadata
                for p in ctx.room.remote_participants.values():
                    if p.metadata:
                        meta = _json.loads(p.metadata)
                        voice_gender = meta.get("voice_gender", "female")
                        break
        except Exception as e:
            logger.warning(f"Could not read voice_gender from metadata: {e}")

        # Select voice based on gender
        voices = {
            "female": os.getenv("CARTESIA_VOICE_FEMALE", "a0e99841-438c-4a64-b679-ae501e7d6091"),
            "male": os.getenv("CARTESIA_VOICE_MALE", "820a3788-2b37-4d21-847a-b65d8a68c99a"),
        }
        selected_voice = voices.get(voice_gender, voices["female"])

        # The room name is also used as the per-user vector-memory partition key
        # so context follows a user across sessions in the same room.
        llm_wrapper = LangGraphLLM(
            publisher=publisher,
            session_id=ctx.room.name,
            user_id=ctx.room.name,
        )

        session = AgentSession(
            stt=deepgram.STT(),
            llm=llm_wrapper,
            tts=cartesia.TTS(
                voice=selected_voice,
                model=os.getenv("CARTESIA_MODEL", "sonic-english"),
            ),
            vad=silero.VAD.load(),
            allow_interruptions=True,
            min_interruption_duration=float(os.getenv("INTERRUPT_SPEECH_DURATION", "0.5")),
            min_interruption_words=int(os.getenv("INTERRUPT_MIN_WORDS", "0")),
        )

        await session.start(
            room=ctx.room,
            agent=Agent(instructions=TASKBUTLER_SYSTEM_PROMPT),
        )

        # Listen for speak_request events forwarded by /speak (from text-input UI)
        # so the agent voices the typed-chat reply too.
        @ctx.room.on("data_received")
        def _on_room_data(data_packet):
            try:
                payload = json.loads(data_packet.data.decode("utf-8"))
            except Exception:
                return
            if payload.get("type") == "speak_request":
                text = (payload.get("text") or "").strip()
                if text:
                    asyncio.ensure_future(session.say(text, allow_interruptions=True))

        # Greeting message
        greeting = os.getenv(
            "AGENT_GREETING",
            "Hey, I'm TaskButler. What can I help you with today?"
        )
        await session.say(greeting, allow_interruptions=True)
