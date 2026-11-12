import { rankTodos } from "@/features/effects/effect";
import { type Todo, holeTodos, leagueTodos, orderByDeadline, tradeDeadlineTodos } from "./todos";

const todo = (id: string, over: Partial<Todo> = {}): Todo => ({
  id,
  leagueKey: "a",
  leagueName: "A",
  kind: "lineup",
  title: id,
  detail: "",
  href: "/lineup?league=a",
  effect: { playoffPoints: null, points: null },
  deadlineDay: null,
  sleeperUrl: null,
  ...over,
});

describe("rankTodos", () => {
  it("puts playoff-odds effects first (biggest first), then fantasy points only, then no number", () => {
    const ranked = rankTodos([
      todo("none"),
      todo("pts", { effect: { playoffPoints: null, points: 4 } }),
      todo("small", { effect: { playoffPoints: 0.8, points: 1 } }),
      todo("big", { effect: { playoffPoints: 2.3, points: 0.2 } }),
    ]);
    expect(ranked.map((t) => t.id)).toEqual(["big", "small", "pts", "none"]);
  });

  it("keeps the given order for ties and does not change the input", () => {
    const input = [todo("x", { effect: { playoffPoints: 1, points: null } }), todo("y", { effect: { playoffPoints: 1, points: null } })];
    expect(rankTodos(input).map((t) => t.id)).toEqual(["x", "y"]);
    expect(input.map((t) => t.id)).toEqual(["x", "y"]);
  });

  it("ranks a negative effect below a positive one and handles an empty list", () => {
    const ranked = rankTodos([
      todo("neg", { effect: { playoffPoints: -1, points: null } }),
      todo("pos", { effect: { playoffPoints: 0.5, points: null } }),
    ]);
    expect(ranked.map((t) => t.id)).toEqual(["pos", "neg"]);
    expect(rankTodos([])).toEqual([]);
  });
});

describe("orderByDeadline", () => {
  it("orders by the earliest deadline day, no deadline last, and by effect within a day", () => {
    const out = orderByDeadline([
      todo("late", { deadlineDay: "2026-11-08", effect: { playoffPoints: 9, points: null } }),
      todo("open", { effect: { playoffPoints: 20, points: null } }),
      todo("wedLow", { deadlineDay: "2026-11-04", effect: { playoffPoints: 1, points: null } }),
      todo("wedHigh", { deadlineDay: "2026-11-04", effect: { playoffPoints: 3, points: null } }),
    ]);
    expect(out.map((t) => t.id)).toEqual(["wedHigh", "wedLow", "late", "open"]);
  });
});

const league = { league_key: "a", name: "Alpha" };
const deadlines = { lineup: "2026-11-08", waiver: "2026-11-04" };

describe("orderByDeadline edge cases", () => {
  it("keeps the effect ranking for two to-dos with no deadline, ties and negative effects", () => {
    const e = (playoffPoints: number | null, points: number | null = null) => ({ playoffPoints, points });
    const out = orderByDeadline([todo("n1", { effect: e(-2) }), todo("n2", { effect: e(1) }), todo("t1", { effect: e(1) }), todo("none")]);
    expect(out.map((t) => t.id)).toEqual(["n2", "t1", "n1", "none"]);
  });
  it("mixes tiers on one day: odds, then points, then no number", () => {
    const day = "2026-11-08";
    const out = orderByDeadline([
      todo("none", { deadlineDay: day }),
      todo("pts", { deadlineDay: day, effect: { playoffPoints: null, points: 3 } }),
      todo("odds", { deadlineDay: day, effect: { playoffPoints: 0.1, points: null } }),
    ]);
    expect(out.map((t) => t.id)).toEqual(["odds", "pts", "none"]);
  });
});

describe("leagueTodos", () => {
  it("picks the add with the biggest playoff change, whatever its position", () => {
    const small = { kind: "waiver", get: "Small", give: "X", playoff_delta: 0.01, delta_points: 1, rank: 1 };
    const big = { kind: "waiver", get: "Big", give: "Y", playoff_delta: 0.04, delta_points: 2, rank: 2 };
    expect(leagueTodos(league, [], [small, big] as never, deadlines)[0]?.title).toBe("Add Big, drop Y");
  });
  it("gives repeated action text distinct ids", () => {
    const a = { kind: "Injury", text: "Cook is Out and in your lineup", delta_points: null };
    const ids = leagueTodos(league, [a, a] as never, [], deadlines).map((t) => t.id);
    expect(new Set(ids).size).toBe(2);
  });

  const waiver = { kind: "waiver", get: "Coleman", give: "Bernard", playoff_delta: 0.023, delta_points: 3.1, rank: 1 } as never;

  it("turns a stored waiver add into a Moves to-do with its playoff effect in points", () => {
    const [t] = leagueTodos(league, [], [waiver], deadlines);
    expect(t).toMatchObject({
      kind: "waiver",
      title: "Add Coleman, drop Bernard",
      leagueKey: "a",
      leagueName: "Alpha",
      href: "/moves?league=a",
      deadlineDay: "2026-11-04",
    });
    expect(t?.effect.playoffPoints).toBeCloseTo(2.3);
    expect(t?.effect.points).toBe(3.1);
  });

  it("skips an add under the bar and the waiver action (the stored add covers it)", () => {
    const small = { ...(waiver as object), playoff_delta: 0.001 } as never;
    const actions = [{ kind: "Waiver", text: "Add X, drop Y: +2.0% playoff odds, +1.0 points", delta_points: 1 }];
    expect(leagueTodos(league, actions as never, [small], deadlines)).toEqual([]);
  });

  it("maps lineup and injury actions to Lineup to-dos with the first kickoff as deadline", () => {
    const actions = [
      { kind: "Injury", text: "Cook is Out and in your lineup", delta_points: null },
      { kind: "Lineup", text: "Start A over B (+4.1 points)", delta_points: 4.1 },
    ];
    const out = leagueTodos(league, actions as never, [], deadlines);
    expect(out.map((t) => [t.kind, t.href, t.deadlineDay])).toEqual([
      ["injury", "/lineup?league=a", "2026-11-08"],
      ["lineup", "/lineup?league=a", "2026-11-08"],
    ]);
    expect(out[1]?.title).toBe("Start A over B");
    expect(out[1]?.effect.points).toBe(4.1);
  });

  it("drops a toss-up win-probability action", () => {
    const actions = [
      { kind: "Win probability", text: "Toss-up: start A over B (50.0% vs 50.1% to win)", delta_points: null, share_better: 0.51 },
    ];
    expect(leagueTodos(league, actions as never, [], deadlines)).toEqual([]);
  });

  it("works with unknown deadlines", () => {
    const [t] = leagueTodos(league, [], [waiver], { lineup: null, waiver: null });
    expect(t?.deadlineDay).toBeNull();
  });
});

describe("leagueTodos in the playoffs", () => {
  const add = {
    kind: "waiver",
    get: "Coleman",
    give: "Bernard",
    playoff_delta: 0,
    title_delta: 0.012,
    delta_points: 3.1,
    rank: 1,
  } as never;
  it("gates and ranks the stored add on the title change, since seeds are fixed", () => {
    const [t] = leagueTodos(league, [], [add], deadlines, "playoffs");
    expect(t?.title).toBe("Add Coleman, drop Bernard");
    expect(t?.effect.playoffPoints).toBeCloseTo(1.2);
    expect(t?.effect.odds).toBe("title");
  });
  it("skips an add whose title change is under the bar even if its playoff change is big", () => {
    const small = { ...(add as object), playoff_delta: 0.05, title_delta: 0.001 } as never;
    expect(leagueTodos(league, [], [small], deadlines, "playoffs")).toEqual([]);
  });
  it("gives an eliminated team no waiver to-do but keeps its lineup to-dos", () => {
    const actions = [{ kind: "Injury", text: "Cook is Out and in your lineup", delta_points: null }];
    expect(leagueTodos(league, actions as never, [add], deadlines, "out").map((t) => t.kind)).toEqual(["injury"]);
  });
});

describe("tradeDeadlineTodos", () => {
  const t = (give: string, get: string, playoff_delta: number | null, title_delta: number | null = null) =>
    ({ kind: "trade", give, get, partner: "R", playoff_delta, title_delta, delta_points: 1, rank: 1 }) as never;
  const run = (state: "open" | "closing" | "passed" | "none", trades: never[], phase: "season" | "playoffs" | "out" = "season") =>
    tradeDeadlineTodos(league, trades, state, 11, "2026-11-04", phase);

  it("gives one to-do for the best trade in deadline week", () => {
    const out = run("closing", [t("A", "B", 0.02), t("C", "D", 0.05)]);
    expect(out).toHaveLength(1);
    expect(out[0]).toMatchObject({
      kind: "trade",
      title: "Trade deadline: C for D",
      detail: "Trades close after week 11",
      href: "/moves?league=a&view=trades",
      deadlineDay: "2026-11-04",
      effect: { playoffPoints: 5 },
    });
  });

  it("gives nothing outside deadline week", () => {
    for (const s of ["open", "passed", "none"] as const) expect(run(s, [t("A", "B", 0.05)])).toEqual([]);
  });

  it("gives nothing under the gain bar, with no trades, or when out", () => {
    expect(run("closing", [t("A", "B", 0.001)])).toEqual([]);
    expect(run("closing", [])).toEqual([]);
    expect(run("closing", [t("A", "B", 0.05)], "out")).toEqual([]);
  });

  it("judges on title odds in the playoffs", () => {
    expect(run("closing", [t("A", "B", 0.09, 0.001), t("C", "D", 0.0, 0.04)], "playoffs")[0]?.title).toBe("Trade deadline: C for D");
  });
});

describe("sleeperUrl", () => {
  it("is the league page when the id is known, null when not", () => {
    const waiver = { get: "A", give: "B", delta_points: 1, playoff_delta: 5, title_delta: 5 } as never;
    expect(leagueTodos({ ...league, league_id: "77" }, [], [waiver], deadlines)[0]?.sleeperUrl).toBe("https://sleeper.com/leagues/77");
    expect(leagueTodos(league, [], [waiver], deadlines)[0]?.sleeperUrl).toBeNull();
  });
});

describe("holeTodos", () => {
  const league = { league_key: "a", league_id: "9", name: "A" };
  const fill = (n: string, p: number, d: string | null) => ({ gsis_id: n, full_name: n, position: "TE", projection: p, drop_name: d });
  it("maps a bye hole to a cover to-do with fill-ins and the lineup deadline", () => {
    const [t = todo("missing")] = holeTodos(
      league,
      [{ kind: "bye", slot: "TE", player_name: "Kelce", fill_ins: [fill("Lowe", 12.34, "Bench")] }],
      "2026-11-15",
    );
    expect(t).toMatchObject({ kind: "cover", title: "No TE this week: Kelce is on bye", deadlineDay: "2026-11-15" });
    expect(t.fillIns).toEqual(["Add Lowe (12.3 pts), drop Bench"]);
    expect(t.sleeperUrl).toContain("9");
  });
  it("words out and empty holes, and keeps an empty fill-in list", () => {
    const todos = holeTodos(
      league,
      [
        { kind: "out", slot: "QB", player_name: "Allen", fill_ins: [] },
        { kind: "empty", slot: "RB", player_name: null, fill_ins: [fill("X", 1, null)] },
      ],
      null,
    );
    expect(todos[0]?.title).toBe("No QB this week: Allen is out");
    expect(todos[0]?.fillIns).toEqual([]);
    expect(todos[1]?.title).toBe("No RB this week: the slot is empty");
    expect(todos[1]?.fillIns).toEqual(["Add X (1.0 pts)"]);
  });
  it("maps an IR move to an ir to-do", () => {
    const [t = todo("missing")] = holeTodos(league, [{ kind: "ir_move", slot: "IR", player_name: "Hurt", fill_ins: [] }], null);
    expect(t).toMatchObject({ kind: "ir", title: "Move Hurt to IR to open a roster spot" });
    expect(t.fillIns).toBeUndefined();
  });
  it("adds no hole to-dos once the team is out", () => {
    const holes: Parameters<typeof holeTodos>[1] = [{ kind: "ir_move", slot: "IR", player_name: "Hurt", fill_ins: [] }];
    expect(holeTodos(league, holes, null, "out")).toEqual([]);
    expect(holeTodos(league, holes, null, "season")).toHaveLength(1);
  });
});
