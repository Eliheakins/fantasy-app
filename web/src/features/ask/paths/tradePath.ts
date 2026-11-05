import { finishTrade, readTrade, type TradeRead } from "../tradeAsk";
import type { AskActions, AskPath } from "./types";

type Read = Exclude<TradeRead, { status: "none" }>;

/** Acts on a trade read; a finished choice can itself ask again for a namesake on the other side. */
function act(read: TradeRead, asked: string, actions: AskActions): void {
  if (read.status === "message") {
    actions.fail(asked, "rules", read.text);
  } else if (read.status === "choose") {
    const { give } = read;
    actions.choose(read.sure, read.unsure, (players, now) => act(finishTrade(players, give), now, actions));
  } else if (read.status === "resolved") {
    actions.showTrade({ ...read.outcome, names: read.names, positions: read.positions }, asked);
  }
}

/** Trades are read by rules alone too, before the intent flow. */
export const tradePath: AskPath<Read> = {
  id: "trade",
  read: ({ question, dictionary }) => {
    const read = readTrade(question, dictionary);
    return read.status === "none" ? null : read;
  },
  answer: (read, { question }, actions) => act(read, question, actions),
};
