"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Trash2, Loader2, Sparkles, AlertTriangle } from "lucide-react";

type MemoryOverview = {
  user_id: string;
  preferences: Record<string, string>;
  interactions: Array<{
    id: string;
    content: string;
    role?: string;
    timestamp?: string;
    session_id?: string;
  }>;
  todos: Array<{
    id: string;
    task: string;
    done?: boolean;
    created?: string;
  }>;
  counts: { preferences: number; interactions: number; todos: number };
};

const PRETTY_KEY: Record<string, string> = {
  user_name: "Your name",
  home_address: "Home address",
  work_address: "Work address",
  preferred_airline: "Preferred airline",
  favorite_restaurant: "Favourite restaurant",
  favorite_cuisine: "Favourite cuisine",
};

function prettyKey(k: string) {
  return PRETTY_KEY[k] || k.replace(/_/g, " ");
}

function relTime(iso?: string) {
  if (!iso) return "";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "";
  const diff = Date.now() - t;
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  return `${d}d ago`;
}

function backendUrl(path: string) {
  const base = (process.env.REACT_APP_BACKEND_URL || "").replace(/\/$/, "");
  return base ? `${base}${path}` : path;
}

export default function MemoryPage() {
  const [userId, setUserId] = useState<string>("default");
  const [data, setData] = useState<MemoryOverview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [confirmingWipe, setConfirmingWipe] = useState(false);

  const totalRemembered = useMemo(() => {
    if (!data) return 0;
    return (
      data.counts.preferences + data.counts.interactions + data.counts.todos
    );
  }, [data]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        backendUrl(`/api/memory/me?user_id=${encodeURIComponent(userId)}`),
        { cache: "no-store" }
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setData((await res.json()) as MemoryOverview);
    } catch (e: any) {
      setError(e?.message || "failed to load memory");
    } finally {
      setLoading(false);
    }
  }, [userId]);

  useEffect(() => {
    load();
  }, [load]);

  const forgetPreference = async (key: string) => {
    setBusyKey(`pref:${key}`);
    try {
      await fetch(
        backendUrl(
          `/api/memory/preference?user_id=${encodeURIComponent(
            userId
          )}&key=${encodeURIComponent(key)}`
        ),
        { method: "DELETE" }
      );
      await load();
    } finally {
      setBusyKey(null);
    }
  };

  const forgetInteraction = async (id: string) => {
    setBusyKey(`int:${id}`);
    try {
      await fetch(
        backendUrl(
          `/api/memory/interaction?user_id=${encodeURIComponent(
            userId
          )}&id=${encodeURIComponent(id)}`
        ),
        { method: "DELETE" }
      );
      await load();
    } finally {
      setBusyKey(null);
    }
  };

  const forgetTodo = async (id: string) => {
    setBusyKey(`todo:${id}`);
    try {
      await fetch(
        backendUrl(
          `/api/memory/todo?user_id=${encodeURIComponent(
            userId
          )}&id=${encodeURIComponent(id)}`
        ),
        { method: "DELETE" }
      );
      await load();
    } finally {
      setBusyKey(null);
    }
  };

  const wipeAll = async () => {
    setBusyKey("wipe");
    try {
      await fetch(
        backendUrl(`/api/memory/wipe?user_id=${encodeURIComponent(userId)}`),
        { method: "POST" }
      );
      setConfirmingWipe(false);
      await load();
    } finally {
      setBusyKey(null);
    }
  };

  return (
    <main className="min-h-screen px-6 md:px-16 py-12" data-testid="memory-page">
      {/* Header */}
      <div className="flex items-center justify-between max-w-5xl mb-12">
        <Link
          href="/"
          className="inline-flex items-center gap-2 text-sm text-muted hover:text-ink transition-colors"
          data-testid="back-link"
        >
          <ArrowLeft size={14} /> back
        </Link>
        <p className="font-mono text-[10px] tracking-[0.3em] text-muted uppercase">
          / memory of you
        </p>
      </div>

      {/* Hero */}
      <section className="max-w-5xl mb-16 grid md:grid-cols-[1.4fr_1fr] gap-10 items-end">
        <div>
          <h1 className="text-5xl md:text-7xl leading-[0.95] font-light tracking-tight">
            What I
            <br />
            <span className="italic text-accent">remember</span> about you.
          </h1>
          <p className="mt-6 text-ink/70 max-w-xl text-base">
            Everything below is stored in a local vector database on this
            machine. You own it. Forget any single item, or wipe it all.
          </p>
        </div>
        <div className="border-l border-ink/15 pl-8 md:pl-10 py-2">
          <label className="block">
            <span className="font-mono text-[11px] tracking-widest uppercase text-muted">
              user&nbsp;id
            </span>
            <input
              data-testid="user-id-input"
              value={userId}
              onChange={(e) => setUserId(e.target.value || "default")}
              className="mt-2 w-full bg-transparent border-b border-ink/20 focus:border-accent focus:outline-none py-1 text-lg"
            />
          </label>
          <div className="mt-6 flex items-baseline gap-3">
            <span
              className="text-5xl font-light text-accent"
              data-testid="memory-total-count"
            >
              {totalRemembered}
            </span>
            <span className="text-sm text-muted">things remembered</span>
          </div>
        </div>
      </section>

      {/* Status */}
      {loading && (
        <p
          className="font-mono text-xs text-muted mb-8 inline-flex items-center gap-2"
          data-testid="memory-loading"
        >
          <Loader2 size={12} className="animate-spin" /> reading memory…
        </p>
      )}
      {error && (
        <p
          className="font-mono text-xs text-warn mb-8 inline-flex items-center gap-2"
          data-testid="memory-error"
        >
          <AlertTriangle size={12} /> {error}
        </p>
      )}

      {/* Preferences */}
      <Section
        title="Preferences"
        kicker="01"
        empty={data && Object.keys(data.preferences).length === 0}
        emptyText="No preferences captured yet. Tell TaskButler your name, your favourite cuisine, or which airline you prefer — it'll show up here."
        testId="preferences-section"
      >
        <ul className="divide-y divide-ink/10">
          {data &&
            Object.entries(data.preferences).map(([k, v]) => (
              <li
                key={k}
                data-testid={`preference-row-${k}`}
                className="grid grid-cols-[1.2fr_2fr_auto] items-center py-5 gap-4"
              >
                <span className="text-sm font-mono uppercase tracking-wider text-muted">
                  {prettyKey(k)}
                </span>
                <span className="text-xl text-ink">{v}</span>
                <button
                  data-testid={`forget-preference-${k}`}
                  onClick={() => forgetPreference(k)}
                  disabled={busyKey === `pref:${k}`}
                  className="inline-flex items-center gap-2 text-xs text-muted hover:text-warn px-3 py-2 rounded-full border border-ink/15 hover:border-warn/40 transition-colors disabled:opacity-50"
                >
                  {busyKey === `pref:${k}` ? (
                    <Loader2 size={12} className="animate-spin" />
                  ) : (
                    <Trash2 size={12} />
                  )}
                  Forget this
                </button>
              </li>
            ))}
        </ul>
      </Section>

      {/* Todos */}
      <Section
        title="Todos"
        kicker="02"
        empty={data && data.todos.length === 0}
        emptyText="No todos saved. Ask TaskButler to remember something for you."
        testId="todos-section"
      >
        <ul className="divide-y divide-ink/10">
          {data?.todos.map((t) => (
            <li
              key={t.id}
              data-testid={`todo-row-${t.id}`}
              className="grid grid-cols-[1fr_auto] items-center py-4 gap-4"
            >
              <div className="flex items-baseline gap-3">
                <span
                  className={
                    t.done
                      ? "text-base text-muted line-through"
                      : "text-base text-ink"
                  }
                >
                  {t.task}
                </span>
                <span className="font-mono text-[10px] text-muted">
                  {relTime(t.created)}
                </span>
              </div>
              <button
                data-testid={`forget-todo-${t.id}`}
                onClick={() => forgetTodo(t.id)}
                disabled={busyKey === `todo:${t.id}`}
                className="inline-flex items-center gap-2 text-xs text-muted hover:text-warn px-3 py-2 rounded-full border border-ink/15 hover:border-warn/40 transition-colors disabled:opacity-50"
              >
                {busyKey === `todo:${t.id}` ? (
                  <Loader2 size={12} className="animate-spin" />
                ) : (
                  <Trash2 size={12} />
                )}
                Forget
              </button>
            </li>
          ))}
        </ul>
      </Section>

      {/* Interactions */}
      <Section
        title="Past conversations"
        kicker="03"
        empty={data && data.interactions.length === 0}
        emptyText="No past turns recorded for this user yet."
        testId="interactions-section"
      >
        <ul className="space-y-3">
          {data?.interactions.map((it) => (
            <li
              key={it.id}
              data-testid={`interaction-row-${it.id}`}
              className="grid grid-cols-[auto_1fr_auto] items-start gap-4 p-4 bg-panel/60 rounded-2xl border border-ink/10"
            >
              <span
                className={
                  "font-mono text-[10px] uppercase tracking-widest pt-1 " +
                  (it.role === "user" ? "text-accent" : "text-muted")
                }
              >
                {it.role || "?"}
              </span>
              <p className="text-base text-ink/90 leading-relaxed">
                {it.content}
                <span className="block mt-1 font-mono text-[10px] text-muted">
                  {relTime(it.timestamp)}
                </span>
              </p>
              <button
                data-testid={`forget-interaction-${it.id}`}
                onClick={() => forgetInteraction(it.id)}
                disabled={busyKey === `int:${it.id}`}
                className="inline-flex items-center gap-2 text-xs text-muted hover:text-warn px-3 py-2 rounded-full border border-ink/10 hover:border-warn/40 transition-colors disabled:opacity-50"
              >
                {busyKey === `int:${it.id}` ? (
                  <Loader2 size={12} className="animate-spin" />
                ) : (
                  <Trash2 size={12} />
                )}
                Forget
              </button>
            </li>
          ))}
        </ul>
      </Section>

      {/* Wipe everything */}
      <section className="max-w-5xl mt-24 border-t border-ink/10 pt-10">
        <h2 className="text-2xl font-light flex items-center gap-3">
          <Sparkles size={18} className="text-accent" />
          Start fresh
        </h2>
        <p className="text-sm text-ink/60 mt-2 max-w-xl">
          Forget every preference, todo, and conversation about this user. This
          cannot be undone.
        </p>

        {!confirmingWipe ? (
          <button
            data-testid="wipe-button"
            onClick={() => setConfirmingWipe(true)}
            className="mt-6 inline-flex items-center gap-2 text-sm text-warn px-5 py-3 rounded-full border border-warn/40 hover:bg-warn/10 transition-colors"
          >
            <Trash2 size={14} /> Forget everything about {userId}
          </button>
        ) : (
          <div
            className="mt-6 inline-flex items-center gap-3 p-2 rounded-full border border-warn/40"
            data-testid="wipe-confirm-tray"
          >
            <span className="ml-3 text-sm text-warn font-mono">
              Are you sure?
            </span>
            <button
              data-testid="wipe-confirm-yes"
              onClick={wipeAll}
              disabled={busyKey === "wipe"}
              className="text-sm bg-warn text-bg px-4 py-2 rounded-full font-medium disabled:opacity-50 inline-flex items-center gap-2"
            >
              {busyKey === "wipe" && (
                <Loader2 size={12} className="animate-spin" />
              )}
              Yes, forget everything
            </button>
            <button
              data-testid="wipe-confirm-no"
              onClick={() => setConfirmingWipe(false)}
              className="text-sm text-muted hover:text-ink px-4 py-2 rounded-full"
            >
              cancel
            </button>
          </div>
        )}
      </section>

      <footer className="max-w-5xl mt-24 pb-8 text-xs font-mono text-muted">
        Stored locally via ChromaDB \u00b7 embeddings:&nbsp;
        all-MiniLM-L6-v2
      </footer>
    </main>
  );
}

function Section({
  title,
  kicker,
  empty,
  emptyText,
  testId,
  children,
}: {
  title: string;
  kicker: string;
  empty: boolean | null | undefined;
  emptyText: string;
  testId: string;
  children: React.ReactNode;
}) {
  return (
    <section className="max-w-5xl mb-16" data-testid={testId}>
      <div className="flex items-baseline gap-6 mb-6">
        <span className="font-mono text-xs tracking-[0.3em] text-muted">
          {kicker}
        </span>
        <h2 className="text-3xl font-light">{title}</h2>
      </div>
      {empty ? (
        <p className="text-sm text-muted/80 italic max-w-xl py-4 border-t border-ink/10">
          {emptyText}
        </p>
      ) : (
        children
      )}
    </section>
  );
}
