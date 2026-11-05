import "@testing-library/jest-dom/vitest";

// jsdom lacks the pointer-capture and scroll APIs Radix Select calls when it opens (node-env tests have no Element).
if (typeof Element !== "undefined") {
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.setPointerCapture ??= () => {};
  Element.prototype.releasePointerCapture ??= () => {};
  Element.prototype.scrollIntoView ??= () => {};
}
