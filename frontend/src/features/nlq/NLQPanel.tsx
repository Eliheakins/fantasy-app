import { type KeyboardEvent, useMemo } from "react";
import { Link } from "react-router-dom";

import { ExploreResultsCanvas } from "@/features/explore/ExploreResultsCanvas";
import { useExploreQueryExecution } from "@/features/explore/useExploreQueryExecution";
import { Callout } from "@/shared/components/Callout";
import { Button } from "@/shared/components/ui/button";
import { Card, CardContent, CardTitle } from "@/shared/components/ui/card";
import { Textarea } from "@/shared/components/ui/textarea";
import { useQueryBuilderStore } from "@/stores/useQueryBuilderStore";

import { buildAnswer } from "./answerText";
import { PlayerChips, PlayerChoices } from "./NlqPlayerPickers";
import { useAsk } from "./useAsk";

export function NLQPanel() {
  const ask = useAsk();
  const exec = useExploreQueryExecution();
  const selectedStatIds = useQueryBuilderStore((s) => s.selectedStatIds);
  const activeGranularity = useQueryBuilderStore((s) => s.activeGranularity);
  const filterChipState = useQueryBuilderStore((s) => s.filterChipState);

  const busy = ask.phase === "working" || ask.phase === "choosing";

  const answer = useMemo(() => {
    if (ask.phase !== "done" || !exec.result || exec.result.rows.length === 0) {
      return null;
    }
    return buildAnswer({
      result: exec.result,
      statIds: selectedStatIds,
      granularity: activeGranularity,
      filterIds: Object.entries(filterChipState)
        .filter(([, on]) => on)
        .map(([id]) => id),
      nameByGsis: new Map(exec.pinnedPlayers.map((p) => [p.gsis_id, p.full_name ?? p.gsis_id])),
    });
  }, [ask.phase, exec.result, exec.pinnedPlayers, selectedStatIds, activeGranularity, filterChipState]);

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !busy) {
      e.preventDefault();
      void ask.onAsk();
    }
  };

  return (
    <div className="space-y-4">
      <Card className="overflow-hidden border-border">
        <CardContent className="space-y-4 px-4 pb-6 pt-5 md:px-6">
          <div>
            <CardTitle className="text-lg text-ink">Ask</CardTitle>
            <p className="mt-1 text-xs text-ink-muted">
              Names are matched in your browser. A local model picks the stats and filters, and the
              Explore query builder runs them on play-by-play data.
            </p>
          </div>

          <Textarea
            value={ask.question}
            onChange={(e) => ask.setQuestion(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="e.g. Mahomes passing yards and touchdowns in 2023, or Kelce vs Kittle receptions per game"
            className="min-h-[88px] text-sm"
            disabled={busy}
            aria-label="Question"
          />

          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" onClick={() => void ask.onAsk()} disabled={busy}>
              {ask.phase === "working" ? "Working…" : "Ask"}
            </Button>
          </div>

          {ask.message ? <Callout variant="danger">{ask.message}</Callout> : null}

          <PlayerChips players={ask.resolved} />
          <PlayerChoices choices={ask.choices} onChoose={(p) => void ask.onChoose(p)} />

          {answer ? (
            <section aria-label="Answer" className="space-y-1 rounded-md border border-border bg-input/40 p-3">
              <p className="text-xs font-medium uppercase tracking-wide text-ink-muted">{answer.context}</p>
              <ul className="space-y-1 text-sm text-ink">
                {answer.lines.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            </section>
          ) : null}
        </CardContent>
      </Card>

      {ask.phase === "done" ? (
        <>
          <ExploreResultsCanvas
            result={exec.result}
            error={exec.error}
            details={exec.details}
            running={exec.running}
            pinnedPlayers={exec.pinnedPlayers}
          />
          <p className="text-xs text-ink-muted">
            Want to adjust it?{" "}
            <Link to="/explore" className="font-medium text-ink underline-offset-2 hover:underline">
              Open this query in Explore
            </Link>
            .
          </p>
        </>
      ) : null}
    </div>
  );
}
