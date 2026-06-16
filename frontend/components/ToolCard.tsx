"use client";

import { motion, AnimatePresence } from "framer-motion";
import {
  AlertTriangle,
  CalendarClock,
  CheckCircle2,
  Disc3,
  Focus,
  Globe,
  Headphones,
  Mail,
  XCircle,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useState } from "react";
import type { ToolResult } from "../lib/types";

interface Props {
  result: ToolResult;
  /** Optional resume hook for HITL cards (Approve / Cancel). */
  onResume?: (approved: boolean, result: ToolResult) => Promise<void> | void;
}

/* -------------------------------------------------------------------- */
/* Pillar registry                                                       */
/* -------------------------------------------------------------------- */
const ICON: Record<string, LucideIcon> = {
  send_email: Mail,
  add_calendar_event: CalendarClock,
  audio_briefing: Headphones,
  environment_orchestrator: Focus,
};

const TINT: Record<string, string> = {
  send_email: "var(--tint-email)",
  add_calendar_event: "var(--tint-calendar)",
  audio_briefing: "var(--tint-todo)",
  environment_orchestrator: "var(--tint-browser)",
};

function tintFor(t: string) {
  return TINT[t] || "var(--tint-browser)";
}

function timeLabel(iso?: string) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

function prettyToolLabel(t: string) {
  return t.replace(/_/g, " ");
}

/* -------------------------------------------------------------------- */
/* Per-pillar body layouts                                               */
/* -------------------------------------------------------------------- */
function CardField({ label, value }: { label: string; value?: string }) {
  if (!value) return null;
  return (
    <div className="flex flex-col">
      <span className="font-mono text-[9px] tracking-widest uppercase text-[var(--ink-3)]">
        {label}
      </span>
      <span
        className="text-sm truncate"
        style={{ color: "var(--ink-1)" }}
        title={value}
      >
        {value}
      </span>
    </div>
  );
}

function EmailBody({ d }: { d: Record<string, any> }) {
  const preview = (d.body_preview as string) || (d.preview as string) || "";
  return (
    <div className="px-6 pb-6 pt-2" data-testid="tool-card-email">
      <p className="font-mono text-[10px] tracking-widest uppercase text-[var(--ink-3)] mb-1">
        to
      </p>
      <p
        className="text-base mb-3 font-mono truncate"
        style={{ color: "var(--ink-1)" }}
        title={(d.to as string) || ""}
      >
        {(d.to as string) || "—"}
      </p>
      <p
        className="font-display tracking-tight text-xl mb-3"
        style={{ color: "var(--ink-1)" }}
      >
        {(d.subject as string) || "(no subject)"}
      </p>
      {preview ? (
        <div
          className="glass-soft px-4 py-3 text-sm leading-relaxed"
          style={{ color: "var(--ink-2)" }}
        >
          {preview}
          {d.body_chars && Number(d.body_chars) > preview.length ? "…" : ""}
        </div>
      ) : null}
    </div>
  );
}

function CalendarBody({ d }: { d: Record<string, any> }) {
  const date = (d.date as string) || "";
  const dayNum = date.match(/\d{4}-\d{2}-(\d{2})/)?.[1] || "—";
  const monthLabel = date.slice(0, 7) || "—";
  const duration =
    (d.duration_minutes && `${d.duration_minutes} min`) ||
    (d.duration as string) ||
    "60 min";
  return (
    <div
      className="px-6 pb-6 pt-2 grid grid-cols-[auto_1fr] gap-5 items-center"
      data-testid="tool-card-calendar"
    >
      <div className="glass-soft text-center px-3 py-2" style={{ minWidth: 76 }}>
        <p className="font-mono text-[10px] tracking-widest uppercase text-[var(--ink-3)]">
          {monthLabel}
        </p>
        <p
          className="font-display"
          style={{ fontSize: "2.4rem", lineHeight: 1, color: "var(--ink-1)" }}
        >
          {dayNum}
        </p>
      </div>
      <div>
        <p className="font-display text-xl text-[var(--ink-1)] mb-1">
          {(d.title as string) || (d.event as string) || "Event"}
        </p>
        <p className="text-sm text-[var(--ink-3)]">
          {(d.time as string) || ""} · {duration}
        </p>
        {d.description ? (
          <p className="text-sm text-[var(--ink-2)] mt-2 line-clamp-2">
            {d.description as string}
          </p>
        ) : null}
      </div>
    </div>
  );
}

function Equalizer({ active }: { active: boolean }) {
  // 7 thin vertical bars, looping sine-driven heights via Framer Motion.
  const bars = [0, 1, 2, 3, 4, 5, 6];
  return (
    <div className="flex items-end gap-[3px] h-8" aria-hidden>
      {bars.map((i) => (
        <motion.span
          key={i}
          className="w-[3px] rounded-full"
          style={{
            background: "rgba(var(--tint-todo),0.85)",
            boxShadow: "0 0 8px rgba(var(--tint-todo),0.4)",
          }}
          initial={{ height: 4 }}
          animate={
            active
              ? {
                  height: [4, 18, 6, 24, 8, 14, 4],
                }
              : { height: 4 }
          }
          transition={{
            duration: 1.1 + (i % 3) * 0.15,
            repeat: Infinity,
            ease: "easeInOut",
            delay: i * 0.07,
          }}
        />
      ))}
    </div>
  );
}

function AudioBriefingBody({ d }: { d: Record<string, any> }) {
  const topic = (d.topic as string) || "your update";
  const script = (d.script as string) || "";
  const sources: Array<{ title?: string; url?: string }> = Array.isArray(d.sources)
    ? (d.sources as any[])
    : [];
  return (
    <div className="px-6 pb-6 pt-2" data-testid="tool-card-audio-briefing">
      <div className="flex items-center justify-between mb-3">
        <div>
          <p className="font-mono text-[10px] tracking-widest uppercase text-[var(--ink-3)]">
            topic
          </p>
          <p
            className="font-display text-lg mt-0.5"
            style={{ color: "var(--ink-1)" }}
          >
            {topic}
          </p>
        </div>
        <Equalizer active />
      </div>
      {script ? (
        <div
          className="glass-soft px-4 py-3 text-sm leading-relaxed"
          style={{ color: "var(--ink-2)" }}
        >
          {script.length > 280 ? `${script.slice(0, 280).trim()}…` : script}
        </div>
      ) : null}
      {sources.length > 0 ? (
        <div className="mt-3" data-testid="briefing-sources">
          <p className="font-mono text-[10px] tracking-widest uppercase text-[var(--ink-3)] mb-1.5">
            sources · {sources.length}
          </p>
          <ul className="flex flex-col gap-1">
            {sources.slice(0, 5).map((s, i) => {
              const label =
                (s.title && s.title.trim()) ||
                (s.url ? new URL(s.url).hostname : `source ${i + 1}`);
              if (!s.url) {
                return (
                  <li
                    key={i}
                    className="text-xs truncate"
                    style={{ color: "var(--ink-3)" }}
                  >
                    {label}
                  </li>
                );
              }
              return (
                <li key={i} className="text-xs truncate">
                  <a
                    href={s.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="hover:underline inline-flex items-center gap-1"
                    style={{ color: "rgba(var(--tint-todo),0.95)" }}
                    title={s.url}
                    data-testid={`briefing-source-${i}`}
                  >
                    <span aria-hidden>↗</span>
                    {label}
                  </a>
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function EnvironmentBody({ d }: { d: Record<string, any> }) {
  const mode = ((d.mode as string) || "focus").replace(/_/g, " ");
  const duration = (d.duration_minutes as number) || 60;
  const calStatus = (d.calendar_status as string) || "";
  const musicStatus = (d.music_status as string) || "";
  const rawNote = (d.note as string) || "";

  // Map machine-readable music_status into a human-friendly card subtitle.
  // `play_focus_music` returns `premium_required` when Spotify rejects with
  // 403 — surface it as a distinct, calmer message instead of a red error.
  let musicCopy = musicStatus;
  let musicTint = "var(--ink-1)";
  let musicNote = rawNote;
  if (musicStatus === "premium_required") {
    musicCopy = "premium needed";
    musicTint = "rgba(255, 184, 108, 0.95)";
    musicNote =
      "Free Spotify accounts can't be controlled remotely — upgrade to Premium to enable playback.";
  } else if (musicStatus === "no_device") {
    musicCopy = "no active device";
    musicNote =
      rawNote ||
      "Open Spotify on your phone or desktop and tap any track once, then ask me to start the music again.";
  } else if (musicStatus === "not_linked") {
    musicCopy = "not linked";
    musicNote = rawNote || "Spotify isn't linked yet — link it from the right panel.";
  } else if (musicStatus === "playing") {
    musicCopy = "playing";
    musicTint = "rgba(87,230,165,0.95)";
  }

  return (
    <div className="px-6 pb-6 pt-2" data-testid="tool-card-environment">
      <div className="flex items-center gap-5">
        {/* Spinning vinyl — only rotates when music is actually playing */}
        <div className="relative" aria-hidden>
          <motion.div
            className="w-14 h-14 rounded-full flex items-center justify-center"
            style={{
              background:
                "radial-gradient(circle at 30% 30%, rgba(var(--tint-browser),0.85), rgba(0,0,0,0.7))",
              boxShadow:
                "0 0 28px -4px rgba(var(--tint-browser),0.55), inset 0 0 0 1px var(--hl-faint)",
            }}
            animate={
              musicStatus === "playing" ? { rotate: 360 } : { rotate: 0 }
            }
            transition={{ duration: 6, repeat: Infinity, ease: "linear" }}
          >
            <Disc3 size={18} style={{ color: "var(--ink-1)" }} />
          </motion.div>
        </div>
        <div>
          <p className="font-mono text-[10px] tracking-widest uppercase text-[var(--ink-3)]">
            mode
          </p>
          <p
            className="font-display text-xl capitalize"
            style={{ color: "var(--ink-1)" }}
          >
            {mode}
          </p>
          <p className="font-mono text-[11px] text-[var(--ink-3)] mt-1">
            {duration} minutes
          </p>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2 glass-soft px-3 py-2 mt-4">
        <CardField label="Calendar" value={calStatus || "—"} />
        <div className="flex flex-col">
          <span className="font-mono text-[9px] tracking-widest uppercase text-[var(--ink-3)]">
            Spotify
          </span>
          <span
            className="text-sm truncate"
            style={{ color: musicTint }}
            title={musicCopy}
            data-testid="env-music-status"
          >
            {musicCopy || "—"}
          </span>
        </div>
      </div>
      {musicNote ? (
        <p className="text-sm text-[var(--ink-2)] mt-3 italic">{musicNote}</p>
      ) : null}
    </div>
  );
}

function GenericBody({ d }: { d: Record<string, any> }) {
  return (
    <div className="px-6 pb-6 pt-2">
      <ul className="grid grid-cols-2 gap-2 glass-soft px-3 py-2">
        {Object.entries(d)
          .slice(0, 6)
          .map(([k, v]) => (
            <CardField
              key={k}
              label={k.replace(/_/g, " ")}
              value={
                typeof v === "object"
                  ? JSON.stringify(v).slice(0, 36)
                  : String(v)
              }
            />
          ))}
      </ul>
    </div>
  );
}

/* -------------------------------------------------------------------- */
/* HITL preview body                                                     */
/* -------------------------------------------------------------------- */
function InterruptPreviewBody({
  tool,
  preview,
}: {
  tool: string;
  preview: Record<string, any>;
}) {
  if (tool === "send_email") return <EmailBody d={preview} />;
  if (tool === "add_calendar_event") return <CalendarBody d={preview} />;
  return <GenericBody d={preview} />;
}

/* -------------------------------------------------------------------- */
/* Approve / Cancel action row                                           */
/* -------------------------------------------------------------------- */
function HitlActions({
  state,
  onApprove,
  onCancel,
}: {
  state: ToolResult["resumeState"];
  onApprove: () => void;
  onCancel: () => void;
}) {
  const settled =
    state === "approved" || state === "cancelled" || state === "error";
  if (settled) {
    const label =
      state === "approved"
        ? "Approved — executing…"
        : state === "cancelled"
        ? "Cancelled"
        : "Couldn't reach the agent";
    const color =
      state === "approved"
        ? "var(--status-good, #57e6a5)"
        : state === "cancelled"
        ? "var(--ink-warn, #ff7b8a)"
        : "var(--ink-warn, #ff7b8a)";
    return (
      <div
        className="px-6 pb-5 pt-2"
        data-testid={`hitl-actions-${state}`}
      >
        <p
          className="font-mono text-[10px] tracking-widest uppercase"
          style={{ color }}
        >
          {label}
        </p>
      </div>
    );
  }
  const busy = state === "approving" || state === "cancelling";
  return (
    <div
      className="px-6 pb-5 pt-2 flex items-center gap-3"
      data-testid="hitl-actions"
    >
      <motion.button
        type="button"
        data-testid="hitl-approve-btn"
        onClick={onApprove}
        disabled={busy}
        whileTap={{ scale: 0.96 }}
        whileHover={!busy ? { y: -1 } : undefined}
        className="flex-1 inline-flex items-center justify-center gap-2 rounded-full px-4 py-2 text-xs font-medium tracking-wider uppercase disabled:opacity-60"
        style={{
          background:
            "linear-gradient(180deg, rgba(87,230,165,0.95), rgba(56,176,124,0.75))",
          color: "rgba(8,18,16,0.95)",
          boxShadow:
            "inset 0 1px 0 rgba(255,255,255,0.35), 0 0 24px -4px rgba(87,230,165,0.6)",
        }}
      >
        <CheckCircle2 size={14} />
        {state === "approving" ? "Approving…" : "Approve"}
      </motion.button>
      <motion.button
        type="button"
        data-testid="hitl-cancel-btn"
        onClick={onCancel}
        disabled={busy}
        whileTap={{ scale: 0.96 }}
        className="inline-flex items-center justify-center gap-2 rounded-full px-4 py-2 text-xs font-medium tracking-wider uppercase disabled:opacity-60"
        style={{
          background: "rgba(255,255,255,0.04)",
          border: "1px solid rgba(255,123,138,0.35)",
          color: "rgba(255,180,190,0.95)",
        }}
      >
        <XCircle size={14} />
        {state === "cancelling" ? "Cancelling…" : "Cancel"}
      </motion.button>
    </div>
  );
}

/* -------------------------------------------------------------------- */
/* Public component                                                     */
/* -------------------------------------------------------------------- */
export const ToolCard: React.FC<Props> = ({ result, onResume }) => {
  const Icon = ICON[result.tool] || Globe;
  const tint = tintFor(result.tool);
  const isError = result.status === "error";
  const isCancelled = result.status === "cancelled";
  const d = result.details || {};
  const [localState, setLocalState] = useState<ToolResult["resumeState"]>(
    result.resumeState
  );

  const liveState = localState || result.resumeState || "pending";

  /* ----- Loading shimmer state ------------------------------------ */
  if (result.isLoading) {
    return (
      <motion.article
        layout
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -8 }}
        transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
        className="glass tint shimmer relative overflow-hidden"
        style={{ ["--tint" as any]: tint }}
        data-testid={`tool-card tool-card-loading`}
      >
        <header className="flex items-center gap-3 px-6 py-5">
          <span className="w-9 h-9 rounded-full flex items-center justify-center">
            <Icon size={16} style={{ opacity: 0.6 }} />
          </span>
          <div>
            <p className="font-mono text-[10px] tracking-widest uppercase text-[var(--ink-3)]">
              {prettyToolLabel(result.tool)}
            </p>
            <h3
              className="font-display tracking-tight"
              style={{ fontSize: "1.05rem", color: "var(--ink-2)" }}
            >
              {result.title}
            </h3>
          </div>
        </header>
      </motion.article>
    );
  }

  /* ----- HITL interrupt state ------------------------------------- */
  if (result.interrupted) {
    const preview = result.payload_preview || {};
    const handleApprove = async () => {
      if (!onResume) return;
      setLocalState("approving");
      try {
        await onResume(true, result);
        setLocalState("approved");
      } catch {
        setLocalState("error");
      }
    };
    const handleCancel = async () => {
      if (!onResume) return;
      setLocalState("cancelling");
      try {
        await onResume(false, result);
        setLocalState("cancelled");
      } catch {
        setLocalState("error");
      }
    };
    return (
      <motion.article
        layout
        initial={{ opacity: 0, y: 8, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: -8 }}
        transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
        className="glass tint glass-hover relative overflow-hidden"
        style={{
          ["--tint" as any]: tint,
          boxShadow:
            "0 0 0 1px rgba(255,255,255,0.05), 0 0 28px -8px rgba(var(--tint-todo),0.45)",
        }}
        data-testid={`tool-card tool-card-${result.tool} tool-card-interrupted`}
      >
        <span aria-hidden className="tint-glow absolute inset-0" />
        <header className="flex items-center justify-between gap-3 px-6 pt-5 pb-3">
          <div className="flex items-center gap-3">
            <span
              className="w-9 h-9 rounded-full flex items-center justify-center"
              style={{
                boxShadow:
                  "inset 0 0 0 1px var(--hl-faint), 0 0 24px -6px rgba(180,195,255,0.5)",
              }}
            >
              <Icon size={16} />
            </span>
            <div>
              <p
                className="font-mono text-[10px] tracking-widest uppercase"
                style={{ color: "rgba(var(--tint-todo),0.9)" }}
              >
                awaiting approval · {prettyToolLabel(result.tool)}
              </p>
              <h3
                className="font-display tracking-tight"
                style={{ fontSize: "1.05rem", color: "var(--ink-1)" }}
              >
                {result.title || "Review and approve"}
              </h3>
            </div>
          </div>
          <span className="font-mono text-[10px] text-[var(--ink-3)]">
            {timeLabel(result.timestamp)}
          </span>
        </header>
        <InterruptPreviewBody tool={result.tool} preview={preview} />
        <HitlActions
          state={liveState}
          onApprove={handleApprove}
          onCancel={handleCancel}
        />
      </motion.article>
    );
  }

  /* ----- Settled result state ------------------------------------- */
  let body: React.ReactNode;
  switch (result.tool) {
    case "send_email":
      body = <EmailBody d={d} />;
      break;
    case "add_calendar_event":
      body = <CalendarBody d={d} />;
      break;
    case "audio_briefing":
      body = <AudioBriefingBody d={d} />;
      break;
    case "environment_orchestrator":
      body = <EnvironmentBody d={d} />;
      break;
    default:
      body = <GenericBody d={d} />;
  }

  return (
    <AnimatePresence mode="wait">
      <motion.article
        layout
        initial={{ opacity: 0, y: 8, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: -8 }}
        transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
        className="glass tint glass-hover relative overflow-hidden"
        style={{ ["--tint" as any]: tint }}
        data-testid={`tool-card tool-card-${result.tool}`}
      >
        <span aria-hidden className="tint-glow absolute inset-0" />
        <header className="flex items-center justify-between gap-3 px-6 pt-5 pb-3">
          <div className="flex items-center gap-3">
            <span
              className="w-9 h-9 rounded-full flex items-center justify-center"
              style={{
                boxShadow:
                  "inset 0 0 0 1px var(--hl-faint), 0 0 24px -6px rgba(180,195,255,0.5)",
              }}
            >
              {isError ? (
                <AlertTriangle size={16} style={{ color: "var(--ink-warn)" }} />
              ) : isCancelled ? (
                <XCircle size={16} style={{ color: "var(--ink-warn)" }} />
              ) : (
                <Icon size={16} />
              )}
            </span>
            <div>
              <p className="font-mono text-[10px] tracking-widest uppercase text-[var(--ink-3)]">
                {prettyToolLabel(result.tool)}
              </p>
              <h3
                className="font-display tracking-tight"
                style={{ fontSize: "1.05rem", color: "var(--ink-1)" }}
              >
                {result.title}
              </h3>
            </div>
          </div>
          <span className="font-mono text-[10px] text-[var(--ink-3)]">
            {timeLabel(result.timestamp)}
          </span>
        </header>
        {body}
      </motion.article>
    </AnimatePresence>
  );
};

export default ToolCard;
