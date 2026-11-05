import { createParquetLoader } from "./parquetColumns";

describe("createParquetLoader read errors", () => {
  it("point at building the data, not at starting the server", async () => {
    const load = createParquetLoader(() => Promise.reject(new Error("boom")), {});

    const error = await load({ year: 2023, url: "/api/stat/data/nfl_pbp_2023.parquet" }, "yards_gained").catch(
      (e: Error) => e,
    );

    expect((error as Error).message).toContain("(boom). Build the data with: make stat-data, and start the app with: make serve");
  });
});
