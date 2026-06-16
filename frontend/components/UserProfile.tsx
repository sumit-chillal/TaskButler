"use client";

import { LogOut, User } from "lucide-react";
import type { UserProfile } from "../lib/types";

interface Props {
  user: UserProfile | null;
  onLogout?: () => void;
}

export const UserProfileChip: React.FC<Props> = ({ user, onLogout }) => {
  if (!user) {
    return (
      <a
        href="/login"
        data-testid="login-link"
        className="glass-soft inline-flex items-center gap-2 px-3 py-1.5 text-xs uppercase tracking-widest font-mono text-[var(--ink-2)] hover:text-[var(--ink-1)]"
        style={{ borderRadius: 999 }}
      >
        <User size={12} /> sign in
      </a>
    );
  }
  return (
    <div
      data-testid="user-profile-chip"
      className="glass-soft inline-flex items-center gap-3 pl-2 pr-1 py-1"
      style={{ borderRadius: 999 }}
    >
      <span
        className="w-7 h-7 rounded-full flex items-center justify-center font-display text-sm"
        style={{
          background:
            "linear-gradient(160deg, rgba(var(--tint-todo),0.25), rgba(var(--tint-flight),0.25))",
          color: "var(--ink-1)",
        }}
        aria-hidden
      >
        {user.name?.[0]?.toUpperCase() || "?"}
      </span>
      <span
        className="text-xs"
        style={{ color: "var(--ink-1)", maxWidth: 120 }}
      >
        {user.name}
      </span>
      <button
        data-testid="logout-btn"
        onClick={onLogout}
        aria-label="Sign out"
        className="w-7 h-7 rounded-full flex items-center justify-center text-[var(--ink-3)] hover:text-[var(--ink-warn)]"
      >
        <LogOut size={12} />
      </button>
    </div>
  );
};

export default UserProfileChip;
