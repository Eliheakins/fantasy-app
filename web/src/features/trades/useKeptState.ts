import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

/**
 * Local state that is also written to the query cache, so it survives leaving and returning to the
 * page. `key` is read once: remount (React `key`) when it changes, e.g. per league.
 */
export function useKeptState<T>(key: readonly unknown[], initial: T): [T, (next: T) => void] {
  const client = useQueryClient();
  const cacheKey = ["kept", ...key];
  const [value, setValue] = useState<T>(() => {
    client.setQueryDefaults(["kept"], { gcTime: Infinity }); // once on mount: no observers, so the default would evict it
    return client.getQueryData<T>(cacheKey) ?? initial;
  });
  return [
    value,
    (next: T) => {
      setValue(next);
      client.setQueryData<T>(cacheKey, next);
    },
  ];
}
