/**
 * A small SQL-expression evaluator over columnar data. It reads the text in `metrics/metrics.json`
 * (aggregates such as `SUM(x) / NULLIF(COUNT(*), 0) * 100`) and the filter-chip predicates
 * (`down = 3 AND ydstogo <= 3`, `offense_personnel LIKE '%1 RB%'`) so the browser needs no SQL engine.
 *
 * Supported: numbers, 'strings', TRUE/FALSE/NULL, columns, + - * /, comparisons, AND/OR/NOT,
 * [NOT] LIKE, CASE WHEN, CAST(x AS DOUBLE), SUM/AVG/COUNT/NULLIF. Null handling follows SQL:
 * nulls propagate through arithmetic and comparisons, aggregates skip them, division by zero is null.
 * Anything else is a parse error that names what is unsupported.
 */

export type Value = number | string | boolean | null;
export type Columns = Record<string, ArrayLike<unknown>>;

type BinaryOp = "+" | "-" | "*" | "/" | "=" | "<>" | "<" | "<=" | ">" | ">=" | "AND" | "OR";

export type Node =
  | { kind: "num"; value: number }
  | { kind: "str"; value: string }
  | { kind: "bool"; value: boolean }
  | { kind: "null" }
  | { kind: "col"; name: string }
  | { kind: "neg"; arg: Node }
  | { kind: "not"; arg: Node }
  | { kind: "cast"; arg: Node }
  | { kind: "bin"; op: BinaryOp; left: Node; right: Node }
  | { kind: "like"; arg: Node; pattern: Node; negated: boolean }
  | { kind: "case"; whens: { when: Node; then: Node }[]; otherwise: Node | null }
  | { kind: "call"; fn: "SUM" | "AVG" | "COUNT" | "NULLIF"; args: Node[] };

// ---- parsing --------------------------------------------------------------

interface Token {
  type: "num" | "str" | "id" | "op" | "eof";
  text: string;
}

const KEYWORDS = new Set(["AND", "OR", "NOT", "LIKE", "CASE", "WHEN", "THEN", "ELSE", "END", "CAST", "AS", "TRUE", "FALSE", "NULL"]);
const FUNCTIONS = new Set(["SUM", "AVG", "COUNT", "NULLIF"]);
const TWO_CHAR_OPS = new Set(["<=", ">=", "<>", "!="]);
const ONE_CHAR_OPS = new Set(["=", "<", ">", "+", "-", "*", "/", "(", ")", ","]);

function tokenize(sql: string): Token[] {
  const tokens: Token[] = [];
  let i = 0;
  while (i < sql.length) {
    const ch = sql[i]!;
    if (/\s/.test(ch)) {
      i++;
    } else if (/\d/.test(ch)) {
      const m = /^\d+(\.\d+)?/.exec(sql.slice(i))!;
      tokens.push({ type: "num", text: m[0] });
      i += m[0].length;
    } else if (ch === "'") {
      let text = "";
      i++;
      for (;;) {
        if (i >= sql.length) {
          throw new Error("Unterminated string in expression");
        }
        if (sql[i] === "'" && sql[i + 1] === "'") {
          text += "'";
          i += 2;
        } else if (sql[i] === "'") {
          i++;
          break;
        } else {
          text += sql[i++];
        }
      }
      tokens.push({ type: "str", text });
    } else if (/[A-Za-z_]/.test(ch)) {
      const m = /^[A-Za-z_][A-Za-z0-9_]*/.exec(sql.slice(i))!;
      tokens.push({ type: "id", text: m[0] });
      i += m[0].length;
    } else if (TWO_CHAR_OPS.has(sql.slice(i, i + 2))) {
      tokens.push({ type: "op", text: sql.slice(i, i + 2) });
      i += 2;
    } else if (ONE_CHAR_OPS.has(ch)) {
      tokens.push({ type: "op", text: ch });
      i++;
    } else {
      throw new Error(`Unsupported character '${ch}' in expression`);
    }
  }
  tokens.push({ type: "eof", text: "" });
  return tokens;
}

class Parser {
  private pos = 0;

  constructor(private readonly tokens: Token[]) {}

  parse(): Node {
    const node = this.or();
    if (this.peek().type !== "eof") {
      throw new Error(`Unexpected '${this.peek().text}' in expression`);
    }
    return node;
  }

  private peek(): Token {
    return this.tokens[this.pos]!;
  }

  private next(): Token {
    return this.tokens[this.pos++]!;
  }

  private isWord(word: string): boolean {
    const t = this.peek();
    return t.type === "id" && t.text.toUpperCase() === word;
  }

  private isOp(op: string): boolean {
    const t = this.peek();
    return t.type === "op" && t.text === op;
  }

  private eatWord(word: string): boolean {
    if (this.isWord(word)) {
      this.pos++;
      return true;
    }
    return false;
  }

  private expectOp(op: string): void {
    if (!this.isOp(op)) {
      this.fail();
    }
    this.pos++;
  }

  private expectWord(word: string): void {
    if (!this.eatWord(word)) {
      this.fail();
    }
  }

  private fail(): never {
    const t = this.peek();
    throw new Error(t.type === "eof" ? "Unexpected end of expression" : `Unexpected '${t.text}' in expression`);
  }

  private or(): Node {
    let left = this.and();
    while (this.eatWord("OR")) {
      left = { kind: "bin", op: "OR", left, right: this.and() };
    }
    return left;
  }

  private and(): Node {
    let left = this.not();
    while (this.eatWord("AND")) {
      left = { kind: "bin", op: "AND", left, right: this.not() };
    }
    return left;
  }

  private not(): Node {
    return this.eatWord("NOT") ? { kind: "not", arg: this.not() } : this.comparison();
  }

  private comparison(): Node {
    const left = this.additive();
    const t = this.peek();
    if (t.type === "op" && ["=", "<>", "!=", "<", "<=", ">", ">="].includes(t.text)) {
      this.pos++;
      const op = (t.text === "!=" ? "<>" : t.text) as BinaryOp;
      return { kind: "bin", op, left, right: this.additive() };
    }
    const negated = this.isWord("NOT") && this.tokens[this.pos + 1]?.text.toUpperCase() === "LIKE";
    if (negated) {
      this.pos++;
    }
    if (this.eatWord("LIKE")) {
      return { kind: "like", arg: left, pattern: this.additive(), negated };
    }
    return left;
  }

  private additive(): Node {
    let left = this.multiplicative();
    while (this.isOp("+") || this.isOp("-")) {
      const op = this.next().text as BinaryOp;
      left = { kind: "bin", op, left, right: this.multiplicative() };
    }
    return left;
  }

  private multiplicative(): Node {
    let left = this.unary();
    while (this.isOp("*") || this.isOp("/")) {
      const op = this.next().text as BinaryOp;
      left = { kind: "bin", op, left, right: this.unary() };
    }
    return left;
  }

  private unary(): Node {
    if (this.isOp("-")) {
      this.pos++;
      return { kind: "neg", arg: this.unary() };
    }
    return this.primary();
  }

  private primary(): Node {
    const t = this.next();
    if (t.type === "num") {
      return { kind: "num", value: Number(t.text) };
    }
    if (t.type === "str") {
      return { kind: "str", value: t.text };
    }
    if (t.type === "op" && t.text === "(") {
      const inner = this.or();
      this.expectOp(")");
      return inner;
    }
    if (t.type !== "id") {
      this.pos--;
      this.fail();
    }
    const word = t.text.toUpperCase();
    if (word === "TRUE" || word === "FALSE") {
      return { kind: "bool", value: word === "TRUE" };
    }
    if (word === "NULL") {
      return { kind: "null" };
    }
    if (word === "CASE") {
      return this.caseExpression();
    }
    if (word === "CAST") {
      this.expectOp("(");
      const arg = this.or();
      this.expectWord("AS");
      if (!this.eatWord("DOUBLE")) {
        throw new Error("Unsupported CAST type (only DOUBLE)");
      }
      this.expectOp(")");
      return { kind: "cast", arg };
    }
    if (this.isOp("(")) {
      return this.call(word);
    }
    if (KEYWORDS.has(word)) {
      this.pos--;
      this.fail();
    }
    return { kind: "col", name: t.text };
  }

  private caseExpression(): Node {
    const whens: { when: Node; then: Node }[] = [];
    while (this.eatWord("WHEN")) {
      const when = this.or();
      this.expectWord("THEN");
      whens.push({ when, then: this.or() });
    }
    const otherwise = this.eatWord("ELSE") ? this.or() : null;
    this.expectWord("END");
    return { kind: "case", whens, otherwise };
  }

  private call(word: string): Node {
    if (!FUNCTIONS.has(word)) {
      throw new Error(`Unsupported function ${word}`);
    }
    this.expectOp("(");
    const args: Node[] = [];
    if (word === "COUNT" && this.isOp("*")) {
      this.pos++;
    } else {
      args.push(this.or());
      while (this.isOp(",")) {
        this.pos++;
        args.push(this.or());
      }
    }
    this.expectOp(")");
    return { kind: "call", fn: word as "SUM" | "AVG" | "COUNT" | "NULLIF", args };
  }
}

export function parseExpression(sql: string): Node {
  return new Parser(tokenize(sql)).parse();
}

/** Every column the expression reads, once each. */
export function columnsIn(node: Node, into = new Set<string>()): string[] {
  switch (node.kind) {
    case "col":
      into.add(node.name);
      break;
    case "neg":
    case "not":
    case "cast":
      columnsIn(node.arg, into);
      break;
    case "bin":
      columnsIn(node.left, into);
      columnsIn(node.right, into);
      break;
    case "like":
      columnsIn(node.arg, into);
      columnsIn(node.pattern, into);
      break;
    case "case":
      for (const w of node.whens) {
        columnsIn(w.when, into);
        columnsIn(w.then, into);
      }
      if (node.otherwise) {
        columnsIn(node.otherwise, into);
      }
      break;
    case "call":
      node.args.forEach((a) => columnsIn(a, into));
      break;
    default:
      break;
  }
  return [...into];
}

// ---- evaluation -----------------------------------------------------------

type Fn<C> = (ctx: C) => Value;

const asNumber = (v: Value): number | null =>
  v === null ? null : typeof v === "boolean" ? Number(v) : typeof v === "number" ? v : Number.NaN;

const asBoolean = (v: Value): boolean | null =>
  v === null ? null : typeof v === "boolean" ? v : typeof v === "number" ? v !== 0 : true;

function arithmetic(op: "+" | "-" | "*" | "/", a: Value, b: Value): Value {
  const x = asNumber(a);
  const y = asNumber(b);
  if (x === null || y === null) {
    return null;
  }
  switch (op) {
    case "+":
      return x + y;
    case "-":
      return x - y;
    case "*":
      return x * y;
    case "/":
      return y === 0 ? null : x / y;
  }
}

function comparison(op: "=" | "<>" | "<" | "<=" | ">" | ">=", a: Value, b: Value): boolean | null {
  if (a === null || b === null) {
    return null;
  }
  // A boolean column compares equal to 1 / TRUE, whichever way Parquet stored it.
  const x = typeof a === "boolean" && typeof b === "number" ? Number(a) : a;
  const y = typeof b === "boolean" && typeof a === "number" ? Number(b) : b;
  switch (op) {
    case "=":
      return x === y;
    case "<>":
      return x !== y;
    case "<":
      return x < y;
    case "<=":
      return x <= y;
    case ">":
      return x > y;
    case ">=":
      return x >= y;
  }
}

function logic(op: "AND" | "OR", a: Value, b: Value): boolean | null {
  const x = asBoolean(a);
  const y = asBoolean(b);
  if (op === "AND") {
    return x === false || y === false ? false : x === null || y === null ? null : true;
  }
  return x === true || y === true ? true : x === null || y === null ? null : false;
}

const likeCache = new Map<string, RegExp>();

function likeRegex(pattern: string): RegExp {
  let re = likeCache.get(pattern);
  if (!re) {
    const body = [...pattern]
      .map((ch) => (ch === "%" ? ".*" : ch === "_" ? "." : ch.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")))
      .join("");
    re = new RegExp(`^${body}$`, "s");
    likeCache.set(pattern, re);
  }
  return re;
}

interface Mode<C> {
  column(name: string): Fn<C>;
  aggregate(fn: "SUM" | "AVG" | "COUNT", arg: Node | null): Fn<C>;
}

function build<C>(node: Node, mode: Mode<C>): Fn<C> {
  switch (node.kind) {
    case "num":
    case "str":
    case "bool": {
      const value = node.value;
      return () => value;
    }
    case "null":
      return () => null;
    case "col":
      return mode.column(node.name);
    case "neg": {
      const arg = build(node.arg, mode);
      return (c) => {
        const v = asNumber(arg(c));
        return v === null ? null : -v;
      };
    }
    case "not": {
      const arg = build(node.arg, mode);
      return (c) => {
        const v = asBoolean(arg(c));
        return v === null ? null : !v;
      };
    }
    case "cast": {
      const arg = build(node.arg, mode);
      return (c) => asNumber(arg(c));
    }
    case "bin": {
      const left = build(node.left, mode);
      const right = build(node.right, mode);
      const op = node.op;
      if (op === "AND" || op === "OR") {
        return (c) => logic(op, left(c), right(c));
      }
      if (op === "+" || op === "-" || op === "*" || op === "/") {
        return (c) => arithmetic(op, left(c), right(c));
      }
      return (c) => comparison(op, left(c), right(c));
    }
    case "like": {
      const arg = build(node.arg, mode);
      const pattern = build(node.pattern, mode);
      return (c) => {
        const text = arg(c);
        const pat = pattern(c);
        if (text === null || pat === null) {
          return null;
        }
        const hit = likeRegex(String(pat)).test(String(text));
        return node.negated ? !hit : hit;
      };
    }
    case "case": {
      const whens = node.whens.map((w) => ({ when: build(w.when, mode), then: build(w.then, mode) }));
      const otherwise = node.otherwise ? build(node.otherwise, mode) : () => null;
      return (c) => {
        for (const w of whens) {
          if (asBoolean(w.when(c)) === true) {
            return w.then(c);
          }
        }
        return otherwise(c);
      };
    }
    case "call": {
      if (node.fn === "NULLIF") {
        const [a, b] = node.args.map((arg) => build(arg, mode));
        if (!a || !b) {
          throw new Error("NULLIF needs two arguments");
        }
        return (c) => {
          const x = a(c);
          return comparison("=", x, b(c)) === true ? null : x;
        };
      }
      return mode.aggregate(node.fn, node.args[0] ?? null);
    }
  }
}

function rowMode(cols: Columns): Mode<number> {
  return {
    column(name) {
      const col = cols[name];
      if (!col) {
        throw new Error(`Column '${name}' is not loaded`);
      }
      return (i) => (col[i] ?? null) as Value;
    },
    aggregate(fn) {
      throw new Error(`Aggregate ${fn} is not allowed in a row expression`);
    },
  };
}

function aggregateMode(cols: Columns): Mode<ArrayLike<number>> {
  return {
    column(name) {
      throw new Error(`Column '${name}' is used outside an aggregate`);
    },
    aggregate(fn, arg) {
      if (fn === "COUNT" && arg === null) {
        return (rows) => rows.length;
      }
      if (arg === null) {
        throw new Error(`${fn} needs an argument`);
      }
      const value = build(arg, rowMode(cols));
      return (rows) => {
        let sum = 0;
        let n = 0;
        for (let k = 0; k < rows.length; k++) {
          const v = asNumber(value(rows[k]!));
          if (v !== null) {
            sum += v;
            n++;
          }
        }
        if (fn === "COUNT") {
          return n;
        }
        if (n === 0) {
          return null;
        }
        return fn === "SUM" ? sum : sum / n;
      };
    },
  };
}

/** A predicate or scalar over one row. Throws now, not per row, if a column is not loaded. */
export function compileRowExpression(node: Node, cols: Columns): (row: number) => Value {
  return build(node, rowMode(cols));
}

/** An aggregate expression over a set of row indices. */
export function compileAggregateExpression(node: Node, cols: Columns): (rows: ArrayLike<number>) => Value {
  return build(node, aggregateMode(cols));
}
