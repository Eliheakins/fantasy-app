import { getStatById, type PlayerRole } from "@/stat/config/statDictionary";
import { MAX_SELECTED_STATS } from "@/stat/lib/queryUrl";

import { type PlayerMatch, tokenize } from "../resolvePlayers";
import type { Entities } from "./entities";
import type { FilterReads } from "./filters";
import { ambiguous, proceed, type Stage, stop, type WordMask } from "./types";
import {
  FILLER,
  GENERIC_STAT,
  GENERIC_WORDS,
  type GenericWord,
  LEADERBOARD_WORDS,
  MAIN_ROLE,
  ROLE_BY_CATEGORY,
  ROLES_BY_POSITION,
  STAT_LINES,
  STAT_LINE_WORDS,
  THROW_WORDS,
  unique,
} from "./vocab";

interface StatPlace {
  at: number;
  id: string;
}

/** The bare words and verbs that stand in for a stat, which `chooseStats` settles. */
export interface StatWords {
  /** "yards", "touchdowns": which role they belong to depends on the rest. */
  generic: { at: number; word: GenericWord }[];
  /** "threw": settles a bare "yards" as the passer's. */
  threw: boolean;
  /** "Tyreek Hill 2023 stats": the usual stats for the player's position. */
  statLine: boolean;
}

const candidatePositions = (match: PlayerMatch): string[] => match.candidates.flatMap((c) => (c.position ? [c.position] : []));

/** The role a player is mainly known for, when all of a match's candidates agree on one. */
function mainRoles(matches: readonly PlayerMatch[]): Set<PlayerRole> {
  const roles = new Set<PlayerRole>();
  for (const match of matches) {
    for (const position of candidatePositions(match)) {
      const role = MAIN_ROLE[position];
      if (role) {
        roles.add(role);
      }
    }
  }
  return roles;
}

/** Marks every word as read or leaves it; a word nothing read makes the parser unsure. */
export function readStatWords(e: Entities, filters: FilterReads, used: WordMask): Stage<StatWords> {
  const { tokens, sortedMatches, isLeaderboard } = e;
  const { found, years } = filters;
  const generic: StatWords["generic"] = [];
  tokens.forEach((token, at) => {
    const word = GENERIC_WORDS[token];
    if (!used[at] && word) {
      used[at] = true;
      generic.push({ at, word });
    }
  });

  let threw = false;
  tokens.forEach((token, at) => {
    if (!used[at] && THROW_WORDS.has(token)) {
      used[at] = true;
      threw = true;
    }
  });

  if (isLeaderboard) {
    tokens.forEach((token, at) => {
      used[at] ||= LEADERBOARD_WORDS.has(token);
    });
  }

  let statLine = false;
  if (sortedMatches.length === 1 && found.every((f) => f.piece.kind !== "stat") && generic.length === 0) {
    tokens.forEach((token, at) => {
      if (!used[at] && STAT_LINE_WORDS.has(token)) {
        used[at] = true;
        statLine = true;
      }
    });
  }

  const leftover = tokens.filter((token, at) => !used[at] && !FILLER.has(token));
  if (leftover.length > 0) {
    const unrecognized = unique(leftover);
    return stop(ambiguous(`I didn't understand: ${unrecognized.join(", ")}.`, unrecognized));
  }

  // Several players: details between their names may belong to only one of them.
  if (sortedMatches.length > 1) {
    const afterFirst = sortedMatches[0]!.start + tokenize(sortedMatches[0]!.phrase).length;
    const beforeLast = sortedMatches[sortedMatches.length - 1]!.start;
    const details = [...found.map((f) => f.at), ...years.map((y) => y.at), ...generic.map((g) => g.at)];
    if (details.some((at) => at >= afterFirst && at < beforeLast)) {
      return stop(ambiguous("Details sit between the players' names, so it is unclear which player they belong to."));
    }
  }
  return proceed({ generic, threw, statLine });
}

/** What a bare "yards" or "touchdowns" means here, or an ambiguity when the role is not settled. */
function genericStats(e: Entities, statAt: readonly StatPlace[], words: StatWords): Stage<StatPlace[]> {
  // "passing yards and touchdowns": the named stat settles the role. Otherwise only a receiver's
  // "yards" and "touchdowns" have one reading, since quarterbacks and backs both run and throw or catch.
  const named = unique([
    ...statAt.flatMap((s) => ROLE_BY_CATEGORY[getStatById(s.id)?.category ?? ""] ?? []),
    ...(words.threw ? (["passer"] as const) : []),
  ]);
  const role: PlayerRole | undefined = named.length === 1 ? named[0] : undefined;
  const playerRoles = mainRoles(e.matches);
  const fallback = playerRoles.size === 1 ? [...playerRoles][0] : undefined;
  const places: StatPlace[] = [];
  for (const { at, word } of words.generic) {
    // "total yards" adds up passing, rushing and receiving, which no single stat does.
    const isTotal = e.tokens[at - 1] === "total";
    const id = role ? GENERIC_STAT[role][word] : fallback === "receiver" && !isTotal ? GENERIC_STAT.receiver[word] : null;
    if (!id) {
      return stop(ambiguous(`"${word}" could mean passing, rushing or receiving here.`));
    }
    places.push({ at, id });
  }
  return proceed(places);
}

/** Several names must each be able to have the stat, and the stats must share one kind. */
function checkPlayersFit(e: Entities, statIds: readonly string[]): Stage<null> {
  if (e.sortedMatches.length <= 1) {
    return proceed(null);
  }
  // A league stat (fantasy points) belongs to no position, so it settles no role.
  const statRoles = unique(
    statIds.flatMap((id) => {
      const stat = getStatById(id);
      return stat && stat.source === "pbp" ? [stat.playerRole] : [];
    }),
  );
  if (statRoles.length > 1) {
    return stop(ambiguous("It mixes players with different kinds of stat."));
  }
  // A second name that cannot have the stat is a mention, not a player to compare.
  const fits = (m: PlayerMatch) =>
    statRoles.length === 0 ||
    candidatePositions(m).some((position) => (ROLES_BY_POSITION[position] ?? []).some((r) => statRoles.includes(r)));
  return e.sortedMatches.every(fits) ? proceed(null) : stop(ambiguous("One of the names is not a player who could have that stat."));
}

/** The stats the question asks for, in reading order, from named stats, bare words and a stat line. */
export function chooseStats(e: Entities, filters: FilterReads, words: StatWords): Stage<string[]> {
  const statAt: StatPlace[] = filters.found.flatMap((f) => (f.piece.kind === "stat" ? [{ at: f.at, id: f.piece.id }] : []));
  if (words.generic.length > 0) {
    const places = genericStats(e, statAt, words);
    if (!places.ok) {
      return places;
    }
    statAt.push(...places.value);
  }

  if (words.statLine) {
    const positions = unique(candidatePositions(e.sortedMatches[0]!).flatMap((p) => (STAT_LINES[p] ? [p] : [])));
    if (positions.length !== 1) {
      return stop(ambiguous("A stat line needs one position, and this name has several or none."));
    }
    statAt.push(...STAT_LINES[positions[0]!]!.map((id, k) => ({ at: e.tokens.length + k, id })));
  }
  const statIds = unique(statAt.sort((a, b) => a.at - b.at).map((s) => s.id));
  if (statIds.length === 0) {
    return stop({ status: "unknown", reason: "No stat I know was named." });
  }
  if (statIds.length > MAX_SELECTED_STATS) {
    return stop(ambiguous(`That names more than ${MAX_SELECTED_STATS} stats.`));
  }
  const fit = checkPlayersFit(e, statIds);
  return fit.ok ? proceed(statIds) : fit;
}
