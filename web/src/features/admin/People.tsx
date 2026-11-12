import { useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { sendJson } from "@/api/envelope";
import type { AdminAccount, InviteCreated } from "@/api/types";
import { useEnvelopeQuery } from "@/api/useEnvelope";
import { ApiBoundary } from "@/components/ApiBoundary";
import { Field } from "@/components/Field";
import { type Column, ResponsiveTable } from "@/components/ResponsiveTable";
import { Button } from "@/components/ui/button";
import { InviteLink } from "./InviteLink";

const ACCOUNTS_URL = "/api/admin/accounts";

/** Who can sign in. Add an email to get a one-time link; a new link for someone who already has an
 * account replaces the old one and, once used, resets their password. */
export function People() {
  const queryClient = useQueryClient();
  const accounts = useEnvelopeQuery<AdminAccount[]>(ACCOUNTS_URL);
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<InviteCreated | null>(null);
  const [confirming, setConfirming] = useState<number | null>(null);

  const refreshList = () => queryClient.invalidateQueries({ queryKey: ["api", ACCOUNTS_URL] });

  async function invite(address: string) {
    setBusy(true);
    setError(null);
    const sent = await sendJson<InviteCreated>("/api/admin/invites", "POST", { email: address });
    setBusy(false);
    if (!sent.ok) {
      setError(sent.error.message);
      return;
    }
    setCreated(sent.data);
    setEmail("");
    await refreshList();
  }

  async function remove(account: AdminAccount) {
    setBusy(true);
    setError(null);
    const sent = await sendJson(`${ACCOUNTS_URL}/${account.id}`, "DELETE");
    setBusy(false);
    setConfirming(null);
    if (!sent.ok) {
      setError(sent.error.message);
      return;
    }
    setCreated((shown) => (shown?.email === account.email ? null : shown));
    await refreshList();
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    void invite(email.trim());
  }

  const columns: Column<AdminAccount>[] = [
    { label: "Email", role: "primary", render: (a) => a.email },
    { label: "Role", render: (a) => (a.is_admin ? "Admin" : "Member") },
    { label: "Status", render: (a) => (a.has_password ? "Active" : a.invite_pending ? "Invited, not joined yet" : "No link") },
    {
      label: "Actions",
      render: (a) =>
        a.is_admin ? (
          "—"
        ) : confirming === a.id ? (
          <span className="flex gap-2">
            <Button size="sm" onClick={() => void remove(a)} disabled={busy}>
              Confirm remove {a.email}
            </Button>
            <Button size="sm" variant="outline" onClick={() => setConfirming(null)}>
              Cancel
            </Button>
          </span>
        ) : (
          <span className="flex gap-2">
            <Button size="sm" variant="outline" onClick={() => void invite(a.email)} disabled={busy}>
              New link for {a.email}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setConfirming(a.id)} disabled={busy}>
              Remove {a.email}
            </Button>
          </span>
        ),
    },
  ];

  return (
    <div>
      <form onSubmit={handleSubmit} className="flex flex-col gap-2 sm:flex-row sm:items-end">
        <Field
          id="invite-email"
          label="Email to invite"
          wrapperClassName="flex-1"
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <Button type="submit" disabled={busy}>
          Create invite link
        </Button>
      </form>
      {error && (
        <p role="alert" className="mt-3 text-body text-ink">
          {error}
        </p>
      )}
      {created && <InviteLink email={created.email} path={created.path} validDays={created.valid_days} />}
      <div className="mt-6">
        <ApiBoundary state={accounts}>
          {(rows) => <ResponsiveTable caption="People with an account" columns={columns} rows={rows} rowKey={(a) => String(a.id)} />}
        </ApiBoundary>
      </div>
    </div>
  );
}
