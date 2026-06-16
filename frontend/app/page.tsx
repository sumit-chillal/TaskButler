"use client";

import Link from "next/link";
import { useState } from "react";
import AuraVisualizer from "../components/AuraVisualizer";
import BackgroundStage from "../components/BackgroundStage";
import ConnectionStatus from "../components/ConnectionStatus";
import ConversationSidebar from "../components/ConversationSidebar";
import ConversationSummary from "../components/ConversationSummary";
import OAuthStatusChip from "../components/OAuthStatus";
import SystemStatus from "../components/SystemStatus";
import TextInputBar from "../components/TextInputBar";
import ToolCard from "../components/ToolCard";
import Transcript from "../components/Transcript";
import UserProfileChip from "../components/UserProfile";
import VoiceGenderToggle from "../components/VoiceGenderToggle";
import { useTaskButler } from "../lib/useTaskButler";

export default function HomePage() {
  const tb = useTaskButler();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <>
      <BackgroundStage />

      <main
        data-testid="dashboard"
        className="relative z-10 min-h-screen px-4 md:px-8 py-6 md:py-8 grid gap-4"
        style={{
          gridTemplateColumns: "minmax(0, 1fr)",
        }}
      >
        {/* Top bar ----------------------------------------------------- */}
        <header className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <button
              data-testid="sidebar-toggle"
              aria-label="Toggle sessions sidebar"
              onClick={() => setSidebarOpen((s) => !s)}
              className="md:hidden glass-soft px-3 py-1.5 text-[10px] tracking-widest uppercase font-mono"
              style={{ borderRadius: 999 }}
            >
              menu
            </button>
            <p className="font-mono text-[10px] tracking-[0.4em] uppercase text-[var(--ink-3)]">
              / TaskButler
            </p>
          </div>
          <nav className="flex items-center gap-2">
            <Link
              href="/memory"
              data-testid="link-memory"
              className="glass-soft px-3 py-1.5 text-[10px] tracking-widest uppercase font-mono text-[var(--ink-2)] hover:text-[var(--ink-1)]"
              style={{ borderRadius: 999 }}
            >
              memory of you
            </Link>
            <ConnectionStatus
              isConnected={tb.isConnected}
              quality={tb.networkQuality}
            />
            <UserProfileChip
              user={tb.user}
              onLogout={() => {
                try {
                  window.localStorage.removeItem("taskbutler_user");
                } catch (e) {
                  console.warn("[page] logout cleanup failed:", e);
                }
                window.location.reload();
              }}
            />
          </nav>
        </header>

        {/* Three-panel layout ----------------------------------------- */}
        <div
          className="grid gap-4 md:gap-6 items-stretch"
          style={{
            gridTemplateColumns: "minmax(0, 1fr)",
            gridTemplateRows: "minmax(0, 1fr)",
          }}
        >
          <div
            className="grid gap-4 md:gap-6 min-h-[78vh]"
            style={{
              gridTemplateColumns:
                "minmax(0, 14rem) minmax(0, 1fr) minmax(0, 22rem)",
            }}
          >
            {/* Left: sessions ------------------------------------- */}
            <section
              className={`glass-panel p-5 md:p-6 ${
                sidebarOpen
                  ? "fixed inset-x-3 inset-y-20 z-30 md:relative md:inset-auto"
                  : "hidden md:flex"
              } flex-col gap-3 overflow-y-auto scrollbar-glass`}
              data-testid="left-panel"
            >
              <ConversationSidebar
                conversations={tb.conversations}
                activeSessionId={tb.sessionId}
                onNewSession={tb.newSession}
              />
              <div className="mt-auto pt-4">
                <ConversationSummary
                  summary={undefined /* live summary saved via /api/summarise */}
                />
              </div>
            </section>

            {/* Center: voice + transcript + input ----------------- */}
            <section
              className="glass-panel relative p-5 md:p-8 flex flex-col gap-4 overflow-hidden"
              data-testid="center-panel"
            >
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="font-mono text-[10px] tracking-[0.4em] uppercase text-[var(--ink-3)]">
                    your butler
                  </p>
                  <h1
                    className="font-display tracking-tight"
                    style={{
                      fontSize: "var(--fs-display-lg)",
                      lineHeight: 0.96,
                      color: "var(--ink-1)",
                    }}
                  >
                    What can I take{" "}
                    <span className="font-serif italic" style={{ color: "var(--ink-accent)" }}>
                      off your plate
                    </span>
                    ?
                  </h1>
                </div>
                <div className="flex flex-col items-end gap-2">
                  <VoiceGenderToggle
                    value={tb.voiceGender}
                    onChange={tb.setVoiceGender}
                  />
                  <button
                    data-testid="voice-toggle-btn"
                    onClick={async () => {
                      try {
                        if (tb.voiceConnected) await tb.voiceDisconnect();
                        else await tb.voiceConnect();
                      } catch (e) {
                        // surface the error in the transcript so it's visible
                        console.error("voice connect failed:", e);
                      }
                    }}
                    className="glass-soft inline-flex items-center gap-2 px-3 py-1.5 text-[10px] tracking-widest uppercase font-mono"
                    style={{
                      borderRadius: 999,
                      color: tb.voiceConnected ? "var(--ink-warn)" : "var(--ink-accent)",
                    }}
                  >
                    <span
                      aria-hidden
                      className="w-1.5 h-1.5 rounded-full"
                      style={{
                        background: tb.voiceConnected ? "var(--status-good)" : "var(--ink-3)",
                        animation: tb.voiceConnected ? "status-pulse 2s ease-in-out infinite" : undefined,
                      }}
                    />
                    {tb.voiceConnected ? "leave voice" : "join voice"}
                  </button>
                </div>
              </div>

              <div className="flex items-center justify-center py-4">
                <AuraVisualizer
                  state={tb.agentState}
                  size={200}
                  audioLevel={tb.audioLevel}
                />
              </div>

              {tb.audioBlocked ? (
                <div
                  data-testid="audio-blocked-banner"
                  role="status"
                  className="glass-soft px-4 py-2.5 flex items-center justify-between gap-3 text-sm"
                  style={{
                    border: "1px solid rgba(255,184,108,0.55)",
                    color: "var(--ink-1)",
                  }}
                >
                  <span>
                    Audio is blocked by your browser. Click anywhere to enable
                    voice playback.
                  </span>
                </div>
              ) : null}

              <div
                className="flex-1 min-h-[200px] max-h-[44vh] overflow-y-auto scrollbar-glass"
                data-testid="transcript-shell"
              >
                <Transcript messages={tb.messages} isThinking={tb.isThinking} />
              </div>

              <TextInputBar
                onSend={tb.sendTextMessage}
                disabled={tb.isThinking}
              />
            </section>

            {/* Right: live tool feed + system ---------------------- */}
            <section
              className="glass-panel p-5 md:p-6 flex flex-col gap-5 overflow-y-auto scrollbar-glass"
              data-testid="right-panel"
            >
              <SystemStatus status={tb.systemStatus} />

              <div className="flex flex-col gap-2" data-testid="oauth-status">
                <p className="font-mono text-[10px] tracking-[0.32em] uppercase text-[var(--ink-3)]">
                  connections
                </p>
                <OAuthStatusChip
                  userId={tb.user?.email || "default"}
                  provider="google"
                />
                <OAuthStatusChip
                  userId={tb.user?.email || "default"}
                  provider="spotify"
                />
              </div>

              <div className="flex flex-col gap-3 flex-1 min-h-0">
                <p className="font-mono text-[10px] tracking-[0.32em] uppercase text-[var(--ink-3)]">
                  live results
                </p>
                {tb.toolResults.length === 0 ? (
                  <p
                    className="font-serif italic text-sm text-[var(--ink-3)]"
                    data-testid="tool-feed-empty"
                  >
                    Nothing yet. Ask me to send an email, schedule something,
                    play a briefing, or start a focus session — the result
                    will appear here as a glass card.
                  </p>
                ) : (
                  <div className="flex flex-col gap-3" data-testid="tool-feed">
                    {tb.toolResults.slice(0, 8).map((r, i) => (
                      <ToolCard
                        key={r.id || `${r.timestamp}-${i}`}
                        result={r}
                        onResume={tb.resumeTool}
                      />
                    ))}
                  </div>
                )}
              </div>
            </section>
          </div>
        </div>

        {/* Mobile stack: panels render full-width below 768px via CSS query */}
        <style jsx>{`
          @media (max-width: 1024px) {
            [data-testid="dashboard"] > div > div {
              grid-template-columns: minmax(0, 1fr) !important;
            }
          }
        `}</style>

        {/* Session summary overlay — appears when voice disconnects with >=2 msgs */}
        {tb.showSummary && (
          <div
            data-testid="session-summary-overlay"
            className="fixed inset-0 z-40 flex items-center justify-center bg-black/50 backdrop-blur-md p-4"
            onClick={() => tb.setShowSummary(false)}
          >
            <div
              onClick={(e) => e.stopPropagation()}
              className="max-w-lg w-full"
            >
              <ConversationSummary
                summary={tb.sessionSummaryText}
                toolsUsed={tb.toolResults.length}
              />
              <div className="mt-3 flex justify-end">
                <button
                  data-testid="session-summary-close"
                  onClick={() => tb.setShowSummary(false)}
                  className="glass-soft px-4 py-1.5 text-[10px] tracking-widest uppercase font-mono"
                  style={{ borderRadius: 999, color: "var(--ink-1)" }}
                >
                  close
                </button>
              </div>
            </div>
          </div>
        )}
      </main>
    </>
  );
}
