/**
 * Authentication helpers for TaskButler.
 *
 * NOTE: Only the user *profile* (name, email) is persisted to localStorage.
 * The JWT auth token returned by /auth/login is intentionally NOT stored on
 * disk — it lives only in memory for the current tab session. This keeps the
 * surface area of an XSS attack to a minimum (no long-lived token can be
 * exfiltrated from localStorage). For server-side session continuity the
 * backend should re-issue tokens via httpOnly cookies; that work is tracked
 * separately in the backlog.
 */

import type { UserProfile } from "./types";

const STORAGE_KEY = "taskbutler_user";

/** Read the stored user profile (if any). */
export function getStoredUser(): UserProfile | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as UserProfile;
  } catch (e) {
    console.warn("[auth] Failed to read stored user profile:", e);
    return null;
  }
}

/** Persist the user profile to localStorage. */
export function setStoredUser(profile: UserProfile): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(profile));
  } catch (e) {
    console.warn("[auth] Failed to persist user profile:", e);
  }
}

/** Remove the stored profile (logout). */
export function clearStoredUser(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch (e) {
    console.warn("[auth] Failed to clear stored user profile:", e);
  }
}

/** Dispatch a login event that the rest of the app listens for. */
export function dispatchLogin(profile: UserProfile): void {
  window.dispatchEvent(
    new CustomEvent("taskbutler:login", { detail: profile })
  );
}

/** Dispatch a logout event. */
export function dispatchLogout(): void {
  clearStoredUser();
  window.dispatchEvent(new CustomEvent("taskbutler:logout"));
}
