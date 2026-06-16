"use client";

interface Props {
  summary?: string;
  durationSeconds?: number;
  toolsUsed?: number;
}

export const ConversationSummary: React.FC<Props> = ({
  summary,
  durationSeconds,
  toolsUsed,
}) => {
  if (!summary) return null;
  return (
    <article
      className="glass tint p-5"
      style={{ ["--tint" as any]: "var(--tint-flight)" }}
      data-testid="conversation-summary"
    >
      <p className="font-mono text-[10px] tracking-widest uppercase text-[var(--ink-3)] mb-2">
        session summary
      </p>
      <p
        className="font-serif italic text-lg leading-snug"
        style={{ color: "var(--ink-1)" }}
      >
        {summary}
      </p>
      <div className="flex gap-4 mt-3">
        {typeof durationSeconds === "number" && (
          <span className="font-mono text-[10px] uppercase tracking-widest text-[var(--ink-3)]">
            {Math.floor(durationSeconds / 60)}m{" "}
            {durationSeconds % 60}s
          </span>
        )}
        {typeof toolsUsed === "number" && (
          <span className="font-mono text-[10px] uppercase tracking-widest text-[var(--ink-3)]">
            {toolsUsed} tools used
          </span>
        )}
      </div>
    </article>
  );
};

export default ConversationSummary;
