"use client";

import { Plus } from "lucide-react";
import type { ConversationSummary } from "../lib/types";

interface Props {
  conversations: ConversationSummary[];
  activeSessionId?: string;
  onSelect?: (sid: string) => void;
  onNewSession?: () => void;
}

function relTime(iso?: string) {
  if (!iso) return "";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "";
  const diff = Date.now() - t;
  const m = Math.floor(diff / 60000);
  if (m < 1) return "now";
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h`;
  return `${Math.floor(h / 24)}d`;
}

export const ConversationSidebar: React.FC<Props> = ({
  conversations,
  activeSessionId,
  onSelect,
  onNewSession,
}) => {
  return (
    <aside
      className="flex flex-col gap-2"
      data-testid="conversation-sidebar"
      aria-label="Past conversations"
    >
      <header className="flex items-center justify-between px-1 pb-2">
        <p className="font-mono text-[10px] tracking-[0.32em] uppercase text-[var(--ink-3)]">
          Sessions
        </p>
        <button
          data-testid="new-session-btn"
          onClick={onNewSession}
          aria-label="Start new session"
          className="glass-soft inline-flex items-center gap-1 px-2 py-1 text-[11px] uppercase tracking-wider font-mono text-[var(--ink-2)] hover:text-[var(--ink-1)]"
        >
          <Plus size={11} /> new
        </button>
      </header>

      {conversations.length === 0 ? (
        <p
          className="font-serif italic text-sm text-[var(--ink-3)] py-4 px-1"
          data-testid="conversation-sidebar-empty"
        >
          Nothing here yet. Your past chats with TaskButler will live here.
        </p>
      ) : (
        <ul className="flex flex-col gap-1">
          {conversations.map((c) => {
            const active = c.session_id === activeSessionId;
            return (
              <li key={c.session_id}>
                <button
                  data-testid={`conversation-item-${c.session_id}`}
                  onClick={() => onSelect?.(c.session_id)}
                  className="glass-soft w-full text-left px-3 py-2.5 transition-colors"
                  style={{
                    background: active
                      ? "var(--hl-mist)"
                      : undefined,
                    color: active ? "var(--ink-1)" : "var(--ink-2)",
                  }}
                >
                  <div className="flex items-baseline justify-between gap-2">
                    <p className="text-[13px] truncate">
                      {c.summary || "Untitled session"}
                    </p>
                    <span className="font-mono text-[10px] text-[var(--ink-3)]">
                      {relTime(c.timestamp)}
                    </span>
                  </div>
                  <p className="font-mono text-[10px] text-[var(--ink-3)] mt-1 uppercase tracking-widest">
                    {c.messages?.length ?? 0} msgs ·{" "}
                    {c.tool_results?.length ?? 0} tools
                  </p>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </aside>
  );
};

export default ConversationSidebar;
