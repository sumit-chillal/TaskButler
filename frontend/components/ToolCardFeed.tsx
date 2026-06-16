"use client";

import type { ToolResult } from "../lib/types";
import ToolCard from "./ToolCard";

interface Props {
  results: ToolResult[];
  /** Maximum number of cards to show (default: unlimited). */
  limit?: number;
  /** HITL resume handler — required to render Approve/Cancel buttons. */
  onResume?: (approved: boolean, result: ToolResult) => Promise<void> | void;
}

/**
 * Scrollable feed of ToolCard results.
 * Shows the most recent tool invocations in reverse-chronological order.
 */
export default function ToolCardFeed({ results, limit, onResume }: Props) {
  const items = limit ? results.slice(0, limit) : results;

  if (items.length === 0) {
    return (
      <div
        className="flex items-center justify-center h-full opacity-40 text-xs font-mono tracking-widest uppercase"
        data-testid="tool-feed-empty"
      >
        No tool activity yet
      </div>
    );
  }

  return (
    <div
      className="flex flex-col gap-3 overflow-y-auto max-h-full pr-1 custom-scrollbar"
      data-testid="tool-feed"
    >
      {items.map((result, idx) => (
        <ToolCard
          key={result.id || `${result.tool}_${idx}`}
          result={result}
          onResume={onResume}
        />
      ))}
    </div>
  );
}
