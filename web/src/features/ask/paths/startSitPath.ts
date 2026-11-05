import { finishStartSit, readStartSit, type StartSitRead } from "../startSit";
import type { AskPath } from "./types";

type Read = Exclude<StartSitRead, { status: "none" }>;

/** Start/sit is read by rules alone: the model is never asked and the catalog stays as it is. */
export const startSitPath: AskPath<Read> = {
  id: "start_sit",
  read: ({ question, dictionary }) => {
    const read = readStartSit(question, dictionary);
    return read.status === "none" ? null : read;
  },
  answer: (read, { question }, actions) => {
    if (read.status === "message") {
      actions.fail(question, "rules", read.text);
    } else if (read.status === "choose") {
      actions.choose(read.sure, read.unsure, (players, asked) => {
        const done = finishStartSit(players);
        if (done.status === "resolved") actions.showStartSit({ ...done.outcome, names: done.names }, asked);
        else if (done.status === "message") actions.fail(asked, "rules", done.text);
      });
    } else if (read.status === "resolved") {
      actions.showStartSit({ ...read.outcome, names: read.names }, question);
    }
  },
};
