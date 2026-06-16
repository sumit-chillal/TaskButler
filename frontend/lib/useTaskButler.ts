/**
 * useTaskButler — the only data hook the UI consumes.
 *
 * Phase 4 + voice (Phase 5): wires real LiveKit duplex audio.
 *  - publishes the user's microphone to the agent room
 *  - subscribes to the agent's TTS audio track and plays it
 *  - listens to the data channel for `agent_state`, `tool_result`,
 *    and `transcript` events emitted by the backend EventPublisher
 *  - barge-in is handled by the backend's Silero VAD, which interrupts
 *    TTS when the user starts speaking; client just keeps the mic open
 *
 * Falls back to text-only if /api/token isn't available, so the same
 * hook works offline / in a browser with no microphone permission.
 */

"use client";

import {
  Room,
  RoomEvent,
  Track,
  type RemoteAudioTrack,
  type RemoteTrack,
  type RemoteTrackPublication,
  type RemoteParticipant,
} from "livekit-client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type {
  AgentStateName,
  ConversationSummary,
  Message,
  NetworkQuality,
  SystemStatusMap,
  ToolResult,
  UserProfile,
  VoiceGender,
} from "./types";
import { sanitizeTranscript } from "./sanitize";

const BACKEND =
  process.env.REACT_APP_BACKEND_URL ||
  process.env.NEXT_PUBLIC_BACKEND_URL ||
  "";

function api(path: string) {
  return BACKEND ? `${BACKEND.replace(/\/$/, "")}${path}` : path;
}

function newSessionId() {
  return `s_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

export interface UseTaskButler {
  sessionId: string;
  user: UserProfile | null;
  messages: Message[];
  toolResults: ToolResult[];
  agentState: AgentStateName;
  audioLevel: number;
  audioBlocked: boolean;
  unlinkProvider: (provider: "google" | "spotify") => Promise<void>;
  isThinking: boolean;
  isConnected: boolean;
  voiceConnected: boolean;
  micEnabled: boolean;
  voiceGender: VoiceGender;
  setVoiceGender: (g: VoiceGender) => void;
  conversations: ConversationSummary[];
  systemStatus: SystemStatusMap;
  networkQuality: NetworkQuality;
  sendTextMessage: (text: string) => Promise<void>;
  resumeTool: (approved: boolean, result: ToolResult) => Promise<void>;
  newSession: () => void;
  loadHistory: () => Promise<void>;
  refreshStatus: () => Promise<void>;
  saveSummary: () => Promise<string>;
  voiceConnect: () => Promise<void>;
  voiceDisconnect: () => Promise<void>;
  toggleMic: () => Promise<void>;
  showSummary: boolean;
  setShowSummary: (v: boolean) => void;
  sessionSummaryText: string;
}

export function useTaskButler(): UseTaskButler {
  const sessionRef = useRef<string>("");
  if (!sessionRef.current) sessionRef.current = newSessionId();
  const userRef = useRef<UserProfile | null>(null);
  if (!userRef.current && typeof window !== "undefined") {
    try {
      const raw = window.localStorage.getItem("taskbutler_user");
      if (raw) userRef.current = JSON.parse(raw) as UserProfile;
    } catch (e) {
      console.warn("[useTaskButler] Failed to read user profile:", e);
    }
  }

  const [sessionId, setSessionId] = useState(sessionRef.current);
  const [user, setUser] = useState<UserProfile | null>(userRef.current);
  const [messages, setMessages] = useState<Message[]>([]);
  const [toolResults, setToolResults] = useState<ToolResult[]>([]);
  const [agentState, setAgentState] = useState<AgentStateName>("idle");
  const [audioLevel, setAudioLevel] = useState<number>(0);
  const [audioBlocked, setAudioBlocked] = useState<boolean>(false);
  const [isThinking, setIsThinking] = useState(false);
  const [voiceGender, setVoiceGenderState] = useState<VoiceGender>("female");
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [systemStatus, setSystemStatus] = useState<SystemStatusMap>({});
  const [networkQuality, setNetworkQuality] = useState<NetworkQuality>("good");
  const [voiceConnected, setVoiceConnected] = useState(false);
  const [micEnabled, setMicEnabled] = useState(false);
  const [showSummary, setShowSummary] = useState(false);
  const [sessionSummaryText, setSessionSummaryText] = useState<string>("");
  const prevVoiceConnected = useRef(false);

  const isConnected = useMemo(
    () => Object.keys(systemStatus).length > 0,
    [systemStatus]
  );

  // ----- LiveKit room ----------------------------------------------------
  const roomRef = useRef<Room | null>(null);
  const audioElRef = useRef<HTMLAudioElement | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const audioMonitorTimer = useRef<number | null>(null);

  const handleData = useCallback((payload: Uint8Array) => {
    let data: any;
    try {
      data = JSON.parse(new TextDecoder().decode(payload));
    } catch {
      return;
    }
    if (!data || typeof data !== "object") return;
    if (data.type === "agent_state" && typeof data.state === "string") {
      setAgentState(data.state as AgentStateName);
    }
    if (data.type === "tool_start") {
      setAgentState("thinking");
      setIsThinking(true);
      const toolName = (data.tool as string) || "tool";
      setToolResults((prev) => [
        {
          id: `loading-${toolName}`,
          tool: toolName,
          status: "success" as const,
          icon: "loader",
          title: `${toolName.replace(/_/g, " ")}…`,
          details: data.input || {},
          timestamp: data.timestamp || new Date().toISOString(),
          isLoading: true,
        },
        ...prev,
      ].slice(0, 8));
    }
    if (data.type === "tool_result" && data.result) {
      const result = data.result as ToolResult;
      setToolResults((prev) => {
        const loadingId = `loading-${data.tool || result.tool}`;
        const hasLoading = prev.some((c) => c.id === loadingId);
        if (hasLoading) {
          return prev.map((c) =>
            c.id === loadingId
              ? { ...result, id: `result-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`, isLoading: false }
              : c
          );
        }
        return [{ ...result, id: `result-${Date.now()}`, isLoading: false }, ...prev].slice(0, 8);
      });
      setIsThinking(false);
      setAgentState("speaking");
    }
    if (data.type === "interrupted" && data.tool_name) {
      const sid = sessionRef.current;
      const uid = (userRef.current && userRef.current.email) || "default";
      setToolResults((prev) => [
        {
          tool: data.tool_name as string,
          status: "success",
          icon: "shield-check",
          title: "Review and approve",
          details: {},
          timestamp: data.timestamp || new Date().toISOString(),
          id: `interrupt-${Date.now()}`,
          interrupted: true,
          payload_preview: (data.payload_preview as Record<string, unknown>) || {},
          resumeState: "pending" as const,
          session_id: sid,
          user_id: uid,
        } as ToolResult,
        ...prev,
      ].slice(0, 8));
      setIsThinking(false);
    }
    if (data.type === "transcript" && data.text) {
      const clean = String(data.text)
        .replace(/<function=[^>]+>/g, "")
        .replace(/<tool_call>[\s\S]*?<\/tool_call>/g, "")
        .replace(/^\s*\{[\s\S]*?\}\s*$/gm, "")
        .trim();
      if (!clean) return;
      const role: Message["role"] = data.role === "user" ? "user" : "assistant";
      setMessages((m) => [
        ...m,
        {
          id: `${role}_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
          role,
          text: sanitizeTranscript(clean),
          timestamp: data.timestamp || new Date().toISOString(),
        },
      ]);
      if (data.role === "user") {
        setAgentState("thinking");
        setIsThinking(true);
      } else if (data.role === "assistant") {
        setIsThinking(false);
        setAgentState("idle");
      }
    }
  }, []);

  const startAudioMeter = useCallback((track: RemoteAudioTrack) => {
    try {
      const stream = new MediaStream([track.mediaStreamTrack]);
      const ctx =
        audioCtxRef.current ||
        new (window.AudioContext || (window as any).webkitAudioContext)();
      audioCtxRef.current = ctx;
      const src = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      src.connect(analyser);
      const data = new Uint8Array(analyser.frequencyBinCount);
      if (audioMonitorTimer.current) window.clearInterval(audioMonitorTimer.current);
      audioMonitorTimer.current = window.setInterval(() => {
        analyser.getByteFrequencyData(data);
        let sum = 0;
        for (let i = 0; i < data.length; i++) sum += data[i];
        const avg = sum / data.length / 255;
        setAudioLevel(avg);
      }, 80) as unknown as number;
    } catch {
      // audio meter is best-effort
    }
  }, []);

  const voiceConnect = useCallback(async () => {
    if (roomRef.current) return;
    setAgentState("connecting");
    const sid = sessionRef.current;
    const uid = (userRef.current && userRef.current.email) || "default";
    let url = "";
    let token = "";
    try {
      const res = await fetch(
        api(
          `/api/token?room=${encodeURIComponent(sid)}&identity=${encodeURIComponent(uid)}&voice_gender=${voiceGender}`
        )
      );
      if (!res.ok) throw new Error(`token ${res.status}`);
      const data = await res.json();
      url = data.url || data.ws_url || "";
      token = data.token || data.access_token || "";
    } catch (e) {
      setAgentState("idle");
      throw e;
    }
    if (!url || !token) {
      setAgentState("idle");
      throw new Error("invalid token response");
    }

    const room = new Room({
      adaptiveStream: true,
      dynacast: true,
      audioCaptureDefaults: { autoGainControl: true, echoCancellation: true, noiseSuppression: true },
    });

    room.on(RoomEvent.DataReceived, (payload) => handleData(payload));
    room.on(
      RoomEvent.TrackSubscribed,
      (track: RemoteTrack, _pub: RemoteTrackPublication, _p: RemoteParticipant) => {
        if (track.kind === Track.Kind.Audio) {
          const at = track as RemoteAudioTrack;
          // Create the <audio> element explicitly so we can control
          // autoplay + iOS playsInline + an explicit play() that throws
          // a typed error when Chrome blocks autoplay. Then we surface
          // a "tap to enable audio" affordance to the user.
          const el = document.createElement("audio");
          el.autoplay = true;
          el.muted = false;
          el.controls = false;
          el.setAttribute("playsinline", "true");
          el.style.display = "none";
          document.body.appendChild(el);
          at.attach(el);
          audioElRef.current = el;

          const tryPlay = () => {
            const p = el.play();
            if (p && typeof p.catch === "function") {
              p.catch((err) => {
                console.warn("[useTaskButler] audio autoplay blocked:", err);
                setAudioBlocked(true);
                // One-shot unlock on the next user gesture anywhere.
                const unlock = () => {
                  el.play()
                    .then(() => setAudioBlocked(false))
                    .catch(() => {});
                  document.removeEventListener("click", unlock);
                  document.removeEventListener("keydown", unlock);
                  document.removeEventListener("touchstart", unlock);
                };
                document.addEventListener("click", unlock);
                document.addEventListener("keydown", unlock);
                document.addEventListener("touchstart", unlock);
              });
            }
          };
          tryPlay();
          startAudioMeter(at);
        }
      }
    );
    room.on(RoomEvent.Disconnected, () => {
      setVoiceConnected(false);
      setMicEnabled(false);
      setAgentState("idle");
    });
    room.on(RoomEvent.ConnectionQualityChanged, (q) => {
      const map: Record<string, NetworkQuality> = {
        excellent: "excellent",
        good: "good",
        poor: "poor",
        lost: "offline",
        unknown: "ok",
      };
      setNetworkQuality(map[q] || "ok");
    });

    await room.connect(url, token);
    await room.localParticipant.setMicrophoneEnabled(true);

    roomRef.current = room;
    setVoiceConnected(true);
    setMicEnabled(true);
    setAgentState("listening");
  }, [handleData, startAudioMeter, voiceGender]);

  const voiceDisconnect = useCallback(async () => {
    const r = roomRef.current;
    if (audioMonitorTimer.current) {
      window.clearInterval(audioMonitorTimer.current);
      audioMonitorTimer.current = null;
    }
    if (audioElRef.current) {
      audioElRef.current.remove();
      audioElRef.current = null;
    }
    if (r) {
      await r.disconnect();
      roomRef.current = null;
    }
    setVoiceConnected(false);
    setMicEnabled(false);
    setAgentState("idle");
    setAudioLevel(0);
  }, []);

  const toggleMic = useCallback(async () => {
    const r = roomRef.current;
    if (!r) return;
    const next = !micEnabled;
    await r.localParticipant.setMicrophoneEnabled(next);
    setMicEnabled(next);
  }, [micEnabled]);

  // ----- text chat (unchanged) ------------------------------------------
  const sendTextMessage = useCallback(async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return;
    const sid = sessionRef.current;
    const uid = (userRef.current && userRef.current.email) || "default";

    const userMsg: Message = {
      id: `u_${Date.now()}`,
      role: "user",
      text: trimmed,
      timestamp: new Date().toISOString(),
    };
    setMessages((m) => [...m, userMsg]);
    setIsThinking(true);
    setAgentState("thinking");

    try {
      const res = await fetch(api("/api/chat"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: trimmed, session_id: sid, user_id: uid }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const cleaned = sanitizeTranscript(data.response || "");

      setMessages((m) => [
        ...m,
        {
          id: `a_${Date.now()}`,
          role: "assistant",
          text: cleaned,
          timestamp: new Date().toISOString(),
        },
      ]);

      // HITL: backend paused before a state-changing tool (email / calendar).
      // Render an "awaiting approval" card with the payload preview.
      if (data.interrupted) {
        const interruptCard: ToolResult = {
          tool: (data.tool_name as string) || "tool",
          status: "success",
          icon: "shield-check",
          title: cleaned || "Review and approve",
          details: {},
          timestamp: new Date().toISOString(),
          id: `interrupt-${Date.now()}`,
          interrupted: true,
          payload_preview: data.payload_preview || {},
          resumeState: "pending",
          session_id: sid,
          user_id: uid,
        };
        setToolResults((t) => [interruptCard, ...t].slice(0, 8));
      }

      const newTools = (data.tool_results || []) as ToolResult[];
      if (newTools.length) setToolResults((t) => [...newTools, ...t]);

      // If a voice room is connected, ask the agent to speak the typed reply.
      if (cleaned && voiceConnected && roomRef.current?.name) {
        fetch(api("/api/speak"), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            text: cleaned,
            room: roomRef.current.name,
          }),
        }).catch((e) => {
          console.warn("[useTaskButler] /speak relay failed:", e);
        });
      }
    } catch (e) {
      console.warn("[useTaskButler] /chat request failed:", e);
      setMessages((m) => [
        ...m,
        {
          id: `a_${Date.now()}`,
          role: "assistant",
          text: "I couldn't reach my brain — please try again in a moment.",
          timestamp: new Date().toISOString(),
        },
      ]);
      setNetworkQuality("poor");
    } finally {
      setIsThinking(false);
      setAgentState(voiceConnected ? "listening" : "idle");
    }
  }, [voiceConnected]);

  // ----- HITL resume -----------------------------------------------------
  const resumeTool = useCallback(
    async (approved: boolean, result: ToolResult) => {
      const sid = result.session_id || sessionRef.current;
      const uid =
        result.user_id ||
        (userRef.current && userRef.current.email) ||
        "default";
      const interruptId = result.id;
      try {
        const res = await fetch(api("/api/chat/resume"), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            session_id: sid,
            user_id: uid,
            approved,
          }),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        const cleaned = sanitizeTranscript(data.response || "");

        // Replace the interrupt card with the final tool result (or remove it
        // if the agent paused again — the new interrupt card will be added).
        setToolResults((prev) => {
          const filtered = prev.filter((c) => c.id !== interruptId);
          const newCards: ToolResult[] = [];
          if (data.interrupted) {
            newCards.push({
              tool: (data.tool_name as string) || "tool",
              status: "success",
              icon: "shield-check",
              title: cleaned || "Review and approve",
              details: {},
              timestamp: new Date().toISOString(),
              id: `interrupt-${Date.now()}`,
              interrupted: true,
              payload_preview: data.payload_preview || {},
              resumeState: "pending",
              session_id: sid,
              user_id: uid,
            });
          }
          const settled = (data.tool_results || []) as ToolResult[];
          return [...newCards, ...settled, ...filtered].slice(0, 8);
        });

        if (cleaned) {
          setMessages((m) => [
            ...m,
            {
              id: `a_${Date.now()}`,
              role: "assistant",
              text: cleaned,
              timestamp: new Date().toISOString(),
            },
          ]);
        }
      } catch (e) {
        console.warn("[useTaskButler] /chat/resume failed:", e);
        throw e;
      }
    },
    []
  );

  // ----- OAuth unlink (used by the dashboard re-link affordance) --------
  const unlinkProvider = useCallback(
    async (provider: "google" | "spotify") => {
      const uid =
        (userRef.current && userRef.current.email) || "default";
      try {
        await fetch(
          api(
            `/api/auth/${provider}/unlink?user_id=${encodeURIComponent(uid)}`
          ),
          { method: "DELETE" }
        );
      } catch (e) {
        console.warn("[useTaskButler] unlink failed:", e);
      }
    },
    []
  );

  const newSession = useCallback(() => {
    const next = newSessionId();
    sessionRef.current = next;
    setSessionId(next);
    setMessages([]);
    setToolResults([]);
    setAgentState(voiceConnected ? "listening" : "idle");
  }, [voiceConnected]);

  const setVoiceGender = useCallback((g: VoiceGender) => {
    setVoiceGenderState(g);
    fetch(api("/api/set-voice"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ room: sessionRef.current, voice_gender: g }),
    }).catch((e) => {
      console.warn("[useTaskButler] set-voice request failed:", e);
    });
  }, []);

  const loadHistory = useCallback(async () => {
    const uid = (userRef.current && userRef.current.email) || "default";
    try {
      const res = await fetch(
        api(`/api/conversation/history?user_id=${encodeURIComponent(uid)}`)
      );
      if (!res.ok) return;
      const data = await res.json();
      setConversations(data.conversations || []);
    } catch (e) {
      console.warn("[useTaskButler] loadHistory failed:", e);
    }
  }, []);

  const refreshStatus = useCallback(async () => {
    try {
      const res = await fetch(api("/api/status"));
      if (!res.ok) {
        setNetworkQuality("poor");
        return;
      }
      const data = await res.json();
      setSystemStatus(data.status || {});
      if (!voiceConnected) setNetworkQuality("excellent");
    } catch {
      setNetworkQuality("offline");
    }
  }, [voiceConnected]);

  const saveSummary = useCallback(async () => {
    const uid = (userRef.current && userRef.current.email) || "default";
    try {
      const sumRes = await fetch(api("/api/summarise"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages }),
      });
      const sum = sumRes.ok ? (await sumRes.json()).summary : "";
      await fetch(api("/api/conversation/save"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: uid,
          session_id: sessionRef.current,
          summary: sum,
          messages,
          tool_results: toolResults,
          timestamp: new Date().toISOString(),
        }),
      });
      await loadHistory();
      return sum;
    } catch (e) {
      console.warn("[useTaskButler] saveSummary failed:", e);
      return "";
    }
  }, [messages, toolResults, loadHistory]);

  // login event hook
  useEffect(() => {
    function onLogin(e: Event) {
      const detail = (e as CustomEvent).detail as UserProfile;
      userRef.current = detail;
      setUser(detail);
      try {
        window.localStorage.setItem("taskbutler_user", JSON.stringify(detail));
      } catch (e) {
        console.warn("[useTaskButler] localStorage write failed:", e);
      }
      loadHistory();
    }
    window.addEventListener("taskbutler:login", onLogin as EventListener);
    return () =>
      window.removeEventListener("taskbutler:login", onLogin as EventListener);
  }, [loadHistory]);

  // Session summary: trigger when voice disconnects with at least 2 messages
  useEffect(() => {
    if (prevVoiceConnected.current && !voiceConnected && messages.length >= 2) {
      saveSummary().then((sum) => {
        setSessionSummaryText(sum || "Session ended.");
        setShowSummary(true);
      });
    }
    prevVoiceConnected.current = voiceConnected;
  }, [voiceConnected, messages.length, saveSummary]);

  useEffect(() => {
    refreshStatus();
    loadHistory();
    const t = setInterval(refreshStatus, 30000);
    return () => clearInterval(t);
  }, [refreshStatus, loadHistory]);

  // cleanup on unmount
  useEffect(() => {
    return () => {
      voiceDisconnect().catch((e) => {
        console.warn("[useTaskButler] voiceDisconnect on unmount failed:", e);
      });
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return {
    sessionId,
    user,
    messages,
    toolResults,
    agentState,
    audioLevel,
    audioBlocked,
    unlinkProvider,
    isThinking,
    isConnected,
    voiceConnected,
    micEnabled,
    voiceGender,
    setVoiceGender,
    conversations,
    systemStatus,
    networkQuality,
    sendTextMessage,
    resumeTool,
    newSession,
    loadHistory,
    refreshStatus,
    saveSummary,
    voiceConnect,
    voiceDisconnect,
    toggleMic,
    showSummary,
    setShowSummary,
    sessionSummaryText,
  };
}
