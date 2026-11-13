import { type QueryClient, useQuery } from "@tanstack/react-query";
import { type ApiError, fetchEnvelope, type Sent, sendJson } from "@/api/envelope";
import type { Envelope, Me } from "@/api/types";

/** Who is signed in. The server decides: `/api/auth/me` answers 401 when nobody is, and on a
 * laptop with no accounts it answers as a local admin, so the same gate works in both places. */

const ME_URL = "/api/auth/me";
/** What the server calls the one person on a run with no accounts (`fantasy/auth/routes.py`). */
export const LOCAL_EMAIL = "local";
/** The key `useEnvelopeQuery` would use for this url, so the session is one cache entry. */
export const ME_KEY = ["api", ME_URL] as const;
const ACCOUNT_KEY = "fantasy.account";
const OWN_KEY_PREFIXES = ["fantasy.", "bridge."];
const SESSION_STALE_MS = 5 * 60 * 1000;
const NO_ACCOUNT: Me = { email: "", is_admin: false, sleeper_user_id: null };
const SIGNED_OUT: Envelope<Me> = {
  status: "error",
  data: null,
  error: { code: "unauthorized", message: "Signed out" },
  started_at: null,
};

export type Session =
  { kind: "loading" } | { kind: "signedOut" } | { kind: "signedIn"; me: Me } | { kind: "error"; message: string; retry: () => void };

/** Saved league, searches, Ask history and cache belong to one person: drop them when another account shows up. */
function scopeStorageTo(envelope: Envelope<Me>): void {
  const email = envelope.status === "ok" ? envelope.data?.email : undefined;
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

async function fetchMe(): Promise<Envelope<Me>> {
  const envelope = await fetchEnvelope("get", ME_URL);
  scopeStorageTo(envelope);
  return envelope;
}

export function useSession(): Session {
  const query = useQuery<Envelope<Me>, Error>({
    queryKey: ME_KEY,
    queryFn: fetchMe,
    retry: false,
    staleTime: SESSION_STALE_MS,
  });
  const retry = () => void query.refetch();
  if (query.error) return { kind: "error", message: query.error.message, retry };
  const envelope = query.data;
  if (!envelope) return { kind: "loading" };
  if (envelope.status === "ok") return { kind: "signedIn", me: envelope.data ?? NO_ACCOUNT };
  if (envelope.error?.code === "unauthorized") return { kind: "signedOut" };
  return { kind: "error", message: envelope.error?.message ?? "Could not check your sign-in.", retry };
}

/** Another person's cached pages must never show for the next person: drop everything, keep the session. */
function startSession(queryClient: QueryClient, envelope: Envelope<Me>): void {
  scopeStorageTo(envelope);
  queryClient.clear();
  queryClient.setQueryData(ME_KEY, envelope);
}

async function authenticate(queryClient: QueryClient, sending: Promise<Sent<Me>>): Promise<ApiError | null> {
  const sent = await sending;
  if (!sent.ok) return sent.error;
  startSession(queryClient, { status: "ok", data: sent.data, error: null, started_at: null });
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
  startSession(queryClient, SIGNED_OUT);
}
