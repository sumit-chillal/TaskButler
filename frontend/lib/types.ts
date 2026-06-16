/**
 * TaskButler shared TypeScript types.
 *
 * Mirrors the structured dicts the backend tools and the LiveKit data
 * channel emit. Anything visible to the frontend is typed here so that
 * components stay decoupled from the hook implementation.
 */

export type ToolName =
  | "send_email"
  | "add_calendar_event"
  | "audio_briefing"
  | "environment_orchestrator";

export type ToolStatus = "success" | "error" | "cancelled" | "degraded";

export interface ToolResult {
  tool: ToolName | string;
  status: ToolStatus | string;
  icon: string;
  title: string;
  details: Record<string, unknown>;
  timestamp: string;
  id?: string;
  isLoading?: boolean;
  /** Set when the backend graph paused on an interrupt awaiting approval. */
  interrupted?: boolean;
  payload_preview?: Record<string, unknown>;
  /** Tracks the resume request lifecycle for HITL cards. */
  resumeState?: "pending" | "approving" | "cancelling" | "approved" | "cancelled" | "error";
  session_id?: string;
  user_id?: string;
}

export type MessageRole = "user" | "assistant" | "system";

export interface Message {
  id: string;
  role: MessageRole;
  text: string;
  timestamp: string;
}

export type AgentStateName =
  | "idle"
  | "listening"
  | "thinking"
  | "speaking"
  | "connecting";

export interface AgentState {
  state: AgentStateName;
  audioLevel?: number;
}

export type VoiceGender = "female" | "male";

export interface ConversationSummary {
  session_id: string;
  summary: string;
  messages: Message[];
  tool_results: ToolResult[];
  timestamp: string;
  duration_seconds: number;
}

export interface SystemStatusMap {
  [service: string]: "healthy" | "active" | "connected" | "error" | "warn" | string;
}

export type NetworkQuality = "excellent" | "good" | "ok" | "poor" | "offline";

export interface UserProfile {
  name: string;
  email: string;
}
