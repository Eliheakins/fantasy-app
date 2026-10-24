import { Fragment } from "react";
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

/** Amber notices for stale data and skipped layers. The live region stays mounted so changes are announced. */
export function StatusBanner() {
  const state = useApi<Status>("/api/status");
  const messages = state.kind === "ready" ? bannerMessages(state.data) : [];
  return (
    <div aria-live="polite" role="status">
      {messages.map((m) => (
        <Fragment key={m}>
          <p className="border-b border-border bg-warning-bg px-4 py-2 text-body text-warning">
            <WithCode text={m} />
          </p>
        </Fragment>
      ))}
    </div>
  );
}
