"use client";

import { motion } from "framer-motion";
import { CheckCircle2, Link2, Loader2, Unlink2, XCircle } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

interface Props {
  userId: string;
  /**
   * Provider key matches the backend (`google` powers email + calendar,
   * `spotify` powers the environment orchestrator).
   */
  provider: "google" | "spotify";
}

interface StatusPayload {
  linked: boolean;
  email?: string | null;
  scopes?: string[];
  expires_at?: string | null;
}

const PROVIDER_META: Record<
  Props["provider"],
  { label: string; tint: string; powers: string }
> = {
  google: {
    label: "Google",
    tint: "rgba(180,195,255,0.95)",
    powers: "Email + Calendar",
  },
  spotify: {
    label: "Spotify",
    tint: "rgba(87,230,165,0.95)",
    powers: "Focus mode",
  },
};

const BACKEND =
  process.env.REACT_APP_BACKEND_URL ||
  process.env.NEXT_PUBLIC_BACKEND_URL ||
  "";

function api(path: string) {
  return BACKEND ? `${BACKEND.replace(/\/$/, "")}${path}` : path;
}

export const OAuthStatusChip: React.FC<Props> = ({ userId, provider }) => {
  const meta = PROVIDER_META[provider];
  const [status, setStatus] = useState<StatusPayload | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch(
        api(`/api/auth/${provider}/status?user_id=${encodeURIComponent(userId)}`)
      );
      if (!res.ok) {
        setStatus({ linked: false });
        return;
      }
      const data = (await res.json()) as StatusPayload;
      setStatus(data);
    } catch {
      setStatus({ linked: false });
    } finally {
      setLoading(false);
    }
  }, [provider, userId]);

  useEffect(() => {
    fetchStatus();
    // Re-poll when the window regains focus (e.g. after returning from the
    // OAuth consent screen in a new tab).
    const onFocus = () => fetchStatus();
    window.addEventListener("focus", onFocus);
    const t = window.setInterval(fetchStatus, 60_000);
    return () => {
      window.removeEventListener("focus", onFocus);
      window.clearInterval(t);
    };
  }, [fetchStatus]);

  const handleLink = async () => {
    // If already linked we first hit /unlink so the next /init forces a
    // brand-new OAuth handshake. This is the path users need after their
    // Spotify account is upgraded to Premium (the cached free-tier token
    // would otherwise keep returning 403s).
    if (linked) {
      try {
        await fetch(
          api(
            `/api/auth/${provider}/unlink?user_id=${encodeURIComponent(userId)}`
          ),
          { method: "DELETE" }
        );
      } catch {
        /* swallow — we still try to re-link */
      }
      setStatus({ linked: false });
    }
    const url = api(
      `/api/auth/${provider}/init?user_id=${encodeURIComponent(userId)}`
    );
    window.open(url, "_blank", "noopener,noreferrer");
  };

  const handleUnlinkOnly = async (e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await fetch(
        api(
          `/api/auth/${provider}/unlink?user_id=${encodeURIComponent(userId)}`
        ),
        { method: "DELETE" }
      );
    } finally {
      setStatus({ linked: false });
    }
  };

  const linked = !!status?.linked;
  const Icon = loading ? Loader2 : linked ? CheckCircle2 : XCircle;
  const iconStyle = loading
    ? { color: "var(--ink-3)", animation: "spin 1s linear infinite" }
    : linked
    ? { color: "rgba(87,230,165,0.95)" }
    : { color: "var(--ink-3)" };

  return (
    <motion.button
      type="button"
      data-testid={`oauth-chip-${provider}`}
      onClick={handleLink}
      whileTap={{ scale: 0.97 }}
      whileHover={{ y: -1 }}
      className="glass-soft w-full flex items-center justify-between gap-2 px-3 py-2 text-left rounded-xl transition-colors"
      title={
        linked
          ? `${meta.label} linked${
              status?.email ? ` as ${status.email}` : ""
            } — click to force a fresh OAuth handshake`
          : `Link ${meta.label} (${meta.powers})`
      }
      style={{
        border: linked
          ? `1px solid ${meta.tint}`
          : "1px solid rgba(255,255,255,0.06)",
      }}
    >
      <span className="flex items-center gap-2 min-w-0">
        <Icon size={14} style={iconStyle} />
        <span className="flex flex-col min-w-0">
          <span
            className="font-mono text-[10px] tracking-widest uppercase truncate"
            style={{ color: linked ? meta.tint : "var(--ink-3)" }}
          >
            {meta.label}
          </span>
          <span
            className="text-[11px] truncate"
            style={{ color: "var(--ink-2)" }}
          >
            {loading
              ? "checking…"
              : linked
              ? status?.email || "linked"
              : meta.powers}
          </span>
        </span>
      </span>
      <span className="flex items-center gap-1">
        {linked ? (
          <span
            role="button"
            data-testid={`oauth-unlink-${provider}`}
            onClick={handleUnlinkOnly}
            className="opacity-60 hover:opacity-100 p-1 -mr-1"
            title={`Disconnect ${meta.label}`}
          >
            <Unlink2 size={12} style={{ color: "var(--ink-3)" }} />
          </span>
        ) : null}
        <Link2 size={12} style={{ color: "var(--ink-3)" }} aria-hidden />
      </span>
    </motion.button>
  );
};

export default OAuthStatusChip;
