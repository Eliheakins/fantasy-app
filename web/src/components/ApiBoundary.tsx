import { type ReactNode, useEffect, useState } from "react";
import { type ApiState, elapsedSeconds } from "@/api/envelope";

/** Plain muted line, for states that have no extra chrome. */
function Message({ children, role }: { children: ReactNode; role?: "status" | "alert" }) {
  return <p role={role} className="measure py-6 text-body text-muted">{children}</p>;
}

/** The no-data copy, with the command set in code. */
export function NoData({ message }: { message?: string }) {
  if (message) return <Message>{message}</Message>;
  return (
    <Message>
      No data yet. Run <code>make refresh</code>, then reload this page.
    </Message>
  );
}

/** Reserves room so the page does not jump when data arrives. */
function Loading() {
  return (
    <div role="status" aria-busy="true" className="min-h-[160px] space-y-3 py-4">
      <span className="sr-only">Loading…</span>
      <div aria-hidden className="h-5 w-1/3 animate-pulse rounded bg-surface" />
      <div aria-hidden className="h-24 animate-pulse rounded bg-surface" />
      <div aria-hidden className="h-5 w-1/2 animate-pulse rounded bg-surface" />
    </div>
  );
}

/** Looks unlike loading: amber edge, plain sentence, the cause in small type, and a way to try again. */
export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="my-4 border-l-4 border-warning bg-surface px-4 py-3">
      <p className="text-body font-semibold">This did not load.</p>
      <p className="text-caption text-muted">{message}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-2 min-h-[44px] rounded border border-border bg-page px-4 text-body text-text"
        >
          Try again
        </button>
      )}
    </div>
  );
}

function Running({ startedAt }: { startedAt: string | null }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);
  const seconds = elapsedSeconds(startedAt, now);
  return (
    <Message role="status">
      Working{seconds === null ? "" : `, ${seconds} s so far`}. This page updates when it finishes.
    </Message>
  );
}

type ApiBoundaryProps<T> = { state: ApiState<T>; children: (data: T) => ReactNode };

/** Renders loading, running (with elapsed time), no-data and error states; children get the data. */
export function ApiBoundary<T>({ state, children }: ApiBoundaryProps<T>) {
  switch (state.kind) {
    case "loading":
      return <Loading />;
    case "running":
      return <Running startedAt={state.startedAt} />;
    case "no_data":
      return <NoData message={state.message} />;
    case "error":
      return <ErrorState message={state.error.message} onRetry={state.retry} />;
    case "ready":
      return <>{children(state.data)}</>;
  }
}
