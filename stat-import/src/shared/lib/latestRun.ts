export type RunOutcome<T> = { stale: false; value: T } | { stale: true };

/**
 * Runs async tasks one "latest" at a time. Starting a run aborts the previous one's signal, and a
 * run that finishes (or fails) after a newer one started reports `stale`, so a slow old query can
 * never overwrite a newer result.
 */
export function createLatestRunner() {
  let current: AbortController | null = null;

  async function run<T>(task: (signal: AbortSignal) => Promise<T>): Promise<RunOutcome<T>> {
    current?.abort();
    const controller = new AbortController();
    current = controller;
    try {
      const value = await task(controller.signal);
      return current === controller ? { stale: false, value } : { stale: true };
    } catch (error) {
      if (current !== controller) {
        return { stale: true };
      }
      throw error;
    }
  }

  /** Makes whatever is running stale, e.g. when the inputs became invalid and no new run follows. */
  function cancel(): void {
    current?.abort();
    current = null;
  }

  return Object.assign(run, { cancel });
}
