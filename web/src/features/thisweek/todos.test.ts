import { rankTodos } from "@/features/effects/effect";
import { type Todo, leagueTodos, orderByDeadline } from "./todos";

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
