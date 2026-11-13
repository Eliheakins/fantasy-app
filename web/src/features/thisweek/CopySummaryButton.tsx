import { useEffect, useRef, useState } from "react";
import { isPending } from "@/api/envelope";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { phaseOf } from "@/features/effects/phase";
import { copyText } from "@/lib/clipboard";
import type { DigestData } from "@/lib/digestTypes";
import { useAllLeagues, useEachLeague } from "@/lib/league";
import { summaryText, type SummaryLeague } from "./summary";
import type { Todo } from "./todos";
import { leagueName } from "./weekLogic";

type CopyState = "idle" | "copied" | "failed";

/** Copies a short plain-text summary of both leagues. The text is built before the click so the copy runs inside the click. */
export function CopySummaryButton({ todos, pending }: { todos: readonly Todo[]; pending: boolean }) {
  const leagues = useAllLeagues();
  const list = leagues.kind === "ready" ? leagues.data : [];
  const digests = useEachLeague<DigestData>(
    list.map((l) => l.league_key),
    "digest",
  );
  const rows: SummaryLeague[] = list.map((l, i) => {
    const d = digests[i];
    const data = d?.kind === "ready" ? d.data : null;
    const odds = data?.odds_change ?? [];
    return {
      name: leagueName(l),
      lastWeek: data?.last_week ?? null,
      odds: odds.find((o) => o.is_me) ?? null,
      phase: phaseOf(l, odds),
      failed: d?.kind === "error",
    };
  });
  const text = summaryText(rows, todos);
  const [state, setState] = useState<CopyState>("idle");
  const box = useRef<HTMLTextAreaElement>(null);
  const lineCount = text.split("\n").length;

  useEffect(() => {
    if (state === "failed") {
      box.current?.focus();
      box.current?.select();
    }
  }, [state]);

  const disabled = pending || leagues.kind !== "ready" || digests.some(isPending);
  return (
    <div className="mt-4">
      <Button
        disabled={disabled}
        onClick={() => void copyText(text).then((ok) => setState(ok ? "copied" : "failed"))}
        className="w-full sm:w-auto"
      >
        Copy summary
      </Button>
      <p role="status" className="mt-2 min-h-5 text-caption text-label">
        {disabled && "Waiting for your to-dos to load."}
        {!disabled && state === "copied" && `Copied ${lineCount} lines.`}
        {!disabled && state === "failed" && "Could not copy. The text is selected."}
      </p>
      {state === "failed" && <Textarea ref={box} readOnly aria-label="Weekly summary" value={text} rows={lineCount} />}
    </div>
  );
}
