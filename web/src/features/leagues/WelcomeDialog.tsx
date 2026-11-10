import { X } from "lucide-react";
import { Dialog } from "radix-ui";
import { useState } from "react";
import type { MyLeague } from "@/api/types";
import { useEnvelopeQuery } from "@/api/useEnvelope";
import { Button } from "@/components/ui/button";
import { useLeague } from "@/lib/league";
import { AddLeague } from "./AddLeague";

/** On a new account's first visit (it can see no league and has added none), ask for the Sleeper
 * username and the leagues and teams, instead of leaving the person on empty pages. It stays open
 * while they add, and once closed the no-leagues banner still points to My leagues. */
export function WelcomeDialog() {
  const { leagues } = useLeague();
  const mine = useEnvelopeQuery<MyLeague[]>("/api/me/leagues"); // an error (no account, login off) means no dialog
  const [username, setUsername] = useState("");
  const [wasNew, setWasNew] = useState(false);
  const [closed, setClosed] = useState(false);
  const isNew = leagues.kind === "ready" && leagues.data.length === 0 && mine.kind === "ready" && mine.data.length === 0;
  if (isNew && !wasNew) setWasNew(true); // remember it, so adding a league does not snap the dialog shut

  return (
    <Dialog.Root open={wasNew && !closed} onOpenChange={(open) => setClosed(!open)}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-page/70" />
        <Dialog.Content className="fixed inset-x-4 top-[10vh] z-50 mx-auto flex max-h-[80vh] max-w-xl flex-col gap-3 overflow-y-auto rounded-2xl border border-line bg-surface p-5 outline-hidden">
          <div className="flex items-start justify-between gap-2">
            <Dialog.Title className="text-heading font-semibold text-ink">Welcome. Add your Sleeper leagues</Dialog.Title>
            <Dialog.Close aria-label="Close" className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-ink">
              <X size={20} aria-hidden />
            </Dialog.Close>
          </div>
          <Dialog.Description className="text-body text-muted">
            Enter your Sleeper username, then add each league and pick which team in it is yours. You can add up to 2, and change them later under My leagues.
          </Dialog.Description>
          <AddLeague username={username} onUsername={setUsername} />
          <Dialog.Close asChild>
            <Button variant="outline" className="self-end">
              Done
            </Button>
          </Dialog.Close>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
