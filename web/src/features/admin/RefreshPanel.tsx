import type { AdminRun, RefreshAdmin } from "@/api/types";
import { apiKey, useEnvelopeMutation, useEnvelopeQuery } from "@/api/useEnvelope";
import { ApiBoundary } from "@/components/ApiBoundary";
import { type Column, ResponsiveTable } from "@/components/ResponsiveTable";
import { Button } from "@/components/ui/button";

const REFRESH_URL = "/api/admin/refresh";
const POLL_MS = 5000;

const columns: Column<AdminRun>[] = [
  { label: "Run", role: "primary", render: (r) => r.run_id },
  { label: "Finished", render: (r) => new Date(r.finished_at).toLocaleString() },
  { label: "Stages", numeric: true, render: (r) => r.stages },
  { label: "Failed", numeric: true, render: (r) => r.failed },
  { label: "Seconds", numeric: true, render: (r) => r.seconds.toFixed(0) },
];

function describe(data: RefreshAdmin): string {
  if (data.state === "running") return "A refresh is running.";
  if (data.state === "queued") {
    return `A refresh is waiting to start (${data.queued} ${data.queued === 1 ? "request" : "requests"}).`;
  }
  return "No refresh is waiting.";
}

/** The data refresh: what it is doing, how the last runs went, and a button to start one now. */
export function RefreshPanel() {
  const overview = useEnvelopeQuery(REFRESH_URL, {}, POLL_MS);
  const refresh = useEnvelopeMutation("post", REFRESH_URL, [apiKey(REFRESH_URL)]);
  const error = refresh.error?.message ?? null;

  return (
    <ApiBoundary state={overview}>
      {(data) => (
        <div>
          <p role="status" className="text-body text-ink">
            {describe(data)}
          </p>
          {data.last_finished_at && (
            <p className="mt-1 text-caption text-muted">
              Last run finished {new Date(data.last_finished_at).toLocaleString()}.{" "}
              {data.last_run_failed ? "At least one stage failed or was skipped." : "Every stage succeeded."}
            </p>
          )}
          <Button className="mt-3" onClick={() => refresh.mutate({})} disabled={refresh.isPending || data.state !== "idle"}>
            Refresh now
          </Button>
          {error && (
            <p role="alert" className="mt-3 text-body text-ink">
              {error}
            </p>
          )}
          {data.runs.length > 0 && (
            <div className="mt-6">
              <ResponsiveTable caption="Recent refresh runs" columns={columns} rows={data.runs} rowKey={(r) => r.run_id} />
            </div>
          )}
        </div>
      )}
    </ApiBoundary>
  );
}
