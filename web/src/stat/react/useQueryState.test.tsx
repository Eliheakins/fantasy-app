import { act, render, screen } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router";
import { ManifestContext } from "./manifest";
import { useQueryState } from "./useQueryState";

let api: ReturnType<typeof useQueryState>;
function Probe() {
  api = useQueryState();
  return <p data-testid="search">{useLocation().search}</p>;
}

function renderAt(entry: string) {
  render(
    <MemoryRouter initialEntries={[entry]}>
      <ManifestContext.Provider value={{ manifest: null, seasons: [2026] }}>
        <Probe />
      </ManifestContext.Provider>
    </MemoryRouter>,
  );
}

const params = () => new URLSearchParams(screen.getByTestId("search").textContent ?? "");

describe("useQueryState", () => {
  it("keeps league and team when the query is edited", () => {
    renderAt("/explore?league=a&team=2&s=rec_yards");

    act(() => api.toggleStatId("rec_receptions"));

    expect(params().getAll("s")).toEqual(["rec_yards", "rec_receptions"]);
    expect(params().get("league")).toBe("a");
    expect(params().get("team")).toBe("2");
  });

  it("keeps league and team when Ask shows another query", () => {
    renderAt("/explore?league=a&team=2&s=rec_yards");

    act(() => api.showQuery({ ...api.state, stats: ["rec_receptions"] }, "who caught the most"));

    expect(params().get("q")).toBe("who caught the most");
    expect(params().getAll("s")).toEqual(["rec_receptions"]);
    expect(params().get("league")).toBe("a");
    expect(params().get("team")).toBe("2");
  });
});
