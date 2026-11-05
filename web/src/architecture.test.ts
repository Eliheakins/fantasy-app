import { readdirSync, readFileSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { describe, expect, test } from "vitest";

const SRC = __dirname;
const IMPORT = /(?:from|import\(|vi\.mock\()\s*["']([^"']+)["']/g;

function sourceFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((e) =>
    e.isDirectory() ? sourceFiles(join(dir, e.name)) : /\.tsx?$/.test(e.name) ? [join(dir, e.name)] : [],
  );
}

/** Each import in files under `folder` as [file, target], both relative to src and without extension. */
function importsUnder(folder: string): [string, string][] {
  return sourceFiles(join(SRC, folder)).flatMap((file) => {
    const specs = [...readFileSync(file, "utf8").matchAll(IMPORT)].map((m) => m[1] ?? "");
    return specs
      .filter((s) => s.startsWith("@/") || s.startsWith("."))
      .map((s): [string, string] => [
        relative(SRC, file),
        (s.startsWith("@/") ? s.slice(2) : relative(SRC, resolve(dirname(file), s))).replace(/\.tsx?$/, ""),
      ]);
  });
}

const offenders = (folder: string, forbidden: RegExp, skip?: RegExp) =>
  importsUnder(folder)
    .filter(([file, target]) => !skip?.test(file) && forbidden.test(target))
    .map(([file, target]) => `${file} -> ${target}`);

describe("layers", () => {
  test("a page does not import another page", () => {
    expect(offenders("pages", /^pages\//, /\.test\.tsx?$/)).toEqual([]);
  });
  test("lib and layout components do not import features or pages", () => {
    expect([...offenders("lib", /^(features|pages)\//), ...offenders("components", /^(features|pages)\//)]).toEqual([]);
  });
  test("stat engine, lib and config stay free of the UI and the fantasy API", () => {
    // api/schema is allowed: generated types only, used by nlqIntent.ts to pin zod to the backend at compile time.
    expect(offenders("stat", /^(features|components|pages)\/|^api\/(?!schema$)/, /^stat\/react\//)).toEqual([]);
  });
  test("moves/trade does not import the rest of moves, so the two do not form a cycle", () => {
    expect(offenders("features/moves/trade", /^features\/moves\/(?!trade\/)[^/]+$/)).toEqual([]);
  });
});
