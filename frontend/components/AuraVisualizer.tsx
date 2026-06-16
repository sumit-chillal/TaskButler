"use client";

import { useEffect, useRef, useState } from "react";
import type { AgentStateName } from "../lib/types";

interface Props {
  state: AgentStateName;
  size?: number;
  audioLevel?: number;
}

const ANIM: Record<AgentStateName, string> = {
  idle: "orb-idle 6s ease-in-out infinite",
  listening: "orb-listen 1.6s ease-in-out infinite",
  thinking: "orb-think 4s linear infinite",
  speaking: "orb-speak 0.8s ease-in-out infinite",
  connecting: "orb-idle 3s ease-in-out infinite",
};

const TINT: Record<AgentStateName, string> = {
  idle: "rgba(var(--tint-flight), 0.55)",
  listening: "rgba(var(--tint-ride), 0.75)",
  thinking: "rgba(var(--tint-calendar), 0.80)",
  speaking: "rgba(var(--tint-todo), 0.75)",
  connecting: "rgba(var(--tint-browser), 0.55)",
};

/**
 * Liquid glass orb. Drag anywhere on screen; it springs back with a
 * subtle bounce when you let go.
 */
export const AuraVisualizer: React.FC<Props> = ({ state, size = 220, audioLevel }) => {
  const tint = TINT[state] || TINT.idle;
  const stateLabel = state.toUpperCase();

  const [drag, setDrag] = useState({ x: 0, y: 0, dragging: false, snap: false });
  const start = useRef<{ x: number; y: number; ox: number; oy: number } | null>(null);

  useEffect(() => {
    function move(e: PointerEvent) {
      if (!start.current) return;
      e.preventDefault();
      setDrag((d) => ({
        ...d,
        x: e.clientX - start.current!.x + start.current!.ox,
        y: e.clientY - start.current!.y + start.current!.oy,
      }));
    }
    function up() {
      if (!start.current) return;
      start.current = null;
      // Spring back to origin
      setDrag({ x: 0, y: 0, dragging: false, snap: true });
      window.setTimeout(() => setDrag((d) => ({ ...d, snap: false })), 600);
    }
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    window.addEventListener("pointercancel", up);
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      window.removeEventListener("pointercancel", up);
    };
  }, []);

  function onPointerDown(e: React.PointerEvent) {
    start.current = {
      x: e.clientX,
      y: e.clientY,
      ox: drag.x,
      oy: drag.y,
    };
    setDrag((d) => ({ ...d, dragging: true, snap: false }));
  }

  // audio-driven scale boost while speaking
  const audioScale = state === "speaking" ? 1 + Math.min(0.18, (audioLevel || 0) * 0.6) : 1;

  return (
    <div
      className="relative inline-flex items-center justify-center select-none"
      style={{
        width: size,
        height: size,
        transform: `translate3d(${drag.x}px, ${drag.y}px, 0) scale(${drag.dragging ? 1.05 : 1})`,
        transition: drag.snap
          ? "transform 600ms var(--ease-spring)"
          : drag.dragging
          ? "none"
          : "transform 220ms var(--ease-glass)",
        cursor: drag.dragging ? "grabbing" : "grab",
        touchAction: "none",
      }}
      data-testid={`aura-${state}`}
      onPointerDown={onPointerDown}
    >
      {(state === "listening" || state === "speaking") && (
        <>
          <span aria-hidden className="absolute inset-0 rounded-full"
            style={{ background: `radial-gradient(circle, ${tint} 0%, transparent 60%)`,
                     animation: "ripple 1.8s ease-out infinite" }} />
          <span aria-hidden className="absolute inset-0 rounded-full"
            style={{ background: `radial-gradient(circle, ${tint} 0%, transparent 60%)`,
                     animation: "ripple 1.8s ease-out infinite 0.6s" }} />
        </>
      )}

      <div
        className="relative rounded-full overflow-hidden"
        style={{
          width: "78%",
          height: "78%",
          animation: ANIM[state] || ANIM.idle,
          transform: `scale(${audioScale})`,
          background: `radial-gradient(circle at 30% 28%, var(--hl-strong) 0%, ${tint} 32%, rgba(var(--tint-flight),0.5) 78%)`,
          boxShadow:
            "inset 0 8px 18px var(--hl-soft), inset 0 -10px 22px var(--shade-soft), 0 30px 70px -22px var(--shade-deep)",
          willChange: "transform",
        }}
      >
        <span aria-hidden className="absolute"
          style={{ top: "8%", left: "18%", width: "44%", height: "30%", borderRadius: "50%",
                   background: "radial-gradient(ellipse, var(--hl-strong) 0%, transparent 70%)",
                   filter: "blur(2px)", opacity: 0.95 }} />
        <span aria-hidden className="absolute inset-0"
          style={{ background: "conic-gradient(from 90deg, transparent 0deg, var(--hl-faint) 60deg, transparent 120deg, var(--hl-mist) 200deg, transparent 270deg)",
                   mixBlendMode: "screen", opacity: 0.6 }} />
      </div>

      <span
        className="absolute bottom-[-2.2rem] font-mono uppercase text-[10px] tracking-[0.42em]"
        style={{ color: "var(--ink-3)" }}
        data-testid="aura-state-label"
      >
        {stateLabel}
      </span>
    </div>
  );
};

export default AuraVisualizer;
