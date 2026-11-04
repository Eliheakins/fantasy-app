import { useCallback, useEffect, useRef, useState } from "react";

import { getStatById, type PlayerRole } from "@/shared/config/statDictionary";
import { getPlayerDictionary, getPlayersByIds } from "@/shared/lib/players";
import { type QueryIntent, requestIntent } from "@/shared/lib/nlqApi";
import { specFromIntent, unsupportedReasons } from "@/shared/lib/querySpec";
import type { PlayerDictionaryRow } from "@/shared/lib/schemas/players";
import { useQueryBuilderStore } from "@/stores/useQueryBuilderStore";
import { MAX_PINNED_PLAYERS, useWorkbenchStore } from "@/stores/useWorkbenchStore";

import { withDefaultSeasonType } from "./intentFilters";
import { narrowByRoles, type PlayerMatch, pickCandidate, resolvePlayers } from "./resolvePlayers";

export type AskPhase = "idle" | "working" | "choosing" | "done";

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
 * Ask flow: match players locally, let the model pick stats/filters, then hand the result to the
 * Explore stores. The Explore query hook runs the query, so Ask and Explore always agree.
 */
export function useAsk() {
  const [question, setQuestion] = useState("");
  const [phase, setPhase] = useState<AskPhase>("idle");
  const [message, setMessage] = useState<string | null>(null);
  const [resolved, setResolved] = useState<PlayerDictionaryRow[]>([]);
  const [choices, setChoices] = useState<PlayerMatch[]>([]);
  const [intent, setIntent] = useState<QueryIntent | null>(null);

  const setPins = useWorkbenchStore((s) => s.setPins);
  const applyIntent = useQueryBuilderStore((s) => s.applyIntent);

  // Each ask gets a number; leaving the page or asking again makes older ones stale, so a slow
  // model reply cannot replace pins or stats the user has set since.
  const currentRequest = useRef(0);
  useEffect(() => {
    return () => {
      currentRequest.current += 1;
    };
  }, []);

  const apply = useCallback(
    async (players: PlayerDictionaryRow[], next: QueryIntent, request: number) => {
      const unique = [...new Map(players.map((p) => [p.gsis_id, p])).values()].slice(
        0,
        MAX_PINNED_PLAYERS,
      );
      const blocked = unsupportedReasons(
        specFromIntent(
          next,
          unique.map((p) => p.gsis_id),
        ),
      );
      if (blocked.length > 0) {
        setMessage(blocked.join(" "));
        setPhase("idle");
        return;
      }
      const found = await getPlayersByIds(unique.map((p) => p.gsis_id));
      if (request !== currentRequest.current) {
        return;
      }
      setPins(found);
      applyIntent({
        statIds: next.stat_ids,
        filterIds: withDefaultSeasonType(next.filter_ids),
        granularity: next.granularity,
      });
      setResolved(unique);
      setIntent(next);
      setPhase("done");
    },
    [setPins, applyIntent],
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
      await apply(sure, next, request);
    } catch (e) {
      if (request === currentRequest.current) {
        setMessage(errorText(e));
        setPhase("idle");
      }
    }
  }, [question, apply]);

  const onChoose = useCallback(
    async (player: PlayerDictionaryRow) => {
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
      setPhase("working");
      const request = ++currentRequest.current;
      try {
        await apply(players, intent, request);
      } catch (e) {
        if (request === currentRequest.current) {
          setMessage(errorText(e));
          setPhase("idle");
        }
      }
    },
    [intent, choices, resolved, apply],
  );

  return { question, setQuestion, phase, message, resolved, choices, onAsk, onChoose };
}
