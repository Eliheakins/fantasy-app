import { useCallback, useSyncExternalStore } from "react";

/** Tailwind's min-width breakpoints, so JS and CSS agree. */
export const BREAKPOINTS = { md: 768, lg: 1024, xl: 1280 } as const;
export type Breakpoint = keyof typeof BREAKPOINTS;

const hasMatchMedia = () => typeof window.matchMedia === "function";

/** True when the viewport is at least the breakpoint wide. Without matchMedia (tests) it reports wide. */
export function useMinWidth(breakpoint: Breakpoint): boolean {
  const query = `(min-width: ${BREAKPOINTS[breakpoint]}px)`;
  const subscribe = useCallback(
    (notify: () => void) => {
      if (!hasMatchMedia()) return () => {};
      const mql = window.matchMedia(query);
      mql.addEventListener("change", notify);
      return () => mql.removeEventListener("change", notify);
    },
    [query],
  );
  return useSyncExternalStore(
    subscribe,
    () => (hasMatchMedia() ? window.matchMedia(query).matches : true),
    () => true,
  );
}
