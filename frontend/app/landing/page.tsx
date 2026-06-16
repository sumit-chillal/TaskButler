"use client";

import Link from "next/link";
import BackgroundStage from "../../components/BackgroundStage";

/**
 * Marketing / landing page for TaskButler.
 * Provides a brief intro and CTA to get started.
 */
export default function LandingPage() {
  return (
    <>
      <BackgroundStage />
      <main
        className="relative z-10 min-h-screen flex flex-col items-center justify-center px-4 text-center"
        data-testid="landing-page"
      >
        <p className="font-mono text-[10px] tracking-[0.4em] uppercase text-[var(--ink-3)]">
          / TaskButler
        </p>
        <h1
          className="font-display tracking-tight mt-4"
          style={{
            fontSize: "clamp(2rem, 6vw, 4.5rem)",
            lineHeight: 0.96,
            color: "var(--ink-1)",
          }}
        >
          Your AI-powered{" "}
          <span className="font-serif italic" style={{ color: "var(--ink-accent)" }}>
            voice
          </span>{" "}
          assistant.
        </h1>
        <p
          className="text-sm mt-5 max-w-md"
          style={{ color: "var(--ink-3)" }}
        >
          TaskButler helps you manage tasks, book flights, set reminders, and
          more — all through natural conversation.
        </p>

        <div className="mt-8 flex gap-4">
          <Link
            href="/login"
            className="inline-flex items-center justify-center gap-2 py-3 px-8 text-sm uppercase tracking-widest font-mono rounded-full"
            style={{
              color: "var(--ink-1)",
              background:
                "linear-gradient(180deg, rgba(196,245,107,0.95), rgba(150,210,80,0.95))",
              boxShadow:
                "inset 0 1px 0 rgba(255,255,255,0.6), 0 8px 28px -8px rgba(196,245,107,0.55)",
            }}
            data-testid="landing-cta"
          >
            Get Started
          </Link>
          <Link
            href="/"
            className="inline-flex items-center justify-center gap-2 py-3 px-8 text-sm uppercase tracking-widest font-mono rounded-full glass-panel"
            style={{ color: "var(--ink-2)" }}
            data-testid="landing-skip"
          >
            Try without login
          </Link>
        </div>
      </main>
    </>
  );
}
