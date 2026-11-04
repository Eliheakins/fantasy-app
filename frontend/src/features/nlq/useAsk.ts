import { useCallback, useEffect, useRef, useState } from "react";

import { getStatById, type PlayerRole } from "@/shared/config/statDictionary";
import { getPlayerDictionary } from "@/shared/lib/players";
import { type QueryIntent, requestIntent } from "@/shared/lib/nlqApi";
import { MAX_PINNED_PLAYERS } from "@/shared/lib/queryUrl";
import { specFromIntent, unsupportedReasons } from "@/shared/lib/querySpec";
import type { PlayerDictionaryRow } from "@/shared/lib/schemas/players";
import { useQueryState } from "@/shared/lib/useQueryState";

import { withDefaultSeasonType } from "./intentFilters";
import { narrowByRoles, type PlayerMatch, pickCandidate, resolvePlayers } from "./resolvePlayers";

export type AskPhase = "idle" | "working" | "choosing";

const NO_PLAYER_MESSAGE =
  "I couldn't find a player in that question. Name one by last or full name, like " +
  "“Mahomes passing yards 2023”. League-wide leaderboards aren't supported yet.";

function rolesOf(intent: QueryIntent): PlayerRole[] {
  const roles = intent.stat_ids.flatMap((id) => {
    const stat = getStatById(id);
    return stat ? [stat.playerRole] : [];
  });
  return [...new Set(roles)];
}

function errorText(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

/**
 * Ask flow: match players locally, let the model pick stats and filters, then show the answer by
 * navigating to a URL that holds the question and the query. Reloading or going back shows the
 * same answer without asking the model again, and Explore's own URL is never touched.
 */
export function useAsk() {
  const { state, question: urlQuestion, showQuery } = useQueryState();
  const [question, setQuestion] = useState(urlQuestion);
  const [phase, setPhase] = useState<AskPhase>("idle");
  const [message, setMessage] = useState<string | null>(null);
  const [resolved, setResolved] = useState<PlayerDictionaryRow[]>([]);
  const [choices, setChoices] = useState<PlayerMatch[]>([]);
  const [intent, setIntent] = useState<QueryIntent | null>(null);

  // Each ask gets a number; leaving the page, going back or asking again makes older ones stale, so a
  // slow model reply cannot replace an answer the user has moved past.
  const currentRequest = useRef(0);
  useEffect(() => {
    return () => {
      currentRequest.current += 1;
    };
  }, []);

  // The URL is the answer on screen: when it changes (back, forward, a new answer), the box shows its question.
  useEffect(() => {
    currentRequest.current += 1;
    setQuestion(urlQuestion);
    setMessage(null);
    setResolved([]);
    setChoices([]);
    setIntent(null);
    setPhase("idle");
  }, [urlQuestion]);

  const show = useCallback(
    (players: PlayerDictionaryRow[], next: QueryIntent, asked: string) => {
      const ids = [...new Set(players.map((p) => p.gsis_id))].slice(0, MAX_PINNED_PLAYERS);
      const blocked = unsupportedReasons(specFromIntent(next, ids));
      if (blocked.length > 0) {
        setMessage(blocked.join(" "));
        setPhase("idle");
        return;
      }
      showQuery(
        {
          players: ids,
          stats: next.stat_ids,
          filters: withDefaultSeasonType(next.filter_ids),
          granularity: next.granularity,
          minPlays: 0,
        },
        asked,
      );
      // The same question can be asked twice, which leaves the URL's question unchanged.
      setPhase("idle");
    },
    [showQuery],
  );

  const onAsk = useCallback(async () => {
    const trimmed = question.trim();
    if (!trimmed) {
      setMessage("Type a question first.");
      return;
    }
    const request = ++currentRequest.current;
    setPhase("working");
    setMessage(null);
    setResolved([]);
    setChoices([]);
    setIntent(null);

    try {
      const dictionary = await getPlayerDictionary();
      if (request !== currentRequest.current) {
        return;
      }
      const matches = resolvePlayers(trimmed, dictionary);
      if (matches.length === 0) {
        setMessage(NO_PLAYER_MESSAGE);
        setPhase("idle");
        return;
      }

      const outcome = await requestIntent(trimmed);
      if (request !== currentRequest.current) {
        return;
      }
      if (outcome.outcome === "unsupported") {
        setMessage(outcome.reason);
        setPhase("idle");
        return;
      }
      const next = outcome.intent;
      const roles = rolesOf(next);
      const sure: PlayerDictionaryRow[] = [];
      const unsure: PlayerMatch[] = [];
      for (const match of matches) {
        const pick = pickCandidate(match, roles);
        if (pick) {
          sure.push(pick);
        } else {
          unsure.push({ ...match, candidates: narrowByRoles(match.candidates, roles) });
        }
      }

      setIntent(next);
      if (unsure.length > 0) {
        setResolved(sure);
        setChoices(unsure);
        setPhase("choosing");
        return;
      }
      show(sure, next, trimmed);
    } catch (e) {
      if (request === currentRequest.current) {
        setMessage(errorText(e));
        setPhase("idle");
      }
    }
  }, [question, show]);

  const onChoose = useCallback(
    (player: PlayerDictionaryRow) => {
      if (!intent) {
        return;
      }
      const remaining = choices.filter((c) => !c.candidates.some((x) => x.gsis_id === player.gsis_id));
      const players = [...resolved, player];
      setResolved(players);
      setChoices(remaining);
      if (remaining.length > 0) {
        return;
      }
      show(players, intent, question.trim());
    },
    [intent, choices, resolved, show, question],
  );

  /** True when the URL holds a query to show: players and at least one stat. */
  const hasResult = state.players.length > 0 && state.stats.length > 0;

  return { question, setQuestion, phase, message, resolved, choices, onAsk, onChoose, hasResult };
}
