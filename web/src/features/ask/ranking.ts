/**
 * How a ranking is read, the same on the rules and model paths: which end comes first, how many rows,
 * the play floor a player needs to qualify ("min 100 carries"), and "in a single game".
 */
import { familyMember, getStatById, type PlayerRole } from "@/stat/config/statDictionary";
import type { Position, QueryOrder } from "@/stat/lib/queryUrl";
import type { GranularityMode } from "@/stat/types/queryBuilder";

/** A league-wide ranking: the stat to order by, how many rows to keep, the plays a player needs to qualify, and who may be listed. */
export interface Leaderboard {
  order: QueryOrder;
  limit: number;
  minPlays: number;
  position?: Position | null;
  rookie?: boolean;
}

/** Position nouns ("quarterbacks", "tight end") and the position they name. Two-word ones are matched first. */
const POSITION_WORDS: readonly [string[], Position][] = [
  [["running", "backs"], "RB"],
  [["running", "back"], "RB"],
  [["wide", "receivers"], "WR"],
  [["wide", "receiver"], "WR"],
  [["tight", "ends"], "TE"],
  [["tight", "end"], "TE"],
  ...(["qb", "qbs", "quarterback", "quarterbacks"].map((w) => [[w], "QB"]) as [string[], Position][]),
  ...(["rb", "rbs"].map((w) => [[w], "RB"]) as [string[], Position][]),
  ...(["wr", "wrs"].map((w) => [[w], "WR"]) as [string[], Position][]),
  ...(["te", "tes"].map((w) => [[w], "TE"]) as [string[], Position][]),
];
/** Role nouns: a hint that must agree with the ranked stat's role ("top 5 rushers in yards per carry"). */
const ROLE_NOUNS: Readonly<Record<string, PlayerRole>> = {
  rusher: "rusher",
  rushers: "rusher",
  passer: "passer",
  passers: "passer",
  receiver: "receiver",
  receivers: "receiver",
};

/** Who a ranking may list: a position, rookies, a role noun, and the words that say so. */
export function readWho(tokens: readonly string[]): {
  position: Position | null;
  rookie: boolean;
  role: PlayerRole | null;
  at: number[];
  reason?: string;
} {
  const at: number[] = [];
  const positions = new Set<Position>();
  for (const [words, position] of POSITION_WORDS) {
    for (let i = 0; i + words.length <= tokens.length; i++) {
      if (words.every((w, k) => tokens[i + k] === w && !at.includes(i + k))) {
        positions.add(position);
        words.forEach((_, k) => at.push(i + k));
      }
    }
  }
  const rookieAt = tokens.flatMap((t, i) => (t === "rookie" || t === "rookies" ? [i] : []));
  const roleAt = tokens.flatMap((t, i) => (ROLE_NOUNS[t] && !at.includes(i) ? [i] : []));
  const roles = new Set(roleAt.map((i) => ROLE_NOUNS[tokens[i]!]!));
  return {
    position: positions.size === 1 ? [...positions][0]! : null,
    rookie: rookieAt.length > 0,
    role: roles.size === 1 ? [...roles][0]! : null,
    at: [...at, ...rookieAt, ...roleAt],
    ...(positions.size > 1 || roles.size > 1 ? { reason: "It names more than one position." } : {}),
  };
}

/** Words that set which end of a ranking comes first. "best" and "worst" depend on the stat (see `better`). */
const RANK_DIRECTION = new Map<string, "desc" | "asc" | "best" | "worst">([
  ["most", "desc"],
  ["highest", "desc"],
  ["fewest", "asc"],
  ["least", "asc"],
  ["lowest", "asc"],
  ["bottom", "asc"],
  ["best", "best"],
  ["worst", "worst"],
]);
/** Words that ask for a ranking. Without one of these (or the model's ranking signal), a question with no player is not a leaderboard. */
export const LEADERBOARD_CUES = new Set([
  "led",
  "leads",
  "lead",
  "leader",
  "leaders",
  "leading",
  "top",
  "leaderboard",
  "rank",
  "ranking",
  "rankings",
  ...RANK_DIRECTION.keys(),
]);

const DEFAULT_LEADERBOARD_LIMIT = 10;
const MAX_LEADERBOARD_LIMIT = 100;
/** A rate, per-game or fewest-first ranking needs a floor of plays, or a player with one play tops it. */
const LEADERBOARD_MIN_PLAYS = 100;
/** A weekly ranking needs a game's worth of plays to qualify, not a season's. */
const WEEKLY_LEADERBOARD_MIN_PLAYS = 10;

/** "top 5", "fewest 5": the number after a ranking word is the limit, not a stat or a season. */
export function readLimit(tokens: readonly string[]): { limit: number; at: number } | { reason: string } | null {
  const at = tokens.findIndex((t, i) => (t === "top" || RANK_DIRECTION.has(t)) && /^\d+$/.test(tokens[i + 1] ?? ""));
  if (at < 0) {
    return null;
  }
  const limit = Number(tokens[at + 1]);
  if (limit < 1 || limit > MAX_LEADERBOARD_LIMIT) {
    return { reason: `A leaderboard shows 1 to ${MAX_LEADERBOARD_LIMIT} rows.` };
  }
  return { limit, at: at + 1 };
}

/** The role whose plays a floor counts: carries are a rusher's, targets a receiver's, attempts a passer's. */
const MIN_UNITS: Readonly<Record<string, PlayerRole>> = {
  carries: "rusher",
  carry: "rusher",
  rushes: "rusher",
  attempts: "passer",
  attempt: "passer",
  passes: "passer",
  dropbacks: "passer",
  targets: "receiver",
  target: "receiver",
};

/** "min 100 carries", "minimum 50 targets", "at least 200 attempts": the floor, its role, and its words. */
export function readMinimum(tokens: readonly string[]): { min: number; role: PlayerRole; at: number[] } | null {
  for (let i = 0; i < tokens.length; i++) {
    const lead = tokens[i] === "min" || tokens[i] === "minimum" ? [i] : tokens[i] === "at" && tokens[i + 1] === "least" ? [i, i + 1] : null;
    if (!lead) {
      continue;
    }
    const n = lead.length + i;
    const role = MIN_UNITS[tokens[n + 1] ?? ""];
    if (/^\d+$/.test(tokens[n] ?? "") && role) {
      return { min: Number(tokens[n]), role, at: [...lead, n, n + 1] };
    }
  }
  return null;
}

/** "in a single game", "in one game": a ranking of single games (split by week). The words' positions, or null. */
export function readSingleGame(tokens: readonly string[]): number[] | null {
  const at = tokens.findIndex((t, i) => (t === "single" || t === "one") && tokens[i + 1] === "game");
  return at < 0 ? null : [at, at + 1];
}

/**
 * Highest first unless the question asks otherwise; asking both ways, or "best" of a neutral stat, is
 * unclear. `allowed` ranks defenses, where what is allowed is better the other way round.
 */
function rankDirection(tokens: readonly string[], metric: string, allowed = false): "asc" | "desc" | { reason: string } {
  const stated = getStatById(metric)?.better;
  const better = stated && allowed ? (stated === "higher" ? "lower" : "higher") : stated;
  const asked = new Set<"asc" | "desc">();
  for (const token of tokens) {
    const cue = RANK_DIRECTION.get(token);
    if (cue === "desc" || cue === "asc") {
      asked.add(cue);
    } else if (cue) {
      if (!better) {
        return {
          reason: `"${token}" has no clear meaning for ${getStatById(metric)?.label ?? metric}; ask for the highest or lowest.`,
        };
      }
      asked.add((cue === "best") === (better === "higher") ? "desc" : "asc");
    }
  }
  if (asked.size > 1) {
    return { reason: "It asks for both the highest and the lowest." };
  }
  return [...asked][0] ?? "desc";
}

/**
 * The ranking a question asks for, ordered by its first stat. The floor keeps a one-play player off the
 * top of a rate, per-game or fewest-first ranking; a total ranked highest first needs none, and a team
 * always has hundreds of plays. A floor in words must count the ranked stat's own plays.
 */
export function leaderboardFor(
  tokens: readonly string[],
  metric: string,
  granularity: GranularityMode,
  scope: { teams: boolean; defense: boolean; weekly: boolean },
): Leaderboard | { reason: string } {
  const direction = rankDirection(tokens, metric, scope.teams && scope.defense);
  if (typeof direction !== "string") {
    return direction;
  }
  const limit = readLimit(tokens);
  if (limit && "reason" in limit) {
    return limit;
  }
  const minimum = readMinimum(tokens);
  const stat = getStatById(metric);
  // A derived stat's floor is its volume, which counts one role's plays when it is a single stat.
  const counted = stat?.source === "derived" ? getStatById(stat.volume ?? "") : stat;
  if (minimum && (scope.teams || counted?.source !== "pbp" || counted.playerRole !== minimum.role || counted.teamOnly)) {
    return { reason: `The minimum counts a ${minimum.role}'s plays, which ${stat?.label ?? metric} does not.` };
  }
  const who = readWho(tokens);
  if (who.reason) {
    return { reason: who.reason };
  }
  // "rushers by EPA" means the rushers' own EPA; a stat with no such member must already count that role.
  const ranked = who.role && stat?.family ? familyMember(metric, who.role) : metric;
  const rankedStat = getStatById(ranked);
  if (who.role && (scope.teams || rankedStat?.source !== "pbp" || rankedStat.playerRole !== who.role)) {
    return { reason: `It asks for ${who.role}s, which ${stat?.label ?? metric} does not count.` };
  }
  if (scope.teams && (who.position || who.rookie)) {
    return { reason: "A team ranking cannot be narrowed to a position or to rookies." };
  }
  const floor = scope.weekly ? WEEKLY_LEADERBOARD_MIN_PLAYS : LEADERBOARD_MIN_PLAYS;
  const needsFloor = granularity !== "total" || direction === "asc";
  const minPlays = minimum ? minimum.min : scope.teams || !needsFloor ? 0 : floor;
  return {
    order: { metric: ranked, direction },
    limit: limit?.limit ?? DEFAULT_LEADERBOARD_LIMIT,
    minPlays,
    position: who.position,
    rookie: who.rookie,
  };
}
