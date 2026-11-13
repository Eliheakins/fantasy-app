import { useEffect, useState } from "react";

const MINUTE_MS = 60_000;

/** The current time, refreshed every `intervalMs` so time-relative labels keep moving. */
export function useNow(intervalMs: number = MINUTE_MS): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), intervalMs);
    return () => window.clearInterval(id);
  }, [intervalMs]);
  return now;
}
