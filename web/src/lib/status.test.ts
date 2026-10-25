import type { Status } from "@/api/types";
import { bannerMessages, liveLabel } from "./status";

const base: Status = { freshness: [], missing_layers: [], data_version: "v1", simulation_behind_inputs: null,
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
      simulation_behind_inputs: "Season odds are older than sleeper: the last refresh may have failed",
    };
    expect(bannerMessages(status)).toEqual([
      "Stale data: Sleeper (30 hours old). Run `make refresh`.",
      "Running without: injury model, outlook. Run `make refresh`.",
      "Season odds are older than sleeper: the last refresh may have failed. Run `make refresh`.",
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
