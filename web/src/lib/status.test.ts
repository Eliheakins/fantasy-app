import type { StatHealth, Status } from "@/api/types";
import { bannerMessages, liveLabel } from "./status";

const base: Status = {
  freshness: [],
  missing_layers: [],
  data_version: "v1",
  simulation_behind_inputs: null,
  refresh_runs: [],
  live_refresh: { enabled: true, active: false, last_ok_at: null, last_error: null, interval_minutes: 10 },
};

describe("bannerMessages", () => {
  it("is empty when fresh", () => {
    const fresh = { ...base, freshness: [{ source: "Sleeper", updated_at: "", age_hours: 3 }] };
    expect(bannerMessages(fresh)).toEqual([]);
  });
  it("copies the Streamlit wording", () => {
    const status: Status = {
      freshness: [{ source: "Sleeper", updated_at: "", age_hours: 30.4 }],
      missing_layers: ["injury model", "outlook"],
      data_version: "v1",
      live_refresh: base.live_refresh,
      refresh_runs: [],
      simulation_behind_inputs: "Season odds are older than sleeper: the last refresh may have failed",
    };
    expect(bannerMessages(status)).toEqual([
      "Stale data: Sleeper (30 hours old). Run `make refresh`.",
      "Running without: injury model, outlook. Run `make refresh`.",
      "Season odds are older than sleeper: the last refresh may have failed. Run `make refresh`.",
    ]);
  });
});

describe("bannerMessages with refresh runs", () => {
  const run = (stage: string, status: "ok" | "failed", error: string | null = null) => ({
    stage,
    finished_at: "2026-11-05T06:00:00+00:00",
    status,
    error,
  });
  it("gives one notice per stage whose latest run failed", () => {
    const status: Status = {
      ...base,
      refresh_runs: [run("score", "ok"), run("digest", "failed", "RuntimeError('boom')"), run("market_values", "failed", "down")],
    };
    expect(bannerMessages(status)).toEqual([
      "Refresh step digest failed: RuntimeError('boom'). Run `make refresh`.",
      "Refresh step market_values failed: down. Run `make refresh`.",
    ]);
  });
  it("tolerates a server without refresh_runs", () => {
    const { refresh_runs: _omit, ...old } = base;
    expect(bannerMessages(old as unknown as Status)).toEqual([]);
  });
  it("cuts a long multi-line error to its first line and handles a null error", () => {
    const long = `${"x".repeat(300)}\nTraceback line 2`;
    const [a, b] = bannerMessages({ ...base, refresh_runs: [run("b_stage", "failed"), run("a_stage", "failed", long)] });
    expect(a).toBe(`Refresh step a_stage failed: ${"x".repeat(200)}.... Run \`make refresh\`.`);
    expect(b).toBe("Refresh step b_stage failed. Run `make refresh`.");
  });
  it("is quiet when every latest run is ok", () => {
    expect(bannerMessages({ ...base, refresh_runs: [run("score", "ok")] })).toEqual([]);
  });
});

describe("bannerMessages with stat data", () => {
  const now = new Date("2026-11-05T12:00:00Z");
  const health = (patch: Partial<StatHealth>): StatHealth => ({
    status: "ok",
    data_ready: true,
    data_through: "2026 week 9",
    built_at: "2026-11-05T00:00:00Z",
    seasons: [2026],
    ...patch,
  });
  it("is quiet when the stat shards are recent or health is unknown", () => {
    expect(bannerMessages(base, health({}), now)).toEqual([]);
    expect(bannerMessages(base, null, now)).toEqual([]);
  });
  it("lists stale stat data next to the other stale sources", () => {
    const status: Status = { ...base, freshness: [{ source: "Sleeper", updated_at: "", age_hours: 3 }] };
    const old = health({ built_at: "2026-11-02T12:00:00Z" });
    expect(bannerMessages(status, old, now)).toEqual(["Stale data: Stat data (72 hours old). Run `make refresh`."]);
    expect(bannerMessages({ ...status, freshness: [{ source: "Sleeper", updated_at: "", age_hours: 60 }] }, old, now)).toEqual([
      "Stale data: Sleeper (60 hours old), Stat data (72 hours old). Run `make refresh`.",
    ]);
  });
  it("says so when the stat shards were never built", () => {
    expect(bannerMessages(base, health({ data_ready: false, built_at: null, seasons: [] }), now)).toEqual([
      "Stat data is not built. Run `make refresh`.",
    ]);
  });
});

describe("liveLabel", () => {
  const now = new Date("2026-10-25T18:04:30Z");
  const live = (patch: Partial<Status["live_refresh"]>): Status => ({
    ...base,
    live_refresh: { ...base.live_refresh, active: true, last_ok_at: "2026-10-25T18:00:00Z", ...patch },
  });
  it("shows minutes since the last live tick", () => {
    expect(liveLabel(live({}), now)).toBe("live, updated 4 min ago");
  });
  it("is null when off, inactive, or no tick yet", () => {
    expect(liveLabel(live({ enabled: false }), now)).toBeNull();
    expect(liveLabel(live({ active: false }), now)).toBeNull();
    expect(liveLabel(live({ last_ok_at: null }), now)).toBeNull();
  });
  it("never shows negative minutes", () => {
    expect(liveLabel(live({ last_ok_at: "2026-10-25T18:10:00Z" }), now)).toBe("live, updated 0 min ago");
  });
});
