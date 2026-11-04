import { useState } from "react";
import { Link } from "react-router-dom";

import { Button } from "@/shared/components/ui/button";
import { Card, CardContent, CardTitle } from "@/shared/components/ui/card";
import { getStatById } from "@/shared/config/statDictionary";
import { getFilterChipGroups } from "@/shared/lib/filterChipGroups";
import { serializeQuery } from "@/shared/lib/queryUrl";

import type { AskLogEntry, LoggedQuery } from "./askLog";
import { toEvalCases } from "./askLog";
import { clearLog, readLog } from "./askLogStore";

const PATH_LABELS: Record<AskLogEntry["path"], string> = {
  rules: "Built-in rules",
  model: "Local model",
  saved: "Your earlier correction",
  none: "No answer",
};

function describe(query: LoggedQuery): string {
  const labels = new Map(getFilterChipGroups().flatMap((g) => g.options.map((o): [string, string] => [o.id, o.label])));
  const stats = query.stats.map((id) => getStatById(id)?.label ?? id).join(", ");
  const filters = query.filters.map((id) => labels.get(id) ?? id).join(", ") || "all seasons";
  const ranking = query.order && query.limit ? ` · top ${query.limit}` : "";
  const who = query.players.length > 0 ? `${query.players.length} player${query.players.length === 1 ? "" : "s"} · ` : "";
  return `${who}${stats} · ${filters} · ${query.granularity.replace("_", " ")}${ranking}`;
}

const reopenSearch = (entry: AskLogEntry): string | null => {
  if (entry.outcome.kind !== "answered") {
    return null;
  }
  const query = entry.corrected ?? entry.outcome.query;
  const params = serializeQuery({ ...query, minPlays: 0 });
  params.set("q", entry.question);
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
export function HistoryPanel() {
  const [entries, setEntries] = useState(readLog);
  const corrections = toEvalCases(entries);

  return (
    <Card className="overflow-hidden border-border">
      <CardContent className="space-y-4 px-4 pb-6 pt-5 md:px-6">
        <div>
          <CardTitle className="text-lg text-ink">Ask history</CardTitle>
          <p className="mt-1 text-xs text-ink-muted">
            Kept in this browser only (the newest 200). A fix you make to an answer is remembered for that question.
            Exported fixes join the eval set with <code>uv run python backend/tests/eval/promote.py</code>.
          </p>
        </div>
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

        {entries.length === 0 ? <p className="text-sm text-ink-muted">Nothing asked yet.</p> : null}
        <ul className="space-y-3">
          {entries.map((entry) => {
            const search = reopenSearch(entry);
            return (
              <li key={entry.id} className="space-y-1 rounded-md border border-border bg-input/40 p-3 text-sm">
                <p className="font-medium text-ink">
                  {search ? (
                    <Link to={{ pathname: "/ask", search }} className="underline-offset-2 hover:underline">
                      {entry.question}
                    </Link>
                  ) : (
                    entry.question
                  )}
                </p>
                <p className="text-xs text-ink-muted">
                  {new Date(entry.at).toLocaleString()} · {PATH_LABELS[entry.path]}
                </p>
                {entry.outcome.kind === "answered" ? (
                  <p className="text-xs text-ink">Answered: {describe(entry.outcome.query)}</p>
                ) : (
                  <p className="text-xs text-warn-fg">{entry.outcome.text}</p>
                )}
                {entry.corrected ? (
                  <p className="text-xs font-medium text-accent">You changed it to: {describe(entry.corrected)}</p>
                ) : null}
              </li>
            );
          })}
        </ul>
      </CardContent>
    </Card>
  );
}
