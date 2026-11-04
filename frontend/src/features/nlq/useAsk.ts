import { useCallback, useEffect, useRef, useState } from "react";

import { getStatById, type PlayerRole } from "@/shared/config/statDictionary";
import { getFilterChipGroups } from "@/shared/lib/filterChipGroups";
import { getPlayerDictionary } from "@/shared/lib/players";
import { type QueryIntent, requestIntent } from "@/shared/lib/nlqApi";
import { buildIntentCatalog } from "@/shared/lib/nlqCatalog";
import { isLeagueQuery, MAX_PINNED_PLAYERS, type QueryState } from "@/shared/lib/queryUrl";
import { specFromIntent, unsupportedReasons } from "@/shared/lib/querySpec";
import type { PlayerDictionaryRow } from "@/shared/lib/schemas/players";
import { useQueryState } from "@/shared/lib/useQueryState";
import { useManifestStore } from "@/stores/useManifestStore";

import { isNewEdit, type LoggedQuery } from "./askLog";
import { browserStorage, logAsk, logCorrection } from "./askLogStore";
import { type AnswerPath, type Interpretation, interpretQuestion } from "./interpretQuestion";
import { cacheKey, catalogSignature, lookupIntent, readIntentCache, storeIntent } from "./intentCache";
import { withDefaultSeasonType } from "./intentFilters";
import { narrowByRoles, type PlayerMatch, pickCandidate, resolvePlayers } from "./resolvePlayers";
import { type Leaderboard, parseRules } from "./ruleParser";

export type AskPhase = "idle" | "working" | "choosing";

const NO_PLAYER_MESSAGE =
  "I couldn't find a player in that question. Name one by last or full name, like " +
  "“Mahomes passing yards 2023”, or ask for a leaderboard like “who led the league in passing yards in 2023”.";

function rolesOf(intent: QueryIntent): PlayerRole[] {
  const roles = intent.stat_ids.flatMap((id) => {
    const stat = getStatById(id);
    return stat ? [stat.playerRole] : [];
  });
  return [...new Set(roles)];
}

const loggedFrom = (state: QueryState): LoggedQuery => ({
  players: state.players,
  stats: state.stats,
  filters: state.filters,
  granularity: state.granularity,
  order: state.order,
  limit: state.limit,
});

/** The cache key for a question under the catalog as it is now. */
const keyFor = (question: string) => cacheKey(catalogSignature(buildIntentCatalog()), question);

/**
 * Reads a question: a correction the user saved wins, then the rules, then the model, whose answers
 * are remembered so asking again costs nothing.
 */
async function interpret(question: string, matches: PlayerMatch[]): Promise<Interpretation> {
  const storage = browserStorage();
  const key = keyFor(question);
  const cached = storage ? lookupIntent(readIntentCache(storage), key) : undefined;
  if (cached?.source === "correction") {
    return { kind: "intent", intent: cached.intent, path: "saved" };
  }
  const askModel: typeof requestIntent = async (q) => {
    if (cached?.source === "model") {
      return { outcome: "query", intent: cached.intent };
    }
    const outcome = await requestIntent(q);
    if (storage && outcome.outcome === "query") {
      storeIntent(storage, key, { intent: outcome.intent, source: "model" });
    }
    return outcome;
  };
  return interpretQuestion({
    question,
    matches,
    seasons: useManifestStore.getState().seasons,
    chipGroups: getFilterChipGroups(),
    askModel,
  });
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
  const [answeredBy, setAnsweredBy] = useState<{
    question: string;
    path: AnswerPath;
    unrecognized: string[];
    entryId: string;
    /** The query as first answered, to tell when the user changed it. */
    answeredKey: string;
  } | null>(null);
  const [pending, setPending] = useState<{ path: AnswerPath; unrecognized: string[] }>({ path: "model", unrecognized: [] });

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

  /** Shows a message instead of an answer, and keeps it in the log. */
  const fail = useCallback((asked: string, path: AnswerPath | "none", text: string) => {
    logAsk({ question: asked, path, outcome: { kind: "message", text } });
    setMessage(text);
    setPhase("idle");
  }, []);

  /** Logs the answer and shows it by navigating to its URL. */
  const answer = useCallback(
    (next: QueryState, asked: string, path: AnswerPath, unrecognized: string[]) => {
      const logged = loggedFrom(next);
      const entryId = logAsk({ question: asked, path, outcome: { kind: "answered", query: logged } });
      setAnsweredBy({ question: asked, path, unrecognized, entryId, answeredKey: JSON.stringify(logged) });
      showQuery(next, asked);
      // The same question can be asked twice, which leaves the URL's question unchanged.
      setPhase("idle");
    },
    [showQuery],
  );

  const show = useCallback(
    (players: PlayerDictionaryRow[], next: QueryIntent, asked: string, path: AnswerPath, unrecognized: string[]) => {
      const ids = [...new Set(players.map((p) => p.gsis_id))].slice(0, MAX_PINNED_PLAYERS);
      const blocked = unsupportedReasons(specFromIntent(next, ids));
      if (blocked.length > 0) {
        fail(asked, path, blocked.join(" "));
        return;
      }
      answer(
        {
          players: ids,
          stats: next.stat_ids,
          filters: withDefaultSeasonType(next.filter_ids),
          granularity: next.granularity,
          minPlays: 0,
          order: null,
          limit: null,
        },
        asked,
        path,
        unrecognized,
      );
    },
    [answer, fail],
  );

  /** A ranking across the league, read by the rules: no player to match, so no model call either. */
  const showLeaderboard = useCallback(
    (next: QueryIntent, board: Leaderboard, asked: string) => {
      answer(
        {
          players: [],
          stats: next.stat_ids,
          filters: withDefaultSeasonType(next.filter_ids),
          granularity: next.granularity,
          minPlays: board.minPlays,
          order: board.order,
          limit: board.limit,
        },
        asked,
        "rules",
        [],
      );
    },
    [answer],
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
        const read = parseRules(trimmed, {
          matches,
          seasons: useManifestStore.getState().seasons,
          chipGroups: getFilterChipGroups(),
        });
        if (read.status === "resolved" && read.leaderboard) {
          showLeaderboard(read.intent, read.leaderboard, trimmed);
          return;
        }
        fail(trimmed, "none", read.status === "unsupported" ? read.reason : NO_PLAYER_MESSAGE);
        return;
      }

      const interpretation = await interpret(trimmed, matches);
      if (request !== currentRequest.current) {
        return;
      }
      if (interpretation.kind === "message") {
        fail(trimmed, "none", interpretation.text);
        return;
      }
      const next = interpretation.intent;
      const unrecognized = interpretation.unrecognized ?? [];
      setPending({ path: interpretation.path, unrecognized });
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
      show(sure, next, trimmed, interpretation.path, unrecognized);
    } catch (e) {
      if (request === currentRequest.current) {
        fail(trimmed, "none", errorText(e));
      }
    }
  }, [question, show, showLeaderboard, fail]);

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
      show(players, intent, question.trim(), pending.path, pending.unrecognized);
    },
    [intent, choices, resolved, show, question, pending],
  );

  /** True when the URL holds a query to show: players (or a leaderboard) and at least one stat. */
  const hasResult = (state.players.length > 0 || isLeagueQuery(state)) && state.stats.length > 0;

  // An edit to the answer on screen (a chip removed, a different granularity) is a correction: log it
  // and remember it, so the same question gives the corrected answer next time.
  const lastLogged = useRef<{ id: string; key: string } | null>(null);
  useEffect(() => {
    if (!answeredBy || answeredBy.question !== urlQuestion || !hasResult) {
      return;
    }
    const logged = loggedFrom(state);
    const key = JSON.stringify(logged);
    if (!isNewEdit(lastLogged.current, answeredBy.entryId, answeredBy.answeredKey, key)) {
      return;
    }
    lastLogged.current = { id: answeredBy.entryId, key };
    logCorrection(answeredBy.entryId, logged);
    const storage = browserStorage();
    if (storage && state.order === null && state.limit === null) {
      storeIntent(storage, keyFor(answeredBy.question), {
        intent: { stat_ids: state.stats, filter_ids: state.filters, granularity: state.granularity },
        source: "correction",
      });
    }
  }, [state, answeredBy, urlQuestion, hasResult]);

  // Which path answered is known only for the answer produced in this session, not after a reload.
  const current = answeredBy && answeredBy.question === urlQuestion ? answeredBy : null;

  return {
    question,
    setQuestion,
    phase,
    message,
    resolved,
    choices,
    onAsk,
    onChoose,
    hasResult,
    path: current?.path ?? null,
    unrecognized: current?.unrecognized ?? [],
  };
}
