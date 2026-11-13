import { type FormEvent, useState } from "react";
import type { AdminAccount, InviteCreated } from "@/api/types";
import { apiKey, useEnvelopeMutation, useEnvelopeQuery } from "@/api/useEnvelope";
import { ApiBoundary } from "@/components/ApiBoundary";
import { Field } from "@/components/Field";
import { type Column, ResponsiveTable } from "@/components/ResponsiveTable";
import { Button } from "@/components/ui/button";
import { InviteLink } from "./InviteLink";

const ACCOUNTS = "/api/admin/accounts";
const ACCOUNTS_KEY = apiKey(ACCOUNTS);

/** Who can sign in. Add an email to get a one-time link; a new link for someone who already has an
 * account replaces the old one and, once used, resets their password. */
export function People() {
  const accounts = useEnvelopeQuery(ACCOUNTS);
  const [email, setEmail] = useState("");
  const [created, setCreated] = useState<InviteCreated | null>(null);
  const [confirming, setConfirming] = useState<number | null>(null);
  const inviting = useEnvelopeMutation("post", "/api/admin/invites", [ACCOUNTS_KEY]);
  const removing = useEnvelopeMutation("delete", "/api/admin/accounts/{account_id}", [ACCOUNTS_KEY]);
  const busy = inviting.isPending || removing.isPending;
  const error = (inviting.error ?? removing.error)?.message ?? null;

  function invite(address: string) {
    removing.reset();
    inviting.mutate(
      { body: { email: address } },
      {
        onSuccess: (data) => {
          setCreated(data);
          setEmail("");
        },
      },
    );
  }

  function remove(account: AdminAccount) {
    inviting.reset();
    removing.mutate(
      { params: { path: { account_id: account.id } } },
      {
        onSuccess: () => setCreated((shown) => (shown?.email === account.email ? null : shown)),
        onSettled: () => setConfirming(null),
      },
    );
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    invite(email.trim());
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
            <Button size="sm" onClick={() => remove(a)} disabled={busy}>
              Confirm remove {a.email}
            </Button>
            <Button size="sm" variant="outline" onClick={() => setConfirming(null)}>
              Cancel
            </Button>
          </span>
        ) : (
          <span className="flex gap-2">
            <Button size="sm" variant="outline" onClick={() => invite(a.email)} disabled={busy}>
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
