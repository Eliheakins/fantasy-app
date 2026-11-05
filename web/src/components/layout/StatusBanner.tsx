import { useState } from "react";
import type { Status } from "@/api/types";
import { useApi } from "@/hooks/useApi";
import { bannerMessages } from "@/lib/status";

function WithCode({ text }: { text: string }) {
  const [before, after] = text.split("`make refresh`");
  return (
    <>
      {before}
      <code>make refresh</code>
      {after}
    </>
  );
}

const INNER = "mx-auto w-full max-w-[1200px] px-[var(--page-pad)]";

/** One amber line at every width with a details disclosure; stacked rows pushed each page's answer down. */
export function StatusBanner() {
  const state = useApi<Status>("/api/status");
  const [open, setOpen] = useState(false);
  const messages = state.kind === "ready" ? bannerMessages(state.data) : [];
  const label = `${messages.length} data ${messages.length === 1 ? "notice" : "notices"}`;
  return (
    <div aria-live="polite" role="status">
      {messages.length > 0 && (
        <div className="border-b border-warning-edge bg-warning-bg text-body text-warning">
          <div className={`${INNER} flex min-h-[40px] items-center justify-between gap-3`}>
            <p>
              <span className="font-medium">{label}</span>
              <span className="hidden sm:inline">. Run <code>make refresh</code>.</span>
            </p>
            <button
              type="button"
              aria-expanded={open}
              aria-controls="data-notices"
              onClick={() => setOpen((o) => !o)}
              className="-my-1 inline-flex min-h-[44px] items-center gap-1 font-medium underline underline-offset-2"
            >
              {open ? "Hide details" : "Details"}
              <span aria-hidden>{open ? "▲" : "▼"}</span>
            </button>
          </div>
          {open && (
            <ul id="data-notices" aria-live="off" className={`${INNER} list-disc space-y-1 pb-3 pl-[calc(var(--page-pad)+1rem)]`}>
              {messages.map((m) => <li key={m}><WithCode text={m} /></li>)}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
