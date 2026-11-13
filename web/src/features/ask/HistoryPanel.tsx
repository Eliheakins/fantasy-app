import { useState } from "react";

import type { FilterChipGroup } from "@/stat/config/queryBuilderOptions";
import { Link } from "react-router-dom";

import type { PageUrl } from "@/components/layout/navLinks";
import { Button } from "@/components/ui/button";
import { copyShared } from "@/lib/sharedParams";
import { getStatById } from "@/stat/config/statDictionary";
import { useFilterChipGroups } from "@/stat/react/filterChipGroups";
import { EMPTY_QUERY, serializeQuery } from "@/stat/lib/queryUrl";

import type { AskLogEntry, LoggedQuery } from "./askLog";
import { toEvalCases } from "./askLog";
import { clearLog, readLog } from "./askLogStore";

const PATH_LABELS: Record<AskLogEntry["path"], string> = {
  rules: "Built-in rules",
  model: "Local model",
  saved: "Your earlier correction",
  none: "No answer",
};

function describe(query: LoggedQuery, chipGroups: FilterChipGroup[]): string {
  const labels = new Map(chipGroups.flatMap((g) => g.options.map((o): [string, string] => [o.id, o.label])));
  const stats = query.stats.map((id) => getStatById(id)?.label ?? id).join(", ");
  const filters = query.filters.map((id) => labels.get(id) ?? id).join(", ") || "all seasons";
  const ranking = query.order && query.limit ? ` · ${query.order.direction === "desc" ? "top" : "bottom"} ${query.limit}` : "";
  const teams = `${query.teams.join(", ") || "every team"} ${query.side === "defense" ? "defense" : "offense"} · `;
  const players = query.players.length > 0 ? `${query.players.length} player${query.players.length === 1 ? "" : "s"} · ` : "";
  const who = query.subject === "teams" ? teams : players;
  return `${who}${stats} · ${filters} · ${query.granularity.replace("_", " ")}${ranking}`;
}

/** The Ask URL that shows an entry again, on the same league and team. */
const reopenSearch = (entry: AskLogEntry, current: URLSearchParams): string | null => {
  const { outcome } = entry;
  if (outcome.kind !== "answered" && outcome.kind !== "start_sit" && outcome.kind !== "trade") return null;
  const params =
    outcome.kind === "answered" ? serializeQuery({ ...EMPTY_QUERY, ...(entry.corrected ?? outcome.query) }) : new URLSearchParams();
  params.set("q", entry.question);
  copyShared(current, params);
  return params.toString();
};

function downloadJson(name: string, value: unknown): void {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  URL.revokeObjectURL(url);
}

/** Every Ask kept in this browser, with the fixes made to its answer. Nothing leaves the machine. */
export function HistoryPanel({ here, onReopen }: { here: PageUrl; onReopen: () => void }) {
  const current = new URLSearchParams(here.search);
  const chipGroups = useFilterChipGroups();
  const [entries, setEntries] = useState(readLog);
  const corrections = toEvalCases(entries);

  return (
    <section className="space-y-4" aria-label="Ask history">
      <p className="text-caption text-muted">
        Kept in this browser only (the newest 200). A fix you make to an answer is remembered for that question. Exported fixes join the
        eval set with <code>uv run python tests/stat/eval/promote.py</code>.
      </p>
      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={corrections.length === 0}
          onClick={() => downloadJson("ask-corrections.json", corrections)}
        >
          Export {corrections.length} correction{corrections.length === 1 ? "" : "s"} as eval cases
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={entries.length === 0}
          onClick={() => {
            clearLog();
            setEntries([]);
          }}
        >
          Clear history
        </Button>
      </div>

      {entries.length === 0 ? <p className="text-body text-muted">Nothing asked yet.</p> : null}
      <ul className="divide-y divide-line">
        {entries.map((entry) => {
          const search = reopenSearch(entry, current);
          return (
            <li key={entry.id} className="space-y-1 py-3 text-body">
              <p className="font-medium text-ink">
                {search ? (
                  <Link
                    to={{ pathname: "/ask", search }}
                    onClick={onReopen}
                    className="inline-flex min-h-11 items-center underline underline-offset-2 md:min-h-0"
                  >
                    {entry.question}
                  </Link>
                ) : (
                  entry.question
                )}
              </p>
              <p className="text-caption text-muted">
                {new Date(entry.at).toLocaleString()} · {PATH_LABELS[entry.path]}
              </p>
              {entry.outcome.kind === "answered" ? (
                <p className="text-caption text-ink">Answered: {describe(entry.outcome.query, chipGroups)}</p>
              ) : entry.outcome.kind === "start_sit" ? (
                <p className="text-caption text-ink">Start/sit: {entry.outcome.text}</p>
              ) : entry.outcome.kind === "trade" ? (
                <p className="text-caption text-ink">Trade: {entry.outcome.text}</p>
              ) : (
                <p className="text-caption text-warning">{entry.outcome.text}</p>
              )}
              {entry.corrected ? (
                <p className="text-caption font-medium text-focus">You changed it to: {describe(entry.corrected, chipGroups)}</p>
              ) : null}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
