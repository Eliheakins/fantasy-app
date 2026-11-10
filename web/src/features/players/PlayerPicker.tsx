import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useManifestQuery } from "@/stat/react/manifest";
import { getPlayers, searchPlayers } from "@/stat/lib/players";

const MIN_QUERY = 2;
const DEBOUNCE_MS = 250;

type Props = { onPick: (gsisId: string) => void; exclude: readonly string[] };

/** A search box for any player in the stat data; picking one calls onPick with his id. */
export function PlayerPicker({ onPick, exclude }: Props) {
  const [text, setText] = useState("");
  const [query, setQuery] = useState("");
  useEffect(() => {
    const t = window.setTimeout(() => setQuery(text.trim()), DEBOUNCE_MS);
    return () => window.clearTimeout(t);
  }, [text]);
  const manifest = useManifestQuery();
  const found = useQuery({
    queryKey: ["compare-search", manifest.data?.built_at ?? null, query],
    enabled: manifest.data !== undefined && query.length >= MIN_QUERY,
    queryFn: async () => searchPlayers(await getPlayers(manifest.data ?? null), query),
  });
  const options = (found.data ?? []).filter((p) => !exclude.includes(p.gsis_id));
  const searching = query.length >= MIN_QUERY;
  const status = !searching
    ? ""
    : found.isFetching
      ? "Searching…"
      : found.error
        ? ""
        : options.length === 0
          ? "No players match."
          : `${options.length} ${options.length === 1 ? "player" : "players"} found.`;
  return (
    <div className="space-y-1">
      <label className="block text-body font-semibold" htmlFor="compare-search">
        Add a player
      </label>
      <input
        id="compare-search"
        type="search"
        placeholder="Type at least two letters of a name"
        value={text}
        onChange={(e) => setText(e.target.value)}
        className="min-h-[44px] w-full max-w-sm rounded-full border border-panel-line bg-surface px-4 text-body"
      />
      <p role="status" className="text-caption text-muted">
        {status}
      </p>
      {found.error && <p className="text-body text-warning">The player search failed: {found.error.message}</p>}
      {options.length > 0 && (
        <ul className="max-w-sm">
          {options.map((p) => (
            <li key={p.gsis_id}>
              <button
                type="button"
                className="min-h-[44px] w-full px-3 text-left text-body hover:bg-panel"
                onClick={() => {
                  onPick(p.gsis_id);
                  setText("");
                  setQuery("");
                }}
              >
                {p.full_name} <span className="text-caption text-muted">{[p.position, p.team].filter(Boolean).join(" · ")}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
