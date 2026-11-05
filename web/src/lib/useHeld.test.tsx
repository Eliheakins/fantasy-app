import { renderHook } from "@testing-library/react";
import { useHeld } from "./useHeld";

describe("useHeld", () => {
  it("keeps the last value while held, drops it on a new scope", () => {
    const { result, rerender } = renderHook(({ v, hold, scope }) => useHeld(v, hold, scope), { initialProps: { v: "a", hold: false, scope: "x" } });
    rerender({ v: "pending", hold: true, scope: "x" });
    expect(result.current).toBe("a");
    rerender({ v: "pending", hold: true, scope: "y" });
    expect(result.current).toBe("pending");
    rerender({ v: "b", hold: false, scope: "y" });
    expect(result.current).toBe("b");
  });
});
