import { formatRunDate, runTicks } from "./logic";

describe("run axis labels", () => {
  it("formats a timestamp short, never ISO", () => {
    expect(formatRunDate("2026-10-23T15:49:00Z", "UTC")).toBe("Oct 23, 3 PM");
    expect(formatRunDate("garbage")).toBe("garbage");
  });

  it("keeps one tick per distinct label", () => {
    const runs = ["2026-10-23T15:10:00Z", "2026-10-23T15:40:00Z", "2026-10-24T15:10:00Z"];
    const label = (iso: string) => formatRunDate(iso, "UTC");
    expect(runTicks(runs, label)).toEqual([runs[0], runs[2]]);
  });

  it("thins long histories to the maximum", () => {
    const runs = Array.from({ length: 12 }, (_, i) => `2026-10-${String(10 + i)}T00:00:00Z`);
    expect(runTicks(runs, (iso) => iso, 4).length).toBeLessThanOrEqual(4);
  });
});
