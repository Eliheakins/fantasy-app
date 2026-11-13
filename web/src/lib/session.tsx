import type { QueryClient } from "@tanstack/react-query";
import { useSyncExternalStore } from "react";
import { type ApiError, fetchEnvelope, type Sent, sendJson } from "@/api/envelope";
import type { Envelope, Me } from "@/api/types";

/** Who is signed in. The server decides: `/api/auth/me` answers 401 when nobody is, and on a
 * laptop with no accounts it answers as a local admin, so the same gate works in both places.
 * The session is a small store of its own, not a react-query entry (the starter's "Why auth uses fetch"): sign-in,
 * sign-out and the check are one-off flows, and clearing the data cache must never touch who is signed in. */

const ME_URL = "/api/auth/me";
/** What the server calls the one person on a run with no accounts (`fantasy/auth/routes.py`). */
export const LOCAL_EMAIL = "local";
const ACCOUNT_KEY = "fantasy.account";
const OWN_KEY_PREFIXES = ["fantasy.", "bridge."];
const SESSION_STALE_MS = 5 * 60 * 1000;
const NO_ACCOUNT: Me = { email: "", is_admin: false, sleeper_user_id: null };

export type Session =
  { kind: "loading" } | { kind: "signedOut" } | { kind: "signedIn"; me: Me } | { kind: "error"; message: string; retry: () => void };

/** Saved league, searches, Ask history and cache belong to one person: drop them when another account shows up. */
function scopeStorageTo(email: string): void {
  if (!email) return;
  try {
    const storage = window.localStorage;
    const stored = storage.getItem(ACCOUNT_KEY);
    if (stored === email) return;
    // No account stored yet (a browser from before scoping): adopt it rather than wipe its keys.
    if (stored === null) {
      storage.setItem(ACCOUNT_KEY, email);
      return;
    }
    const stale = Array.from({ length: storage.length }, (_, i) => storage.key(i) ?? "").filter((key) =>
      OWN_KEY_PREFIXES.some((prefix) => key.startsWith(prefix)),
    );
    for (const key of stale) storage.removeItem(key);
    storage.setItem(ACCOUNT_KEY, email);
  } catch {
    // Storage can be blocked; there is then nothing saved to leak.
  }
}

let session: Session = { kind: "loading" };
/** When the last answer came, or null before the first; a check older than SESSION_STALE_MS runs again on return. */
let checkedAt: number | null = null;
let checking: Promise<void> | null = null;
/** Bumped by every sign-in, sign-out and reset, so a check that was already in flight cannot undo them. */
let generation = 0;
const listeners = new Set<() => void>();

function publish(next: Session): void {
  session = next;
  checkedAt = Date.now();
  for (const listener of listeners) listener();
}

function fromEnvelope(envelope: Envelope<Me>): Session {
  if (envelope.status === "ok") return { kind: "signedIn", me: envelope.data ?? NO_ACCOUNT };
  if (envelope.error?.code === "unauthorized") return { kind: "signedOut" };
  return { kind: "error", message: envelope.error?.message ?? "Could not check your sign-in.", retry: () => void checkSession() };
}

function signedInAs(next: Session): Session {
  if (next.kind === "signedIn") scopeStorageTo(next.me.email);
  return next;
}

/** Ask the server who is signed in (one request at a time); the screen keeps what it shows until the answer.
 * RequireSession calls it when a request comes back unauthorized (`UNAUTHORIZED_EVENT`). */
export function checkSession(): Promise<void> {
  if (checking) return checking;
  const started = generation;
  const run = fetchEnvelope("get", ME_URL)
    .then(
      (envelope) => {
        if (started === generation) publish(signedInAs(fromEnvelope(envelope)));
      },
      (err: unknown) => {
        const message = err instanceof Error ? err.message : String(err);
        if (started === generation) publish({ kind: "error", message, retry: () => void checkSession() });
      },
    )
    .finally(() => {
      if (checking === run) checking = null;
    });
  checking = run;
  return run;
}

const isStale = (): boolean => checkedAt === null || Date.now() - checkedAt > SESSION_STALE_MS;

function onVisible(): void {
  if (document.visibilityState !== "hidden" && isStale()) void checkSession();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  if (listeners.size === 1) document.addEventListener("visibilitychange", onVisible);
  if (isStale()) void checkSession();
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0) document.removeEventListener("visibilitychange", onVisible);
  };
}

export function useSession(): Session {
  return useSyncExternalStore(subscribe, () => session);
}

/** Drops any check in flight, so its answer cannot overwrite what comes next. */
function forgetCheck(): void {
  generation += 1;
  checking = null;
}

/** Back to "nobody checked yet", for tests (`test/setup.ts`): each starts with no session. */
export function resetSession(): void {
  forgetCheck();
  session = { kind: "loading" };
  checkedAt = null;
}

/** Another person's cached pages must never show for the next person: drop everything, then set the session. */
function startSession(queryClient: QueryClient, next: Session): void {
  forgetCheck();
  queryClient.clear();
  publish(signedInAs(next));
}

async function authenticate(queryClient: QueryClient, sending: Promise<Sent<Me>>): Promise<ApiError | null> {
  const sent = await sending;
  if (!sent.ok) return sent.error;
  startSession(queryClient, { kind: "signedIn", me: sent.data });
  return null;
}

/** Null on success; otherwise the message to show. */
export const signIn = (queryClient: QueryClient, email: string, password: string) =>
  authenticate(queryClient, sendJson("post", "/api/auth/login", { body: { email, password } }));

/** Sets the password from an invite link and signs in. Null on success. */
export const redeemInvite = (queryClient: QueryClient, token: string, password: string) =>
  authenticate(queryClient, sendJson("post", "/api/auth/redeem", { body: { token, password } }));

export async function signOut(queryClient: QueryClient, everywhere = false): Promise<void> {
  await sendJson("post", everywhere ? "/api/auth/logout-everywhere" : "/api/auth/logout");
  startSession(queryClient, { kind: "signedOut" });
}
