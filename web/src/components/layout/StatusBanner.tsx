import { useState } from "react";
import type { Status } from "@/api/types";
import { useApi } from "@/hooks/useApi";
import { useMinWidth } from "@/hooks/useMediaQuery";
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

const ROW = "border-b border-line bg-warning-bg text-body text-warning";
const INNER = "mx-auto w-full max-w-[1200px] px-[var(--page-pad)]";

/** Phones get one line with a disclosure; three tall amber rows would push the page's answer below the fold. */
function PhoneNotices({ messages }: { messages: string[] }) {
  const [open, setOpen] = useState(false);
  const label = `${messages.length} data ${messages.length === 1 ? "notice" : "notices"}`;
  return (
    <div className={ROW}>
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className={`${INNER} flex min-h-[44px] items-center justify-between text-left font-medium`}
      >
        <span>{label}</span>
        <span aria-hidden>{open ? "Hide ▲" : "Show ▼"}</span>
      </button>
      {open && (
        <ul className={`${INNER} space-y-2 pb-2`}>
          {messages.map((m) => <li key={m}><WithCode text={m} /></li>)}
        </ul>
      )}
    </div>
  );
}

/** Amber notices for stale data and skipped layers. The live region stays mounted so changes are announced. */
export function StatusBanner() {
  const state = useApi<Status>("/api/status");
  const wide = useMinWidth("md");
  const messages = state.kind === "ready" ? bannerMessages(state.data) : [];
  return (
    <div aria-live="polite" role="status">
      {messages.length > 0 && !wide && <PhoneNotices messages={messages} />}
      {wide && messages.map((m) => (
        <div key={m} className={ROW}>
          <p className={`${INNER} py-2`}>
            <WithCode text={m} />
          </p>
        </div>
      ))}
    </div>
  );
}
