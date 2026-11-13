import { useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { Field } from "@/components/Field";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { z } from "zod";
import { redeemInvite } from "@/lib/session";

/** The server's minimum (fantasy/auth/passwords.py); checked here too so most mistakes need no round trip. */
const MIN_PASSWORD_LENGTH = 12;

const passwordForm = z
  .object({
    password: z.string().min(MIN_PASSWORD_LENGTH, `Use at least ${MIN_PASSWORD_LENGTH} characters.`),
    again: z.string(),
  })
  .refine((form) => form.password === form.again, { message: "The two passwords are not the same.", path: ["again"] });

type FieldName = keyof z.infer<typeof passwordForm>;
type FieldError = { field: FieldName; message: string };

/** The first problem only, on the field it belongs to (the length before the match), or null. */
function firstProblem(form: { password: string; again: string }): FieldError | null {
  const issue = passwordForm.safeParse(form).error?.issues[0];
  return issue ? { field: issue.path[0] === "again" ? "again" : "password", message: issue.message } : null;
}

/** What the invite link opens: choose a password, then you are signed in. The server says if the
 * link is wrong, used or expired. */
export default function RedeemInvite() {
  const { token = "" } = useParams();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [password, setPassword] = useState("");
  const [again, setAgain] = useState("");
  const [fieldError, setFieldError] = useState<FieldError | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const fields = { password: useRef<HTMLInputElement>(null), again: useRef<HTMLInputElement>(null) };

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const problem = firstProblem({ password, again });
    setFieldError(problem);
    if (problem) {
      setError(null);
      fields[problem.field].current?.focus();
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
          ref={fields.password}
          error={fieldError?.field === "password" ? fieldError.message : null}
          type="password"
          autoComplete="new-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <Field
          id="invite-again"
          label="Type it again"
          ref={fields.again}
          error={fieldError?.field === "again" ? fieldError.message : null}
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
