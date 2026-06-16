"use client";

import type { NetworkQuality as Q } from "../lib/types";

interface Props {
  quality: Q;
}

const LEVELS: Q[] = ["offline", "poor", "ok", "good", "excellent"];

export const NetworkQuality: React.FC<Props> = ({ quality }) => {
  const level = Math.max(0, LEVELS.indexOf(quality));
  return (
    <div
      data-testid={`network-quality-${quality}`}
      className="inline-flex items-end gap-[3px] h-4"
      aria-label={`Network ${quality}`}
    >
      {[0, 1, 2, 3].map((i) => {
        const active = i < level;
        return (
          <span
            key={i}
            className="block w-[3px] rounded-sm origin-bottom"
            style={{
              height: `${(i + 1) * 25}%`,
              background: active
                ? "linear-gradient(180deg, var(--status-good), rgba(var(--tint-todo),0.4))"
                : "var(--hl-faint)",
              animation: active
                ? `signal-bar 2.2s ease-in-out infinite ${i * 0.15}s`
                : undefined,
            }}
          />
        );
      })}
    </div>
  );
};

export default NetworkQuality;
