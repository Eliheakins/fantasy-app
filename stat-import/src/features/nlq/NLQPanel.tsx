import { type KeyboardEvent, useMemo } from "react";
import { Link } from "react-router-dom";

import { IgnoredFiltersNotice } from "@/features/explore/IgnoredFiltersNotice";
import { ParticipationNotice } from "@/features/explore/ParticipationNotice";
import { ExploreResultsCanvas } from "@/features/explore/ExploreResultsCanvas";
import { useExploreQueryExecution } from "@/features/explore/useExploreQueryExecution";
import { Callout } from "@/shared/components/Callout";
import { Button } from "@/shared/components/ui/button";
import { Card, CardContent, CardTitle } from "@/shared/components/ui/card";
import { Textarea } from "@/shared/components/ui/textarea";
import { TEAMS } from "@/shared/config/teams";
import { isLeagueQuery, serializeQuery } from "@/shared/lib/queryUrl";
import { useQueryState } from "@/shared/lib/useQueryState";

import { buildAnswer } from "./answerText";
import { InterpretationChips } from "./InterpretationChips";
import { PlayerChips, PlayerChoices } from "./NlqPlayerPickers";
import { useAsk } from "./useAsk";

export function NLQPanel() {
  const ask = useAsk();
  const exec = useExploreQueryExecution();
  const { state } = useQueryState();

  const busy = ask.phase === "working" || ask.phase === "choosing";
  // A failed or unsupported ask shows its message instead of the previous answer.
  const showingAnswer = ask.hasResult && ask.phase === "idle" && ask.message === null;

  // While choosing between namesakes the matches so far are shown; otherwise the answer's own players.
  const matched = useMemo(
    () =>
      ask.phase === "choosing"
        ? ask.resolved
        : exec.pinnedPlayers.map((p) => ({
            gsis_id: p.gsis_id,
            display_name: p.full_name ?? p.gsis_id,
            search_key: "",
            position: p.position,
            team: p.team,
          })),
    [ask.phase, ask.resolved, exec.pinnedPlayers],
  );

  const answer = useMemo(() => {
    if (!showingAnswer || !exec.result || exec.result.rows.length === 0) {
      return null;
    }
    return buildAnswer({
      result: exec.result,
      statIds: state.stats,
      granularity: state.granularity,
      filterIds: state.filters,
      nameByGsis:
        state.subject === "teams"
          ? new Map(TEAMS.map((t) => [t.id, t.name]))
          : new Map(exec.namedPlayers.map((p) => [p.gsis_id, p.full_name ?? p.gsis_id])),
      ranked: isLeagueQuery(state),
      idColumn: state.subject === "teams" ? "team_id" : "player_id",
    });
  }, [showingAnswer, exec.result, exec.namedPlayers, state]);

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
              Names are matched in your browser. A local model picks the stats and filters, and the Explore query
              builder runs them on play-by-play data.
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
          <IgnoredFiltersNotice />
          <ParticipationNotice />

          <PlayerChips players={showingAnswer || ask.phase === "choosing" ? matched : []} />
          <PlayerChoices choices={ask.choices} onChoose={(p) => void ask.onChoose(p)} />

          {answer ? (
            <section aria-label="Answer" className="space-y-1 rounded-md border border-border bg-input/40 p-3">
              <p className="text-xs font-medium uppercase tracking-wide text-ink-muted">{answer.context}</p>
              <ul className="space-y-1 text-sm text-ink">
                {answer.lines.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
              {ask.path ? (
                <p className="text-[11px] text-ink-muted">
                  {ask.path === "rules"
                    ? "Read by the built-in rules."
                    : ask.path === "saved"
                      ? "Using the fix you made to this question earlier."
                      : "Read by the local model."}
                </p>
              ) : null}
              {ask.unrecognized.length > 0 ? (
                <p className="text-[11px] text-warn-fg">
                  The built-in rules did not recognise: {ask.unrecognized.join(", ")}. Check that this answers what you
                  asked.
                </p>
              ) : null}
            </section>
          ) : null}

          {showingAnswer ? <InterpretationChips /> : null}
        </CardContent>
      </Card>

      {showingAnswer ? (
        <>
          <ExploreResultsCanvas
            result={exec.result}
            error={exec.error}
            details={exec.details}
            running={exec.running}
            pinnedPlayers={exec.pinnedPlayers}
            namedPlayers={exec.namedPlayers}
          />
          <p className="text-xs text-ink-muted">
            Want to adjust it?{" "}
            <Link
              to={{ pathname: "/explore", search: serializeQuery(state).toString() }}
              className="font-medium text-ink underline-offset-2 hover:underline"
            >
              Open this query in Explore
            </Link>
            .
          </p>
        </>
      ) : null}
    </div>
  );
}
