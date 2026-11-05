import { useRef } from "react";

/** While `hold` is true (a refetch is under way), keep returning the last value shown in the same `scope`, so a number the user has open does not unmount. */
export function useHeld<T>(value: T, hold: boolean, scope: string): T {
  const kept = useRef({ scope, value });
  if (!hold || kept.current.scope !== scope) kept.current = { scope, value };
  return kept.current.value;
}
