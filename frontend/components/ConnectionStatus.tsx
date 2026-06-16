"use client";

import type { NetworkQuality as Q } from "../lib/types";
import NetworkQuality from "./NetworkQuality";

interface Props {
  isConnected: boolean;
  quality: Q;
}

export const ConnectionStatus: React.FC<Props> = ({ isConnected, quality }) => {
  const dotColor = !isConnected
    ? "var(--status-bad)"
    : quality === "poor"
    ? "var(--status-warn)"
    : "var(--status-good)";

  const label = !isConnected ? "Offline" : quality.charAt(0).toUpperCase() + quality.slice(1);

  return (
    <div
      data-testid="connection-status"
      className="glass-soft inline-flex items-center gap-2 px-3 py-1.5"
      aria-live="polite"
      style={{ borderRadius: 999 }}
    >
      <span
        aria-hidden
        className="inline-block w-1.5 h-1.5 rounded-full"
        style={{
          background: dotColor,
          animation: isConnected ? "status-pulse 2s ease-in-out infinite" : undefined,
        }}
      />
      <span
        className="font-mono uppercase text-[10px] tracking-widest"
        style={{ color: "var(--ink-2)" }}
      >
        {label}
      </span>
      <NetworkQuality quality={quality} />
    </div>
  );
};

export default ConnectionStatus;
