import type { PlayerDictionaryRow } from "@/stat/lib/schemas/players";
import type { FilterChipGroup } from "@/stat/config/queryBuilderOptions";
import type { QueryState } from "@/stat/lib/queryUrl";
import type { AnswerPath } from "../interpretQuestion";
import type { PlayerMatch } from "../resolvePlayers";
import type { StartSitOutcome } from "../startSit";
import type { TradeOutcome } from "../tradeAsk";

/** A start/sit answer on screen: the two players and their names. */
export type StartSitShown = StartSitOutcome & { names: Record<string, string> };

/** A trade answer on screen: the players on each side and their names. */
export type TradeShown = TradeOutcome & { names: Record<string, string>; positions: Record<string, string | null> };

/** What a question is read against. */
export type AskInput = {
  question: string;
  dictionary: PlayerDictionaryRow[];
  seasons: number[];
  /** The latest week each season reaches (the manifest's `max_week`). */
  maxWeeks?: Readonly<Record<number, number>>;
  chipGroups: FilterChipGroup[];
  /** Cancels the model request when the ask goes stale. */
  signal: AbortSignal;
};

/** Finishes a question once the user has picked every namesake; `asked` is the box text at that moment. */
export type Resume = (players: PlayerDictionaryRow[], asked: string) => void;

/** What a path can do to the screen; the hook owns the state behind each. */
export type AskActions = {
  /** Shows a message instead of an answer, and keeps it in the log. */
  fail: (asked: string, path: AnswerPath | "none", text: string) => void;
  /** Logs the answer and shows it by navigating to its URL; `notes` say how a relative or missing time was read. */
  answer: (next: QueryState, asked: string, path: AnswerPath, unrecognized: string[], notes: string[]) => void;
  showStartSit: (shown: StartSitShown, asked: string) => void;
  showTrade: (shown: TradeShown, asked: string) => void;
  /** Asks the user to pick among namesakes; `resume` runs with all the players once none is left. */
  choose: (sure: PlayerDictionaryRow[], unsure: PlayerMatch[], resume: Resume) => void;
};

/**
 * One way of answering a question. `read` returns null when the question is not this path's, so the
 * next path in the list gets it; otherwise `answer` acts on what was read. Adding a path means adding
 * one file and one entry in `ASK_PATHS`.
 */
export type AskPath<M = unknown> = {
  id: "start_sit" | "trade" | "rules" | "model";
  read: (input: AskInput) => M | null | Promise<M | null>;
  answer: (match: M, input: AskInput, actions: AskActions) => void;
};
