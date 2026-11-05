import {
  appendEntry,
  type AskLogEntry,
  loadLog,
  type LoggedQuery,
  recordCorrection,
  saveLog,
  type StorageLike,
} from "./askLog";

/** The browser's storage, or null where it is blocked; the log then simply stays empty. */
function browserStorage(): StorageLike | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export const readLog = (): AskLogEntry[] => {
  const storage = browserStorage();
  return storage ? loadLog(storage) : [];
};

/** `crypto.randomUUID` exists only in secure contexts; plain http (a Tailscale address) lacks it. */
const newId = (): string =>
  typeof crypto.randomUUID === "function" ? crypto.randomUUID() : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;

/** Adds an ask to the log and returns its id, so a later edit can be attached to it. */
export function logAsk(entry: Pick<AskLogEntry, "question" | "path" | "outcome">): string {
  const id = newId();
  const storage = browserStorage();
  if (storage) {
    saveLog(storage, appendEntry(loadLog(storage), { ...entry, id, at: new Date().toISOString(), corrected: null }));
  }
  return id;
}

export function logCorrection(id: string, query: LoggedQuery): void {
  const storage = browserStorage();
  if (storage) {
    saveLog(storage, recordCorrection(loadLog(storage), id, query));
  }
}

export function clearLog(): void {
  const storage = browserStorage();
  if (storage) {
    saveLog(storage, []);
  }
}

export { browserStorage };
