import { PlayerLink } from "@/components/PlayerLink";
import { type KeyboardEvent, useMemo } from "react";
import { Link } from "react-router-dom";

import { useFilterChipGroups } from "@/stat/react/filterChipGroups";
import { IgnoredFiltersNotice } from "@/features/explore/IgnoredFiltersNotice";
import { ParticipationNotice } from "@/features/explore/ParticipationNotice";
import { ExploreResultsCanvas } from "@/features/explore/ExploreResultsCanvas";
import { useExploreQueryExecution } from "@/features/explore/useExploreQueryExecution";
import { Callout } from "@/components/Callout";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useLeagueName } from "@/lib/league";
import { TEAMS } from "@/stat/config/teams";
import { isLeagueQuery, serializeQuery } from "@/stat/lib/queryUrl";
import { useQueryState } from "@/stat/react/useQueryState";

import { buildAnswer } from "./answerText";
import { InterpretationChips } from "./InterpretationChips";
import { PlayerChips, PlayerChoices } from "./NlqPlayerPickers";
import { StartSitAnswer } from "./StartSitAnswer";
import { TradeAnswer } from "./TradeAnswer";
import { useAsk } from "./useAsk";

/** The intent endpoint rejects longer questions (max_length in nfl_stat/schemas/nlq.py); it also bounds the ask log. */
const MAX_QUESTION_LENGTH = 2000;

export function NLQPanel() {
  const ask = useAsk();
  const exec = useExploreQueryExecution();
  const { state } = useQueryState();
  const chipGroups = useFilterChipGroups();

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

  const leagueName = useLeagueName();
  const positionByGsis = useMemo(() => new Map(exec.namedPlayers.map((p) => [p.gsis_id, p.position ?? ""])), [exec.namedPlayers]);
  const answer = useMemo(() => {
    if (!showingAnswer || !exec.result || exec.result.rows.length === 0) {
      return null;
    }
    return buildAnswer({
      result: exec.result,
      statIds: state.stats,
      granularity: state.granularity,
      filterIds: state.filters,
      chipGroups,
      nameByGsis:
        state.subject === "teams"
          ? new Map(TEAMS.map((t) => [t.id, t.name]))
          : new Map(exec.namedPlayers.map((p) => [p.gsis_id, p.full_name ?? p.gsis_id])),
      ranked: isLeagueQuery(state),
      idColumn: state.subject === "teams" ? "team_id" : "player_id",
      leagueName,
    });
  }, [showingAnswer, exec.result, exec.namedPlayers, state, chipGroups, leagueName]);

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !busy) {
      e.preventDefault();
      void ask.onAsk();
    }
  };

  return (
    <div className="space-y-4">
      <section className="space-y-4" aria-label="Ask a question">
          <p className="measure text-caption text-muted">
            Names are matched in your browser. Built-in rules read what they can; a local model reads the rest. The
            numbers are computed in your browser from play-by-play data.
          </p>

          <Textarea
            value={ask.question}
            onChange={(e) => ask.setQuestion(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="e.g. Mahomes passing yards and touchdowns in 2023, or Kelce vs Kittle receptions per game"
            className="min-h-24 max-w-3xl"
            maxLength={MAX_QUESTION_LENGTH}
            disabled={busy}
            aria-label="Question"
          />

          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" onClick={() => void ask.onAsk()} disabled={busy}>
              {ask.phase === "working" ? "Working…" : "Ask"}
            </Button>
          </div>

          <div role="alert">{ask.message ? <Callout variant="error">{ask.message}</Callout> : null}</div>
          <IgnoredFiltersNotice />
          <ParticipationNotice />

          <PlayerChips players={showingAnswer || ask.phase === "choosing" ? matched : []} />
          <PlayerChoices choices={ask.choices} onChoose={(p) => void ask.onChoose(p)} />

          {answer ? (
            <section aria-label="Answer" className="space-y-1 border-t border-line pt-3">
              <p className="text-caption font-medium uppercase tracking-wide text-focus">{answer.context}</p>
              <ul className="space-y-1 text-body text-ink">
                {answer.parts.map((p, i) => (
                  <li key={answer.lines[i]}>
                    {p.before}
                    {p.gsisId ? <PlayerLink gsisId={p.gsisId} name={p.name} position={positionByGsis.get(p.gsisId) ?? ""} /> : p.name}
                    {p.after}
                  </li>
                ))}
              </ul>
              {ask.path ? (
                <p className="text-caption text-muted">
                  {ask.path === "rules"
                    ? "Read by the built-in rules."
                    : ask.path === "saved"
                      ? "Using the fix you made to this question earlier."
                      : "Read by the local model."}
                </p>
              ) : null}
              {ask.unrecognized.length > 0 ? (
                <p className="text-caption text-warning">
                  The built-in rules did not recognise: {ask.unrecognized.join(", ")}. Check that this answers what you
                  asked.
                </p>
              ) : null}
            </section>
          ) : null}

          {ask.startSit && ask.phase === "idle" ? (
            <StartSitAnswer a={ask.startSit.a} b={ask.startSit.b} names={ask.startSit.names} />
          ) : null}

          {ask.trade && ask.phase === "idle" ? (
            <TradeAnswer give={ask.trade.give} get={ask.trade.get} names={ask.trade.names} positions={ask.trade.positions} />
          ) : null}

          {showingAnswer ? <InterpretationChips /> : null}
      </section>

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
          <p className="text-caption text-muted">
            Want to adjust it?{" "}
            <Link
              to={{ pathname: "/players/find", search: serializeQuery(state).toString() }}
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
