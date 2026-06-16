"use client";

import { useEffect, useRef } from "react";
import type { Message } from "../lib/types";
import { sanitizeTranscript } from "../lib/sanitize";

interface Props {
  messages: Message[];
  isThinking?: boolean;
}

export const Transcript: React.FC<Props> = ({ messages, isThinking }) => {
  const endRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length, isThinking]);

  return (
    <div
      className="flex flex-col gap-3 overflow-y-auto px-1 scrollbar-glass"
      data-testid="transcript"
      style={{ maxHeight: "100%" }}
    >
      {messages.length === 0 && !isThinking && (
        <div
          className="font-serif italic text-[var(--ink-3)] text-lg leading-snug py-10 px-2"
          data-testid="transcript-empty"
        >
          Speak, type, or just think out loud.
          <br />
          <span className="text-[var(--ink-4)]">
            I remember everything you tell me.
          </span>
        </div>
      )}

      {messages.map((m) => {
        const isUser = m.role === "user";
        const tint = isUser ? "var(--tint-ride)" : "var(--tint-calendar)";
        const cleaned = sanitizeTranscript(m.text);
        if (!cleaned) return null;
        return (
          <div
            key={m.id}
            data-testid={`message-${m.role}`}
            className="flex"
            style={{
              justifyContent: isUser ? "flex-end" : "flex-start",
              animation: "card-enter 0.45s var(--ease-glass) both",
            }}
          >
            <div
              className="glass tint relative max-w-[78%] px-4 py-3"
              style={{ ["--tint" as any]: tint }}
            >
              <p
                className="font-mono text-[10px] tracking-widest uppercase mb-1"
                style={{ color: "var(--ink-3)" }}
              >
                {isUser ? "you" : "taskbutler"}
              </p>
              <p
                className="font-body leading-relaxed"
                style={{ color: "var(--ink-1)", fontSize: "var(--fs-body)" }}
              >
                {cleaned}
              </p>
            </div>
          </div>
        );
      })}

      {isThinking && (
        <div className="flex" data-testid="transcript-thinking">
          <div
            className="glass tint px-5 py-4 inline-flex items-end gap-1"
            style={{ ["--tint" as any]: "var(--tint-calendar)" }}
            aria-label="assistant thinking"
          >
            {[0, 1, 2, 3, 4].map((i) => (
              <span
                key={i}
                className="block"
                style={{
                  width: 3,
                  height: 22,
                  borderRadius: 2,
                  background:
                    "linear-gradient(180deg, var(--hl-strong), rgba(var(--tint-calendar),0.6))",
                  transformOrigin: "center",
                  animation: `wave-bar 1.0s var(--ease-soft) infinite ${i * 0.1}s`,
                }}
              />
            ))}
          </div>
        </div>
      )}

      <div ref={endRef} />
    </div>
  );
};

export default Transcript;
