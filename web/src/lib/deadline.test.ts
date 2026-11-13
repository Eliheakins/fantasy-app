import { deadlineWeekState } from "./deadline";

describe("deadlineWeekState", () => {
  it.each([
    [9, null, 14, "none"],
    [9, undefined, 14, "none"],
    [9, 99, 14, "none"],
    [9, 15, 14, "none"],
    [null, 11, 14, "none"],
    [10, 11, 14, "open"],
    [11, 11, 14, "closing"],
    [12, 11, 14, "passed"],
    [11, 14, 14, "open"],
    [14, 14, 14, "closing"],
    [10, 11, null, "open"],
    [10, 99, null, "none"],
  ] as const)("week %s, deadline %s, last regular %s is %s", (week, deadline, last, expected) => {
    expect(deadlineWeekState(week, deadline, last)).toBe(expected);
  });
});
