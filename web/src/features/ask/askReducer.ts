import type { PlayerDictionaryRow } from "@/stat/lib/schemas/players";

import type { FantasyRoute } from "./fantasyRoute";
import type { StartSitShown, TradeShown } from "./paths/types";
import type { PlayerMatch } from "./resolvePlayers";

interface ShownValue {
  startSit: StartSitShown;
  trade: TradeShown;
  route: FantasyRoute;
}

/** An answer shown in place of a stat query; at most one at a time. */
export type Shown = { [K in keyof ShownValue]: { kind: K; value: ShownValue[K] } }[keyof ShownValue];

interface Common {
  /** The text in the ask box. */
  question: string;
  message: string | null;
}

export type AskState =
  | (Common & { phase: "idle"; shown: Shown | null })
  | (Common & { phase: "working" })
  | (Common & { phase: "choosing"; resolved: PlayerDictionaryRow[]; choices: PlayerMatch[] });

export type AskEvent =
  | { type: "edit"; question: string }
  /** The URL's question changed; `keepShown` when it is the question the shown answer belongs to. */
  | { type: "urlChanged"; question: string; keepShown: boolean }
  | { type: "needText" }
  | { type: "start" }
  | { type: "fail"; text: string }
  | { type: "answered" }
  | { type: "show"; shown: Shown }
  | { type: "choose"; resolved: PlayerDictionaryRow[]; choices: PlayerMatch[] };

export const initialAsk = (question: string): AskState => ({ phase: "idle", question, message: null, shown: null });

export function askReducer(state: AskState, event: AskEvent): AskState {
  const { question, message } = state;
  switch (event.type) {
    case "edit":
      return { ...state, question: event.question };
    case "urlChanged": {
      const kept = event.keepShown && state.phase === "idle" ? state.shown : null;
      return { phase: "idle", question: event.question, message: null, shown: kept };
    }
    case "needText":
      return { ...state, message: "Type a question first." };
    case "start":
      return { phase: "working", question, message: null };
    case "fail":
      return { phase: "idle", question, message: event.text, shown: null };
    case "answered":
      return { phase: "idle", question, message, shown: null };
    case "show":
      return { phase: "idle", question, message, shown: event.shown };
    case "choose":
      return { phase: "choosing", question, message, resolved: event.resolved, choices: event.choices };
  }
}

/** The shown answer of one kind, or null. */
export function shownOf<K extends keyof ShownValue>(state: AskState, kind: K): ShownValue[K] | null {
  if (state.phase !== "idle" || state.shown?.kind !== kind) {
    return null;
  }
  return state.shown.value as ShownValue[K];
}
