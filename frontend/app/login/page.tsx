"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Mail, Lock, ArrowRight } from "lucide-react";
import BackgroundStage from "../../components/BackgroundStage";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const profile = {
        name: (email.split("@")[0] || "Friend").replace(/\b\w/g, (c) =>
          c.toUpperCase()
        ),
        email,
      };
      try {
        window.localStorage.setItem("taskbutler_user", JSON.stringify(profile));
      } catch (e) {
        console.warn("[login] localStorage write failed:", e);
      }
      window.dispatchEvent(
        new CustomEvent("taskbutler:login", { detail: profile })
      );
      router.push("/");
    } catch (err: any) {
      setError(err?.message || "sign in failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <BackgroundStage />
      <main
        className="relative z-10 min-h-screen flex items-center justify-center px-4"
        data-testid="login-page"
      >
        <form
          onSubmit={submit}
          className="glass-panel relative p-8 md:p-10 w-full max-w-md flex flex-col gap-5"
        >
          <div>
            <p className="font-mono text-[10px] tracking-[0.4em] uppercase text-[var(--ink-3)]">
              / TaskButler
            </p>
            <h1
              className="font-display tracking-tight mt-2"
              style={{
                fontSize: "var(--fs-display-lg)",
                lineHeight: 0.96,
                color: "var(--ink-1)",
              }}
            >
              Welcome{" "}
              <span className="font-serif italic" style={{ color: "var(--ink-accent)" }}>
                back
              </span>
              .
            </h1>
            <p
              className="text-sm mt-3"
              style={{ color: "var(--ink-3)", maxWidth: 320 }}
            >
              Sign in so I can remember you across sessions and personalise
              everything I do.
            </p>
          </div>

          <label className="block">
            <span className="font-mono text-[10px] tracking-widest uppercase text-[var(--ink-3)]">
              email
            </span>
            <div className="mt-2 relative">
              <Mail
                size={14}
                aria-hidden
                className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--ink-3)]"
              />
              <input
                data-testid="login-email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@domain.com"
                className="glass-input w-full pl-9"
                autoComplete="email"
              />
            </div>
          </label>

          <label className="block">
            <span className="font-mono text-[10px] tracking-widest uppercase text-[var(--ink-3)]">
              password
            </span>
            <div className="mt-2 relative">
              <Lock
                size={14}
                aria-hidden
                className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--ink-3)]"
              />
              <input
                data-testid="login-password"
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="any-password (demo)"
                className="glass-input w-full pl-9"
                autoComplete="current-password"
              />
            </div>
          </label>

          {error && (
            <p
              className="text-xs"
              style={{ color: "var(--ink-warn)" }}
              data-testid="login-error"
            >
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={busy}
            data-testid="login-submit"
            className="mt-2 w-full inline-flex items-center justify-center gap-2 py-3 text-sm uppercase tracking-widest font-mono"
            style={{
              borderRadius: 999,
              color: "var(--ink-1)",
              background:
                "linear-gradient(180deg, rgba(196,245,107,0.95), rgba(150,210,80,0.95))",
              boxShadow:
                "inset 0 1px 0 rgba(255,255,255,0.6), 0 8px 28px -8px rgba(196,245,107,0.55)",
              opacity: busy ? 0.7 : 1,
            }}
          >
            {busy ? "signing you in…" : "continue"} <ArrowRight size={14} />
          </button>

          <a
            href="/"
            className="text-center font-mono text-[10px] tracking-[0.3em] uppercase text-[var(--ink-3)] hover:text-[var(--ink-1)]"
            data-testid="login-skip"
          >
            skip for now →
          </a>
        </form>
      </main>
    </>
  );
}
