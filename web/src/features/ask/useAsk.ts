import { useCallback, useEffect, useRef, useState } from "react";

import { getStatById, type PlayerRole } from "@/stat/config/statDictionary";
import { useFilterChipGroups } from "@/features/explore/filterChipGroups";
import { useManifest } from "@/features/explore/manifest";
import { getPlayerDictionary } from "@/stat/lib/players";
import { type IntentOutcome, type QueryIntent, requestIntent } from "@/stat/lib/nlqApi";
import { buildIntentCatalog } from "@/stat/lib/nlqCatalog";
import { type FilterChipGroup, getAllFilterChipIds } from "@/stat/config/queryBuilderOptions";
import {
  EMPTY_QUERY,
  isLeagueQuery,
  MAX_PINNED_PLAYERS,
  parseQuery,
  type QueryState,
  writeQuery,
} from "@/stat/lib/queryUrl";
import { specFromIntent, unsupportedReasons } from "@/stat/lib/querySpec";
import type { PlayerDictionaryRow } from "@/stat/lib/schemas/players";
import { useQueryState } from "@/features/explore/useQueryState";
import type { Side, Split } from "@/stat/types/queryBuilder";

import { isNewEdit, type LoggedQuery } from "./askLog";
import { browserStorage, logAsk, logCorrection } from "./askLogStore";
import { type AnswerPath, type Interpretation, interpretQuestion } from "./interpretQuestion";
import {
  cacheKey,
  catalogSignature,
  forgetCorrection,
  lookupIntent,
  readIntentCache,
  storeIntent,
} from "./intentCache";
import { withDefaultSeasonType } from "./intentFilters";
import { narrowByRoles, type PlayerMatch, pickCandidate, resolvePlayers } from "./resolvePlayers";
import { dropTeamNames, resolveTeams } from "./resolveTeams";
import { type Leaderboard, parseRules, splitAsked } from "./ruleParser";

export type AskPhase = "idle" | "working" | "choosing";

const NO_PLAYER_MESSAGE =
  "I couldn't find a player or team in that question. Name a player by last or full name, like " +
  "“Mahomes passing yards 2023”, a team, like “Chiefs passing yards 2023”, or ask for a leaderboard like " +
  "“who led the league in passing yards in 2023”.";

function rolesOf(intent: QueryIntent): PlayerRole[] {
  const roles = intent.stat_ids.flatMap((id) => {
    const stat = getStatById(id);
    // A league stat belongs to no position: it must not narrow who "Josh Allen" can be.
    return stat && stat.source !== "league" ? [stat.playerRole] : [];
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
  split: state.split,
  subject: state.subject,
  teams: state.teams,
  side: state.side,
});

/** What an edit can correct: players and teams are matched by name, never part of the intent. */
const editKey = (state: QueryState): string => {
  const { players: _players, teams: _teams, ...rest } = loggedFrom(state);
  return JSON.stringify(rest);
};

/** "by season" and "each game" split the answer, whichever path read the rest of the question. */
const splitOf = (question: string): Split | null => {
  const split = splitAsked(question);
  return split === "both" ? null : split;
};

/** The cache key for a question under the catalog as it is now. */
const keyFor = (seasons: readonly number[], question: string) =>
  cacheKey(catalogSignature(buildIntentCatalog(seasons)), question);

/** What a question is read against: the data's seasons and the filter chips they give. */
type Context = { seasons: number[]; chipGroups: FilterChipGroup[] };

/**
 * Reads a question: a correction the user saved wins, then the rules, then the model, whose answers
 * are remembered so asking again costs nothing.
 */
async function interpret(
  question: string,
  matches: PlayerMatch[],
  ctx: Context,
  signal: AbortSignal,
): Promise<Interpretation> {
  const storage = browserStorage();
  const key = keyFor(ctx.seasons, question);
  const cached = storage ? lookupIntent(readIntentCache(storage), key) : undefined;
  if (cached?.source === "correction") {
    return { kind: "intent", intent: cached.intent, path: "saved" };
  }
  const askModel = async (q: string): Promise<IntentOutcome> => {
    if (cached?.source === "model") {
      return { outcome: "query", intent: cached.intent };
    }
    const outcome = await requestIntent(q, ctx.seasons, signal);
    if (storage && !signal.aborted && outcome.outcome === "query") {
      storeIntent(storage, key, { intent: outcome.intent, source: "model" });
    }
    return outcome;
  };
  return interpretQuestion({
    question,
    matches,
    seasons: ctx.seasons,
    chipGroups: ctx.chipGroups,
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
  const { manifest, seasons } = useManifest();
  const chipGroups = useFilterChipGroups();
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
  const [pending, setPending] = useState<{ path: AnswerPath; unrecognized: string[] }>({
    path: "model",
    unrecognized: [],
  });

  // Each ask gets a number; leaving the page, going back or asking again makes older ones stale, so a
  // slow model reply cannot replace an answer the user has moved past.
  const currentRequest = useRef(0);
  // The model request in flight, cancelled with the stale ask so a slow server is not kept waiting.
  const controllerRef = useRef<AbortController | null>(null);
  useEffect(() => {
    return () => {
      currentRequest.current += 1;
      controllerRef.current?.abort();
    };
  }, []);

  // The URL is the answer on screen: when it changes (back, forward, a new answer), the box shows its question.
  useEffect(() => {
    currentRequest.current += 1;
    controllerRef.current?.abort();
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
      // The URL can drop or clamp parts of a query, so compare edits against what is actually shown.
      const shown = parseQuery(
        writeQuery(new URLSearchParams(), next),
        new Set(getAllFilterChipIds(chipGroups)),
      );
      const entryId = logAsk({ question: asked, path, outcome: { kind: "answered", query: loggedFrom(shown) } });
      setAnsweredBy({ question: asked, path, unrecognized, entryId, answeredKey: editKey(shown) });
      showQuery(next, asked);
      // The same question can be asked twice, which leaves the URL's question unchanged.
      setPhase("idle");
    },
    [showQuery, chipGroups],
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
          ...EMPTY_QUERY,
          players: ids,
          stats: next.stat_ids,
          filters: withDefaultSeasonType(next.filter_ids),
          granularity: next.granularity,
          minPlays: 0,
          order: null,
          limit: null,
          split: splitOf(asked),
        },
        asked,
        path,
        unrecognized,
      );
    },
    [answer, fail],
  );

  /** Read by the rules alone with no player to match (a league ranking or a team question), so no model call. */
  const showRules = useCallback(
    (
      next: QueryIntent,
      board: Leaderboard | undefined,
      team: { ids: string[]; side: Side } | undefined,
      asked: string,
    ) => {
      answer(
        {
          ...EMPTY_QUERY,
          subject: team ? "teams" : "players",
          teams: team?.ids ?? [],
          side: team?.side ?? "offense",
          stats: next.stat_ids,
          filters: withDefaultSeasonType(next.filter_ids),
          granularity: next.granularity,
          minPlays: board?.minPlays ?? 0,
          order: board?.order ?? null,
          limit: board?.limit ?? null,
          split: splitOf(asked),
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
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setPhase("working");
    setMessage(null);
    setResolved([]);
    setChoices([]);
    setIntent(null);

    try {
      const dictionary = await getPlayerDictionary(manifest);
      if (request !== currentRequest.current) {
        return;
      }
      const matches = dropTeamNames(resolvePlayers(trimmed, dictionary), resolveTeams(trimmed));
      if (matches.length === 0) {
        const read = parseRules(trimmed, {
          matches,
          seasons,
          chipGroups,
        });
        if (read.status === "resolved" && (read.leaderboard || read.team)) {
          showRules(read.intent, read.leaderboard, read.team, trimmed);
          return;
        }
        // With no player, "ambiguous" is a ranking question the rules could not finish: say why.
        fail(
          trimmed,
          "none",
          read.status === "unsupported" || read.status === "ambiguous" ? read.reason : NO_PLAYER_MESSAGE,
        );
        return;
      }

      const interpretation = await interpret(trimmed, matches, { seasons, chipGroups }, controller.signal);
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
  }, [question, show, showRules, fail, manifest, seasons, chipGroups]);

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
  // Ask answers about players only, so a team URL (who=teams) is not shown as an answer here.
  const named = state.subject === "teams" ? state.teams : state.players;
  const hasResult = (named.length > 0 || isLeagueQuery(state)) && state.stats.length > 0;

  // An edit to the answer on screen (a chip removed, a different granularity) is a correction: log it
  // and remember it, so the same question gives the corrected answer next time.
  const lastLogged = useRef<{ id: string; key: string } | null>(null);
  useEffect(() => {
    if (!answeredBy || answeredBy.question !== urlQuestion || !hasResult) {
      return;
    }
    const key = editKey(state);
    if (!isNewEdit(lastLogged.current, answeredBy.entryId, answeredBy.answeredKey, key)) {
      return;
    }
    lastLogged.current = { id: answeredBy.entryId, key };
    logCorrection(answeredBy.entryId, loggedFrom(state));
    const storage = browserStorage();
    // Rankings and team questions are read by the rules alone and never consult the cache, so a saved
    // correction for them would never be replayed; the log above keeps it.
    if (!storage || state.order !== null || state.limit !== null || state.subject === "teams") {
      return;
    }
    const cacheKeyNow = keyFor(seasons, answeredBy.question);
    if (key === answeredBy.answeredKey) {
      // Put back as it was answered: there is nothing left to remember.
      forgetCorrection(storage, cacheKeyNow);
      return;
    }
    storeIntent(storage, cacheKeyNow, {
      intent: { stat_ids: state.stats, filter_ids: state.filters, granularity: state.granularity },
      source: "correction",
    });
  }, [state, answeredBy, urlQuestion, hasResult, seasons]);

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
