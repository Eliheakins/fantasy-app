import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

type Props = { email: string; path: string; validDays: number };

type CopyState = "idle" | "copied" | "failed";

/** The one-time link for an invited person. It is shown right after it is made and never again (the
 * server keeps only a hash), so the page says so and makes copying it easy. */
export function InviteLink({ email, path, validDays }: Props) {
  const url = `${window.location.origin}${path}`;
  const field = useRef<HTMLInputElement>(null);
  const [copy, setCopy] = useState<CopyState>("idle");

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(url);
      setCopy("copied");
    } catch {
      field.current?.select(); // no clipboard access (plain http, an old browser): leave it selected
      setCopy("failed");
    }
  }

  return (
    <div className="mt-4 rounded-lg border border-panel-line bg-panel p-4">
      <p className="text-body font-semibold text-ink">Link for {email}</p>
      <p className="mt-1 text-caption text-muted">
        Valid for {validDays} days and works once. It is shown only now: send it to them yourself.
      </p>
      <div className="mt-3 flex flex-col gap-2 sm:flex-row">
        <Input ref={field} readOnly aria-label="Invite link" value={url} onFocus={(e) => e.currentTarget.select()} />
        <Button onClick={() => void handleCopy()} className="shrink-0">
          Copy link
        </Button>
      </div>
      <p role="status" className="mt-2 min-h-5 text-caption text-label">
        {copy === "copied" && "Copied."}
        {copy === "failed" && "Could not copy automatically. The link is selected: copy it by hand."}
      </p>
    </div>
  );
}
