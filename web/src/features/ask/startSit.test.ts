import { describe, expect, it } from "vitest";

import type { PlayerDictionaryRow } from "@/stat/lib/schemas/players";

import { parseStartSit, readStartSit } from "./startSit";

const row = (gsis_id: string, display_name: string, position = "WR", team = "KC"): PlayerDictionaryRow => ({
  gsis_id, display_name, search_key: display_name.toLowerCase(), position, team,
});
const DICT = [
  row("kelce", "Travis Kelce", "TE"),
  row("kittle", "George Kittle", "TE", "SF"),
  row("allen-qb", "Josh Allen", "QB", "BUF"),
  row("allen-lb", "Josh Allen", "LB", "JAX"),
  row("hill", "Tyreek Hill"),
];

describe("parseStartSit", () => {
  it.each([
    ["start Kelce or Kittle", ["Kelce", "Kittle"]],
    ["Should I start Kelce or Kittle?", ["Kelce", "Kittle"]],
    ["who should I start, Kelce or Kittle this week", ["Kelce", "Kittle"]],
    ["Kelce or Kittle this week", ["Kelce", "Kittle"]],
    ["should I sit Kelce or Kittle", ["Kelce", "Kittle"]],
    ["start Travis Kelce over George Kittle", ["Travis Kelce", "George Kittle"]],
  ])("reads %s", (question, sides) => {
    expect(parseStartSit(question)).toMatchObject({ a: sides[0], b: sides[1] });
  });

  it.each([
    "Kelce or Kittle receptions in 2023",
    "Mahomes passing yards",
    "start Mahomes passing yards",
    "who led the league in start-of-game targets",
    "trade Kelce for Kittle",
    "start Kelce or Kittle or Hill",
    "Kelce vs Kittle receptions per game",
    "Mahomes or Allen passing yards in 2023",
    "Chase vs Jefferson receiving yards",
    "",
  ])("refuses %s", (question) => {
    expect(parseStartSit(question)).toBeNull();
  });
});

describe("readStartSit", () => {
  it("ignores questions that are not start/sit", () => {
    expect(readStartSit("Kelce receptions", DICT)).toEqual({ status: "none" });
  });

  it("resolves both names to gsis ids", () => {
    expect(readStartSit("start Kelce or Kittle", DICT)).toEqual({
      status: "resolved",
      outcome: { kind: "start_sit", a: "kelce", b: "kittle" },
      names: { kelce: "Travis Kelce", kittle: "George Kittle" },
    });
  });

  it("asks which player for a namesake", () => {
    const read = readStartSit("start Josh Allen or Kelce", DICT);
    expect(read.status).toBe("choose");
    if (read.status === "choose") {
      expect(read.sure.map((p) => p.gsis_id)).toEqual(["kelce"]);
      expect(read.unsure[0]?.candidates.map((p) => p.gsis_id)).toEqual(["allen-qb", "allen-lb"]);
    }
  });

  it.each([
    "Kelce vs Kittle receptions per game",
    "Mahomes or Allen passing yards in 2023",
    "Kelce or Kittle receptions this week",
    "Kelce or Kittle receptions per game this week",
    "start Kelce or Kittle receptions",
  ])("leaves the stat comparison %s to the stat path", (question) => {
    expect(readStartSit(question, DICT)).toEqual({ status: "none" });
  });

  it("names the side it cannot find", () => {
    const read = readStartSit("start Kelce or Nobodyson", DICT);
    expect(read).toMatchObject({ status: "message" });
    expect(read.status === "message" && read.text).toContain("Nobodyson");
  });

  it("refuses the same player twice", () => {
    const read = readStartSit("start Kelce or Travis Kelce", DICT);
    expect(read).toMatchObject({ status: "message" });
    expect(read.status === "message" && read.text).toMatch(/same player/);
  });
});
