import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { getAllFilterChipIds } from "@/stat/config/queryBuilderOptions";
import { useFilterChipGroups } from "@/stat/react/filterChipGroups";
import { useManifest } from "@/stat/react/manifest";
import { getPlayerDictionary } from "@/stat/lib/players";
import { isLeagueQuery, parseQuery, type QueryState, writeQuery } from "@/stat/lib/queryUrl";
import type { PlayerDictionaryRow } from "@/stat/lib/schemas/players";
import { useQueryState } from "@/stat/react/useQueryState";

import { isNewEdit, type LoggedQuery } from "./askLog";
import { browserStorage, logAsk, logCorrection } from "./askLogStore";
import type { AnswerPath } from "./interpretQuestion";
import { forgetCorrection, storeIntent } from "./intentCache";
import { dispatchAsk } from "./paths/dispatch";
import { keyFor } from "./paths/modelPath";
import type { AskActions, Resume, StartSitShown, TradeShown } from "./paths/types";
import type { PlayerMatch } from "./resolvePlayers";

export type { StartSitShown, TradeShown };
export type AskPhase = "idle" | "working" | "choosing";

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

/**
 * Ask flow: the question goes down the ordered `ASK_PATHS` (start/sit, trade, rules, model) and the
 * first that reads it answers, by navigating to a URL that holds the question and the query.
 * Reloading or going back shows the same answer without asking the model again, and Explore's own
 * URL is never touched.
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
  const [startSit, setStartSit] = useState<StartSitShown | null>(null);
  const [trade, setTrade] = useState<TradeShown | null>(null);
  const [, setParams] = useSearchParams();
  // The question a start/sit or trade answer belongs to, and how the pending namesake choice finishes.
  const startSitFor = useRef<string | null>(null);
  const resume = useRef<Resume | null>(null);
  const [answeredBy, setAnsweredBy] = useState<{
    question: string;
    path: AnswerPath;
    unrecognized: string[];
    entryId: string;
    /** The query as first answered, to tell when the user changed it. */
    answeredKey: string;
  } | null>(null);

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
    resume.current = null;
    if (startSitFor.current !== urlQuestion) {
      setStartSit(null);
      setTrade(null);
    }
    setPhase("idle");
  }, [urlQuestion]);

  const fail = useCallback<AskActions["fail"]>((asked, path, text) => {
    logAsk({ question: asked, path, outcome: { kind: "message", text } });
    setMessage(text);
    setPhase("idle");
  }, []);

  const answer = useCallback<AskActions["answer"]>(
    (next, asked, path, unrecognized) => {
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

  /** A start/sit or trade answer: the URL keeps the question, so reload or a shared link answers it again. */
  const keepQuestion = useCallback(
    (asked: string) => {
      startSitFor.current = asked;
      setPhase("idle");
      setParams((prev) => {
        const next = new URLSearchParams(prev);
        next.set("q", asked);
        return next;
      });
    },
    [setParams],
  );

  const showStartSit = useCallback<AskActions["showStartSit"]>(
    (shown, asked) => {
      const [first, second] = [shown.names[shown.a], shown.names[shown.b]];
      logAsk({ question: asked, path: "rules", outcome: { kind: "start_sit", text: `${first} or ${second}` } });
      setStartSit(shown);
      keepQuestion(asked);
    },
    [keepQuestion],
  );

  const showTrade = useCallback<AskActions["showTrade"]>(
    (shown, asked) => {
      const list = (ids: string[]) => ids.map((id) => shown.names[id]).join(" and ");
      logAsk({ question: asked, path: "rules", outcome: { kind: "trade", text: `${list(shown.give)} for ${list(shown.get)}` } });
      setTrade(shown);
      keepQuestion(asked);
    },
    [keepQuestion],
  );

  const choose = useCallback<AskActions["choose"]>((sure, unsure, finish) => {
    resume.current = finish;
    setResolved(sure);
    setChoices(unsure);
    setPhase("choosing");
  }, []);

  // Paths and namesake choices outlive this render, so they call through to the latest handlers.
  const latest = useRef<AskActions>({ fail, answer, showStartSit, showTrade, choose });
  latest.current = { fail, answer, showStartSit, showTrade, choose };
  const actions = useMemo<AskActions>(
    () => ({
      fail: (...a) => latest.current.fail(...a),
      answer: (...a) => latest.current.answer(...a),
      showStartSit: (...a) => latest.current.showStartSit(...a),
      showTrade: (...a) => latest.current.showTrade(...a),
      choose: (...a) => latest.current.choose(...a),
    }),
    [],
  );

  const onAsk = useCallback(async (text?: string) => {
    const trimmed = (text ?? question).trim();
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
    setStartSit(null);
    setTrade(null);
    startSitFor.current = null;
    resume.current = null;

    const isStale = () => request !== currentRequest.current;
    try {
      const dictionary = await getPlayerDictionary(manifest);
      if (isStale()) {
        return;
      }
      await dispatchAsk({ question: trimmed, dictionary, seasons, chipGroups, signal: controller.signal }, actions, isStale);
    } catch (e) {
      if (!isStale()) {
        fail(trimmed, "none", e instanceof Error ? e.message : String(e));
      }
    }
  }, [question, fail, actions, manifest, seasons, chipGroups]);

  const onChoose = useCallback(
    (player: PlayerDictionaryRow) => {
      const finish = resume.current;
      if (!finish) {
        return;
      }
      const remaining = choices.filter((c) => !c.candidates.some((x) => x.gsis_id === player.gsis_id));
      const players = [...resolved, player];
      setResolved(players);
      setChoices(remaining);
      if (remaining.length > 0) {
        return;
      }
      resume.current = null;
      finish(players, question.trim());
    },
    [choices, resolved, question],
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

  // Arriving with a question in the URL and no answer in it (the top bar's Ask box) answers it, as the box does.
  const arrivalAsk = useRef(onAsk);
  arrivalAsk.current = onAsk;
  const hasResultRef = useRef(hasResult);
  hasResultRef.current = hasResult;
  useEffect(() => {
    if (urlQuestion.trim() && !hasResultRef.current && startSitFor.current !== urlQuestion) {
      void arrivalAsk.current(urlQuestion);
    }
  }, [urlQuestion]);

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
    startSit,
    trade,
    path: current?.path ?? null,
    unrecognized: current?.unrecognized ?? [],
  };
}
