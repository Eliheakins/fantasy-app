import { describe, expect, it } from "vitest";

import { buildFilterChipGroups } from "@/stat/config/queryBuilderOptions";
import { STAT_DEFINITIONS } from "@/stat/config/statDictionary";

import {
  columnsIn,
  compileAggregateExpression,
  compileRowExpression,
  parseExpression,
  type Columns,
} from "./expression";

const range = (n: number) => Array.from({ length: n }, (_, i) => i);

function aggregate(sql: string, cols: Columns, rows = range(Object.values(cols)[0]?.length ?? 0)) {
  return compileAggregateExpression(parseExpression(sql), cols)(rows);
}

function rowValues(sql: string, cols: Columns, n: number) {
  const fn = compileRowExpression(parseExpression(sql), cols);
  return range(n).map(fn);
}

describe("aggregates follow SQL null rules", () => {
  const cols: Columns = { a: [1, 2, null, 5], b: [0, 0, 0, 0], flag: [true, false, true, null] };

  it("SUM and AVG skip nulls, and are null when nothing is left", () => {
    expect(aggregate("SUM(a)", cols)).toBe(8);
    expect(aggregate("AVG(a)", cols)).toBeCloseTo(8 / 3);
    expect(aggregate("SUM(a)", cols, [2])).toBeNull();
    expect(aggregate("AVG(a)", cols, [])).toBeNull();
  });

  it("COUNT(*) counts rows and COUNT(col) counts non-null values", () => {
    expect(aggregate("COUNT(*)", cols)).toBe(4);
    expect(aggregate("COUNT(a)", cols)).toBe(3);
  });

  it("NULLIF turns a zero denominator into null, and any division by zero is null", () => {
    expect(aggregate("SUM(a) / NULLIF(SUM(b), 0)", cols)).toBeNull();
    expect(aggregate("SUM(a) / SUM(b)", cols)).toBeNull();
    expect(aggregate("SUM(a) / NULLIF(COUNT(*), 0) * 100", cols)).toBe(200);
  });

  it("CAST ... AS DOUBLE and arithmetic precedence", () => {
    expect(aggregate("SUM(a) / NULLIF(CAST(COUNT(*) AS DOUBLE), 0)", cols)).toBe(2);
    expect(aggregate("1 + 2 * 3 - (4 - 1)", cols)).toBe(4);
    expect(aggregate("-SUM(a) + 10", cols)).toBe(2);
  });

  it("CASE WHEN falls through to ELSE when the condition is null", () => {
    expect(aggregate("AVG(CASE WHEN a >= 2 THEN 1 ELSE 0 END)", cols)).toBe(0.5);
    expect(aggregate("SUM(CASE WHEN a >= 2 THEN 10 END)", cols)).toBe(20);
  });

  it("averages booleans as 0 and 1", () => {
    expect(aggregate("AVG(flag)", cols)).toBeCloseTo(2 / 3);
  });
});

describe("row predicates", () => {
  it("compares strings, numbers and quoted quotes", () => {
    const cols: Columns = { season_type: ["REG", "POST", null], name: ["O'Brien", "x", "y"] };

    expect(rowValues("season_type = 'REG'", cols, 3)).toEqual([true, false, null]);
    expect(rowValues("name = 'O''Brien'", cols, 3)).toEqual([true, false, false]);
  });

  it("uses three-valued AND and OR", () => {
    const cols: Columns = { x: [1, null, null], y: [1, 1, 5] };

    expect(rowValues("x = 1 AND y = 1", cols, 3)).toEqual([true, null, false]);
    expect(rowValues("x = 1 OR y = 1", cols, 3)).toEqual([true, true, null]);
    expect(rowValues("x = 9 AND y = 1", cols, 3)).toEqual([false, null, false]);
  });

  it("treats a boolean column as equal to TRUE and to 1", () => {
    const bools: Columns = { goal_to_go: [true, false, null] };
    const ints: Columns = { goal_to_go: [1, 0, null] };
    const sql = "(goal_to_go = TRUE OR goal_to_go = 1)";

    expect(rowValues(sql, bools, 3)).toEqual([true, false, null]);
    expect(rowValues(sql, ints, 3)).toEqual([true, false, null]);
  });

  it("matches LIKE case-sensitively with % and _, and escapes regex characters", () => {
    const cols: Columns = {
      p: ["1 RB, 1 TE, 3 WR", "1 rb, 1 te, 3 wr", "x.y", "xzy", null],
    };

    expect(rowValues("p LIKE '%1 RB, 1 TE, 3 WR%'", cols, 5)).toEqual([true, false, false, false, null]);
    expect(rowValues("p LIKE 'x.y'", cols, 5)).toEqual([false, false, true, false, null]);
    expect(rowValues("p LIKE 'x_y'", cols, 5)).toEqual([false, false, true, true, null]);
    expect(rowValues("p NOT LIKE 'x%'", cols, 5)).toEqual([true, true, false, false, null]);
  });

  it("compares numbers with every operator and NOT", () => {
    const cols: Columns = { n: [1, 2, 3] };

    expect(rowValues("n <> 2", cols, 3)).toEqual([true, false, true]);
    expect(rowValues("n != 2", cols, 3)).toEqual([true, false, true]);
    expect(rowValues("n >= 2 AND n < 3", cols, 3)).toEqual([false, true, false]);
    expect(rowValues("NOT n = 2", cols, 3)).toEqual([true, false, true]);
  });
});

describe("errors", () => {
  const cols: Columns = { a: [1] };

  it("names the unsupported construct", () => {
    expect(() => parseExpression("a ~ 1")).toThrow(/Unsupported/);
    expect(() => parseExpression("SUM(a) extra")).toThrow(/Unexpected/);
    expect(() => parseExpression("FOO(a)")).toThrow(/Unsupported function/);
    expect(() => parseExpression("a =")).toThrow(/Unexpected end/);
  });

  it("only accepts a string literal as a LIKE pattern", () => {
    expect(() => parseExpression("a LIKE b")).toThrow(/string literal/);
    expect(() => parseExpression("a LIKE 'x' || 'y'")).toThrow();
  });

  it("rejects a column that was not loaded", () => {
    expect(() => compileRowExpression(parseExpression("missing = 1"), cols)).toThrow(/Column 'missing'/);
  });

  it("rejects a bare column in an aggregate expression and an aggregate in a row expression", () => {
    expect(() => compileAggregateExpression(parseExpression("a + 1"), cols)).toThrow(/outside an aggregate/);
    expect(() => compileRowExpression(parseExpression("SUM(a) > 1"), cols)).toThrow(/aggregate/i);
  });
});

describe("columnsIn", () => {
  it("lists each column once", () => {
    expect(columnsIn(parseExpression("SUM(a) / NULLIF(SUM(b), 0) + SUM(a)")).sort()).toEqual(["a", "b"]);
    expect(columnsIn(parseExpression("COUNT(*)"))).toEqual([]);
  });
});

describe("the app's own expressions", () => {
  const everyColumn = new Proxy({} as Columns, { get: () => [1], has: () => true });

  it("parses and compiles every metric and play filter in metrics.json", () => {
    for (const stat of STAT_DEFINITIONS) {
      expect(() => compileAggregateExpression(parseExpression(stat.base_sql), everyColumn), stat.id).not.toThrow();
      if (stat.playFilter) {
        expect(() => compileRowExpression(parseExpression(stat.playFilter!), everyColumn), stat.id).not.toThrow();
      }
    }
  });

  it("parses and compiles every filter chip predicate", () => {
    const groups = buildFilterChipGroups([2023, 2024]);

    const predicates = groups.flatMap((g) => g.options.map((o) => ({ id: o.id, sql: o.predicate })));
    expect(predicates.length).toBeGreaterThan(20);
    for (const { id, sql } of predicates) {
      expect(() => compileRowExpression(parseExpression(sql), everyColumn), id).not.toThrow();
    }
  });
});
