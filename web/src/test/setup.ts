import "@testing-library/jest-dom/vitest";
import { resetSession } from "@/lib/session";
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
// the session is a module store (`lib/session.tsx`): every test starts with nobody checked yet
beforeEach(resetSession);
afterEach(() => {
  const extra = takeUnexpected();
  if (extra.length > 0) throw new Error(`unexpected request: ${extra.join(", ")}`);
});
