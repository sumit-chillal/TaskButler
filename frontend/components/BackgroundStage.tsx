"use client";

/**
 * Fixed multi-layer animated background. Uses only CSS transforms +
 * opacity (compositor-friendly) and respects prefers-reduced-motion via
 * the rule in globals.css.
 */
export const BackgroundStage = () => (
  <div className="bg-stage" aria-hidden>
    <div className="blob blob-a" />
    <div className="blob blob-b" />
    <div className="blob blob-c" />
    <div className="grain" />
    <div className="vignette" />
  </div>
);

export default BackgroundStage;
