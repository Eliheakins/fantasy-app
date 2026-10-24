import type { Status } from "@/api/types";
import { bannerMessages } from "./status";

const base: Status = { freshness: [], missing_layers: [], data_version: "v1", simulation_behind_inputs: null };

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
      simulation_behind_inputs: "Season odds are older than sleeper: the last refresh may have failed",
    };
    expect(bannerMessages(status)).toEqual([
      "Stale data: Sleeper (30 hours old). Run `make refresh`.",
      "Running without: injury model, outlook. Run `make refresh`.",
      "Season odds are older than sleeper: the last refresh may have failed. Run `make refresh`.",
    ]);
  });
});
