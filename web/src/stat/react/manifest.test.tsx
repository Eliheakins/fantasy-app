import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ManifestProvider, seasonsOf, useManifest } from "./manifest";
import { fetchManifest } from "@/stat/lib/api";
import type { Manifest } from "@/stat/lib/schemas/manifest";

vi.mock("@/stat/lib/api", () => ({ fetchManifest: vi.fn() }));

const manifest = (seasons: number[]): Manifest => ({
  schema_version: 1,
  built_at: "2026-11-04T12:00:00+00:00",
  nflreadpy_version: "0.1.0",
  seasons: seasons.map((season) => ({ season, path: `nfl_pbp_${season}.parquet`, rows: 1, max_week: 9, has_participation: true })),
  player_index: null,
  player_game: null,
  players: null,
});

function Seasons() {
  return <p>seasons {useManifest().seasons.join(",")}</p>;
}

function renderProvider() {
  const client = new QueryClient();
  return render(
    <QueryClientProvider client={client}>
      <ManifestProvider>
        <Seasons />
      </ManifestProvider>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.mocked(fetchManifest).mockReset());

describe("seasonsOf", () => {
  it("lists each season once, oldest first", () => {
    expect(seasonsOf(manifest([2025, 2025, 2024]))).toEqual([2024, 2025]);
  });
});

describe("ManifestProvider", () => {
  it("shows a loading state, then gives children the seasons", async () => {
    vi.mocked(fetchManifest).mockResolvedValue(manifest([2026, 2025]));
    renderProvider();
    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(await screen.findByText("seasons 2025,2026")).toBeInTheDocument();
  });

  it("shows the error with a retry that fetches again", async () => {
    vi.mocked(fetchManifest)
      .mockRejectedValueOnce(new Error("No data manifest found."))
      .mockResolvedValueOnce(manifest([2025]));
    renderProvider();
    expect(await screen.findByRole("alert")).toHaveTextContent("No data manifest found.");

    await userEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByText("seasons 2025")).toBeInTheDocument();
    expect(fetchManifest).toHaveBeenCalledTimes(2);
  });
});
