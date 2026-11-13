import "@testing-library/jest-dom/vitest";
import { takeUnexpected } from "./fakeApi";

// jsdom lacks the pointer-capture and scroll APIs Radix Select calls when it opens (node-env tests have no Element).
if (typeof Element !== "undefined") {
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.setPointerCapture ??= () => {};
  Element.prototype.releasePointerCapture ??= () => {};
  Element.prototype.scrollIntoView ??= () => {};
}

// A request no stub answered fails the test that made it (`fakeApi.ts`); one left over from an earlier test does not.
beforeEach(() => void takeUnexpected());
afterEach(() => {
  const extra = takeUnexpected();
  if (extra.length > 0) throw new Error(`unexpected request: ${extra.join(", ")}`);
});
