import { useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Field } from "@/components/Field";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { redeemInvite } from "@/lib/session";

/** The server's minimum (fantasy/auth/passwords.py); checked here too so most mistakes need no round trip. */
const MIN_PASSWORD_LENGTH = 12;

/** What the invite link opens: choose a password, then you are signed in. The server says if the
 * link is wrong, used or expired. */
export default function RedeemInvite() {
  const { token = "" } = useParams();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [password, setPassword] = useState("");
  const [again, setAgain] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const field = useRef<HTMLInputElement>(null);

  useEffect(() => {
    document.title = "Choose a password · Fantasy";
  }, []);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const problem =
      password.length < MIN_PASSWORD_LENGTH
        ? `Use at least ${MIN_PASSWORD_LENGTH} characters.`
        : password !== again
          ? "The two passwords are not the same."
          : null;
    if (problem) {
      setError(problem);
      field.current?.focus();
      return;
    }
    setBusy(true);
    setError(null);
    const failure = await redeemInvite(queryClient, token, password);
    setBusy(false);
    if (failure) {
      setError(failure.message);
      return;
    }
    navigate("/", { replace: true });
  }

  return (
    <main className="mx-auto w-full max-w-sm px-4 py-10">
      <PageHeader title="Choose a password" subtitle={`At least ${MIN_PASSWORD_LENGTH} characters. A password manager makes this easy.`} />
      <form onSubmit={(e) => void handleSubmit(e)} className="flex flex-col gap-4">
        <Field
          id="invite-password"
          label="New password"
          ref={field}
          type="password"
          autoComplete="new-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <Field
          id="invite-again"
          label="Type it again"
          type="password"
          autoComplete="new-password"
          required
          value={again}
          onChange={(e) => setAgain(e.target.value)}
        />
        {error && (
          <p role="alert" className="text-body text-ink">
            {error}
          </p>
        )}
        <Button type="submit" disabled={busy}>
          {busy ? "Saving…" : "Save password and sign in"}
        </Button>
      </form>
      <p className="mt-6 text-caption text-muted">
        Already have a password?{" "}
        <Link to="/login" className="underline">
          Sign in
        </Link>
      </p>
    </main>
  );
}
