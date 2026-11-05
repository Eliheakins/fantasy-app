import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type { StatHealth, Status } from "@/api/types";
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

const STAT_HEALTH_REFETCH_MS = 5 * 60_000;

/** The stat app's health (plain JSON, not the envelope); null until it loads or if it fails. */
function useStatHealth(): StatHealth | null {
  const { data } = useQuery<StatHealth, Error>({
    queryKey: ["stat-health"],
    queryFn: async () => {
      const res = await fetch("/api/stat/health");
      if (!res.ok) throw new Error(`stat health ${res.status}`);
      return (await res.json()) as StatHealth;
    },
    refetchInterval: STAT_HEALTH_REFETCH_MS,
    retry: false,
  });
  return typeof data?.data_ready === "boolean" ? data : null;
}

const INNER = "mx-auto w-full max-w-[1200px] px-[var(--page-pad)]";

/** One amber line at every width with a details disclosure; stacked rows pushed each page's answer down. */
export function StatusBanner() {
  const state = useApi<Status>("/api/status");
  const [open, setOpen] = useState(false);
  const statHealth = useStatHealth();
  const messages = bannerMessages(state.kind === "ready" ? state.data : null, statHealth);
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
