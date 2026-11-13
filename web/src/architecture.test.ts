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
  test("a feature does not import a page", () => {
    expect(offenders("features", /^pages\//, /\.test\.tsx?$/)).toEqual([]);
  });
  test.each(["lib", "components", "viz", "hooks", "api"])("shared %s/ does not import features or pages", (folder) => {
    expect(offenders(folder, /^(features|pages)\//)).toEqual([]);
  });
  test("stat engine, lib and config stay free of the UI and the fantasy API", () => {
    // api/schema is allowed: generated types only, used by nlqIntent.ts to pin zod to the backend at compile time.
    expect(offenders("stat", /^(features|components|pages)\/|^api\/(?!schema$)/, /^stat\/react\//)).toEqual([]);
  });
  test("moves and thisweek do not import each other; what they share lives in features/effects", () => {
    expect([...offenders("features/moves", /^features\/thisweek\//), ...offenders("features/thisweek", /^features\/moves\//)]).toEqual([]);
  });
  test("moves/trade does not import the rest of moves, so the two do not form a cycle", () => {
    expect(offenders("features/moves/trade", /^features\/moves\/(?!trade\/)[^/]+$/)).toEqual([]);
  });
});

describe("route boundary", () => {
  // Pages read the URL and hand features typed props. Explore and the Ask flow are the documented exception: their URL is
  // the stat query itself, kept by the stat kernel's useQueryState (web/CLAUDE.md, "Route boundary").
  const READS_URL = /\b(useLocation|useSearchParams|useSearchParam|useParams)\(/;
  const URL_IS_THE_QUERY = /^features\/(explore\/|ask\/useAsk\.ts$)/;
  test("a feature reads no URL state; its page passes it in", () => {
    const readers = sourceFiles(join(SRC, "features"))
      .map((file) => relative(SRC, file))
      .filter((file) => !/\.test\.tsx?$/.test(file) && !URL_IS_THE_QUERY.test(file))
      .filter((file) => READS_URL.test(readFileSync(join(SRC, file), "utf8")));
    expect(readers).toEqual([]);
  });
});
