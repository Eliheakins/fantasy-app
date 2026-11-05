import { useEffect, useState } from "react";

const MINUTE_MS = 60_000;

/** The current time, refreshed every minute: the one clock the strip and the to-dos share. */
export function useNow(): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), MINUTE_MS);
    return () => window.clearInterval(id);
  }, []);
  return now;
}
