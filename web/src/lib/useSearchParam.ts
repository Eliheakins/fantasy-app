import { useCallback } from "react";
import { useSearchParams } from "react-router-dom";

/** One URL search param and its setter: a string sets it, null removes it; the other params stay and history is replaced. */
export function useSearchParam(key: string): [string | null, (next: string | null) => void] {
  const [params, setParams] = useSearchParams();
  const set = useCallback(
    (next: string | null) =>
      setParams(
        (prev) => {
          const out = new URLSearchParams(prev);
          if (next === null) out.delete(key);
          else out.set(key, next);
          return out;
        },
        { replace: true },
      ),
    [key, setParams],
  );
  return [params.get(key), set];
}
