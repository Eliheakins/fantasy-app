import type { Status } from "@/api/types";

/** Hours after which a source is stale; same limits as STALE_HOURS in app/ui.py. */
export const STALE_HOURS: Readonly<Record<string, number>> = {
  Sleeper: 24,
  "NFL stats": 48,
  Simulation: 48,
};

/** Banner lines, worded exactly like stale_banner() in app/ui.py (each ends "Run `make refresh`."). */
export function bannerMessages(status: Status): string[] {
  const old = status.freshness
    .filter((r) => r.age_hours > (STALE_HOURS[r.source] ?? Number.POSITIVE_INFINITY))
    .map((r) => `${r.source} (${r.age_hours.toFixed(0)} hours old)`);
  const messages: string[] = [];
  if (old.length) messages.push(`Stale data: ${old.join(", ")}. Run \`make refresh\`.`);
  if (status.missing_layers.length) {
    messages.push(`Running without: ${status.missing_layers.join(", ")}. Run \`make refresh\`.`);
  }
  if (status.simulation_behind_inputs) messages.push(`${status.simulation_behind_inputs}. Run \`make refresh\`.`);
  return messages;
}

/** Newest source write, for the top bar's "as of" text. */
export function latestUpdate(status: Status): Date | null {
  const times = status.freshness.map((r) => Date.parse(r.updated_at)).filter(Number.isFinite);
  return times.length ? new Date(Math.max(...times)) : null;
}

export function formatAsOf(date: Date): string {
  const day = date.toLocaleDateString(undefined, { weekday: "short" });
  const time = date.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  return `${day} ${time}`;
}
