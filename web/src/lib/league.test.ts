import type { ApiState } from "@/api/envelope";
import type { League } from "@/api/types";
import { trimLeagueNames } from "./league";

describe("trimLeagueNames", () => {
  it("trims trailing spaces for display and leaves other states alone", () => {
    const ready = { kind: "ready", data: [{ league_key: "a", name: "Colgate Fantasy Football " }] } as ApiState<League[]>;
    const out = trimLeagueNames(ready);
    expect(out.kind === "ready" && out.data[0]?.name).toBe("Colgate Fantasy Football");
    const loading: ApiState<League[]> = { kind: "loading" };
    expect(trimLeagueNames(loading)).toBe(loading);
  });
});
