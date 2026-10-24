import { type ReactNode, useEffect, useState } from "react";
import { type ApiState, elapsedSeconds } from "@/api/envelope";

function Message({ children }: { children: ReactNode }) {
  return <p className="py-6 text-body text-muted">{children}</p>;
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

function Running({ startedAt }: { startedAt: string | null }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);
  const seconds = elapsedSeconds(startedAt, now);
  return (
    <Message>
      <span role="status">
        Working{seconds === null ? "" : `, ${seconds} s so far`}. This page updates when it finishes.
      </span>
    </Message>
  );
}

type ApiBoundaryProps<T> = { state: ApiState<T>; children: (data: T) => ReactNode };

/** Renders loading, running (with elapsed time), no-data and error states; children get the data. */
export function ApiBoundary<T>({ state, children }: ApiBoundaryProps<T>) {
  switch (state.kind) {
    case "loading":
      return <Message>Loading…</Message>;
    case "running":
      return <Running startedAt={state.startedAt} />;
    case "no_data":
      return <NoData />;
    case "error":
      return <Message>Something went wrong: {state.error.message}</Message>;
    case "ready":
      return <>{children(state.data)}</>;
  }
}
