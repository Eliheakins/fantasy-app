import { describe, expect, it } from "vitest";

import { createLatestRunner } from "./latestRun";

function deferred<T>() {
  let resolve!: (v: T) => void;
  const promise = new Promise<T>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}

describe("createLatestRunner", () => {
  it("returns the result of the only run", async () => {
    const run = createLatestRunner();

    expect(await run(async () => 7)).toEqual({ stale: false, value: 7 });
  });

  it("reports an older, slower run as stale so it cannot overwrite the newer result", async () => {
    const run = createLatestRunner();
    const slow = deferred<string>();

    const older = run(() => slow.promise);
    const newer = run(async () => "new");
    slow.resolve("old");

    expect(await newer).toEqual({ stale: false, value: "new" });
    expect(await older).toEqual({ stale: true });
  });

  it("aborts the previous run's signal when a new run starts", async () => {
    const run = createLatestRunner();
    let firstSignal!: AbortSignal;

    void run(async (signal) => {
      firstSignal = signal;
      return 1;
    });
    await run(async () => 2);

    expect(firstSignal.aborted).toBe(true);
  });

  it("treats an abort error from a superseded run as stale, not a failure", async () => {
    const run = createLatestRunner();

    const older = run(async (signal) => {
      await new Promise((_, reject) => signal.addEventListener("abort", () => reject(signal.reason)));
      return "never";
    });
    await run(async () => "new");

    expect(await older).toEqual({ stale: true });
  });

  it("makes the running task stale when cancelled", async () => {
    const run = createLatestRunner();
    const slow = deferred<string>();

    const pending = run(() => slow.promise);
    run.cancel();
    slow.resolve("late");

    expect(await pending).toEqual({ stale: true });
  });

  it("rethrows a real error from the latest run", async () => {
    const run = createLatestRunner();

    await expect(
      run(async () => {
        throw new Error("boom");
      }),
    ).rejects.toThrow("boom");
  });

  it("swallows a real error from a superseded run", async () => {
    const run = createLatestRunner();
    let fail!: (e: Error) => void;
    const failing = new Promise<string>((_, reject) => {
      fail = reject;
    });

    const older = run(() => failing);
    await run(async () => "new");
    fail(new Error("late failure"));

    expect(await older).toEqual({ stale: true });
  });
});
