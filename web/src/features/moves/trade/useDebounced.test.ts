import { act, renderHook } from "@testing-library/react";
import { useDebounced } from "./useDebounced";

describe("useDebounced", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());
  it("starts with the value and only follows a change after the delay, using the last value", () => {
    const { result, rerender } = renderHook(({ v }) => useDebounced(v, 500), { initialProps: { v: "a" } });
    expect(result.current).toBe("a");
    rerender({ v: "b" });
    act(() => void vi.advanceTimersByTime(300));
    rerender({ v: "c" });
    act(() => void vi.advanceTimersByTime(300));
    expect(result.current).toBe("a");
    act(() => void vi.advanceTimersByTime(200));
    expect(result.current).toBe("c");
  });
});
