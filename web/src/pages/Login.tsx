import { useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useRef, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { Field } from "@/components/Field";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { signIn, useSession } from "@/lib/session";

type LoginState = { from?: string; ended?: boolean } | null;

/** The page an unsigned visitor lands on. `from` is where they were going; it is only used if it is
 * a path on this site, so a crafted link cannot send a signed-in person elsewhere. */
export function safePath(from: string | undefined): string {
  return from && from.startsWith("/") && !from.startsWith("//") ? from : "/";
}

export default function Login() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const state = useLocation().state as LoginState;
  const session = useSession();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const passwordField = useRef<HTMLInputElement>(null);
  const destination = safePath(state?.from);

  useEffect(() => {
    document.title = "Sign in · Fantasy";
  }, []);

  if (session.kind === "signedIn") return <Navigate to={destination} replace />;

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const failure = await signIn(queryClient, email.trim(), password);
    setBusy(false);
    if (failure) {
      setError(failure.message);
      setPassword("");
      passwordField.current?.focus();
      return;
    }
    navigate(destination, { replace: true });
  }

  return (
    <main className="mx-auto w-full max-w-sm px-4 py-10">
      <PageHeader title="Sign in" subtitle="Use the email your invite was sent to." />
      {state?.ended && (
        <p role="status" className="mb-4 rounded-lg bg-panel p-3 text-body text-label">
          Your session ended. Sign in again to continue.
        </p>
      )}
      <form onSubmit={(e) => void handleSubmit(e)} className="flex flex-col gap-4">
        <Field
          id="login-email"
          label="Email"
          type="email"
          autoComplete="username"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <Field
          id="login-password"
          label="Password"
          ref={passwordField}
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        {error && (
          <p role="alert" className="text-body text-ink">
            {error}
          </p>
        )}
        <Button type="submit" disabled={busy}>
          {busy ? "Signing in…" : "Sign in"}
        </Button>
      </form>
      <p className="mt-6 text-caption text-muted">No account yet? Ask for an invite link.</p>
    </main>
  );
}
