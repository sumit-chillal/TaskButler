"use client";

import type { SystemStatusMap } from "../lib/types";

interface Props {
  status: SystemStatusMap;
}

const ORDER = ["LiveKit", "Groq LLM", "Deepgram STT", "Cartesia TTS", "API Server"];

function colorFor(state: string) {
  const s = state.toLowerCase();
  if (s === "healthy" || s === "active" || s === "connected") return "var(--status-good)";
  if (s === "warn" || s === "warning") return "var(--status-warn)";
  if (s === "error" || s === "down" || s === "offline") return "var(--status-bad)";
  return "var(--status-idle)";
}

export const SystemStatus: React.FC<Props> = ({ status }) => {
  const rows = ORDER.map((name) => ({
    name,
    state: (status?.[name] as string) || "idle",
  }));

  return (
    <section
      data-testid="system-status"
      aria-label="System status"
      className="flex flex-col gap-1.5"
    >
      <p className="font-mono text-[10px] tracking-[0.32em] uppercase text-[var(--ink-3)] mb-1">
        services
      </p>
      <ul className="flex flex-col gap-1">
        {rows.map((r) => (
          <li
            key={r.name}
            data-testid={`system-status-row-${r.name.toLowerCase().replace(/\s+/g, "-")}`}
            className="flex items-center justify-between text-xs"
          >
            <span className="text-[var(--ink-2)]">{r.name}</span>
            <span className="inline-flex items-center gap-2 font-mono uppercase tracking-widest text-[10px] text-[var(--ink-3)]">
              <span
                aria-hidden
                className="inline-block w-1.5 h-1.5 rounded-full"
                style={{
                  background: colorFor(r.state),
                  animation: "status-pulse 2.4s ease-in-out infinite",
                }}
              />
              {r.state}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
};

export default SystemStatus;
