import { currentSeason, statLink } from "./statLink";

const BASE = "http://stat.test";
const link = (position: string, gsisId: string | null = "00-0033873", base = BASE) =>
  statLink({ gsisId, position, season: 2026, base });

describe("statLink", () => {
  it("opens a WR's weekly receiving log for the season", () => {
    expect(link("WR")).toBe(
      "http://stat.test/explore?p=00-0033873&s=rec_receptions&s=rec_yards&f=season-2026&f=stype-reg&by=week&g=total",
    );
  });
  it("uses the receiving set for a TE", () => {
    expect(link("TE")).toBe(link("WR"));
  });
  it("uses passing stats for a QB and rushing plus receiving for an RB", () => {
    expect(link("QB")).toContain("&s=pass_yards&s=pass_tds&");
    expect(link("RB")).toContain("&s=rush_yards&s=rush_tds&s=rec_receptions&s=rec_yards&");
  });
  it("has no link without a gsis id, or for K and DEF", () => {
    expect(link("WR", null)).toBeNull();
    expect(link("WR", "")).toBeNull();
    expect(link("K")).toBeNull();
    expect(link("DEF")).toBeNull();
  });
  it("matches the position case-insensitively and ignores inherited object keys", () => {
    expect(link("wr")).toBe(link("WR"));
    expect(link("constructor")).toBeNull();
  });
  it("trims trailing slashes from the base", () => {
    expect(link("QB", "00-1", "http://stat.test//")).toMatch(/^http:\/\/stat\.test\/explore\?/);
  });
  it("takes the season from the argument", () => {
    expect(statLink({ gsisId: "00-1", position: "QB", season: 2031, base: BASE })).toContain("f=season-2031&");
  });
});

describe("currentSeason", () => {
  it("is the calendar year from September, the previous year until then", () => {
    expect(currentSeason(new Date(2026, 10, 4))).toBe(2026);
    expect(currentSeason(new Date(2027, 1, 10))).toBe(2026);
    expect(currentSeason(new Date(2027, 7, 31))).toBe(2026);
    expect(currentSeason(new Date(2027, 8, 1))).toBe(2027);
  });
});
