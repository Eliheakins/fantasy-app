import { describe, expect, it } from "vitest";

import type { PlayerDictionaryRow } from "@/stat/lib/schemas/players";

import { narrowByRoles, pickCandidate, resolvePlayers, tokenize } from "./resolvePlayers";

function row(gsis_id: string, display_name: string, position: string, team = "KC"): PlayerDictionaryRow {
  return { gsis_id, display_name, search_key: display_name.toLowerCase(), position, team };
}

const MAHOMES = row("m", "Patrick Mahomes", "QB");
const KELCE = row("k", "Travis Kelce", "TE");
const JOSH_ALLEN = row("ja", "Josh Allen", "QB", "BUF");
const KEENAN_ALLEN = row("ka", "Keenan Allen", "WR", "CHI");
const JOSH_ALLEN_LB = row("jl", "Josh Allen", "LB", "JAX");
const WILL_LEVIS = row("wl", "Will Levis", "QB", "TEN");
const OBJ = row("o", "Odell Beckham Jr.", "WR", "MIA");
const KYLE_LONG = row("kl", "Kyle Long", "OT", "CHI");
const DICT = [MAHOMES, KELCE, JOSH_ALLEN, KEENAN_ALLEN, JOSH_ALLEN_LB, WILL_LEVIS, OBJ, KYLE_LONG];

const phrases = (q: string) => resolvePlayers(q, DICT).map((m) => m.phrase);

describe("tokenize", () => {
  it("lowercases and drops apostrophes and punctuation", () => {
    expect(tokenize("Ja'Marr Chase, 2023!")).toEqual(["jamarr", "chase", "2023"]);
  });

  it("drops a possessive 's so 'Burrow's yards' still names Burrow", () => {
    expect(tokenize("Burrow's passing yards")).toEqual(["burrow", "passing", "yards"]);
    expect(tokenize("Burrow\u2019s passing yards")).toEqual(["burrow", "passing", "yards"]);
  });

  it("keeps apostrophes inside names that are not possessives", () => {
    expect(tokenize("D'Andre Swift and Ke'Shawn Vaughn")).toEqual(["dandre", "swift", "and", "keshawn", "vaughn"]);
  });
});

describe("resolvePlayers and everyday football words", () => {
  it("does not take 'long' or 'short' in '3rd and long' for a player's surname", () => {
    expect(phrases("Mahomes passing yards on 3rd and long")).toEqual(["mahomes"]);
  });

  it("still finds the player when the full name is used", () => {
    expect(phrases("Kyle Long snaps")).toEqual(["kyle long"]);
  });

  it("finds a player named in the possessive", () => {
    expect(phrases("What were Mahomes's passing yards in 2023")).toEqual(["mahomes"]);
  });
});

describe("resolvePlayers", () => {
  it("matches a bare surname", () => {
    expect(phrases("Mahomes passing yards in 2023")).toEqual(["mahomes"]);
  });

  it("matches a full name and uses its words only once", () => {
    const matches = resolvePlayers("Patrick Mahomes passing yards", DICT);

    expect(matches).toHaveLength(1);
    expect(matches[0]!.phrase).toBe("patrick mahomes");
    expect(matches[0]!.candidates).toEqual([MAHOMES]);
  });

  it("finds several players in reading order", () => {
    expect(phrases("compare Kelce and Mahomes")).toEqual(["kelce", "mahomes"]);
  });

  it("does not match a first name on its own", () => {
    expect(phrases("what will happen on third down")).toEqual([]);
  });

  it("ignores stopwords and very short words", () => {
    expect(phrases("pass yards per game in 2023")).toEqual([]);
  });

  it("returns namesakes as one match with all candidates", () => {
    const [match] = resolvePlayers("Allen rushing yards", DICT);

    expect(match!.candidates.map((c) => c.gsis_id).sort()).toEqual(["ja", "jl", "ka"]);
  });

  it("matches a full name that has a suffix in the roster", () => {
    expect(phrases("Odell Beckham receptions")).toEqual(["odell beckham"]);
    expect(phrases("Beckham Jr. receptions")).toEqual(["beckham"]);
  });

  it("returns nothing for an empty question or empty dictionary", () => {
    expect(resolvePlayers("", DICT)).toEqual([]);
    expect(resolvePlayers("Mahomes", [])).toEqual([]);
  });
});

describe("narrowByRoles / pickCandidate", () => {
  const [allen] = resolvePlayers("Allen", DICT);

  it("picks the QB when the stat is passing", () => {
    expect(pickCandidate(allen!, ["passer"])).toEqual(JOSH_ALLEN);
  });

  it("keeps only the receiver namesake when the stat is receiving", () => {
    expect(narrowByRoles(allen!.candidates, ["receiver"])).toEqual([KEENAN_ALLEN]);
  });

  it("stays ambiguous when several namesakes fit", () => {
    expect(pickCandidate(allen!, ["passer", "receiver"])).toBeNull();
  });

  it("falls back to every candidate when none fit the role", () => {
    const match = { phrase: "x", start: 0, candidates: [JOSH_ALLEN_LB] };

    expect(narrowByRoles(match.candidates, ["passer"])).toEqual([JOSH_ALLEN_LB]);
  });
});
