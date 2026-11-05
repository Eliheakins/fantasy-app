import { lastExploreParams, rememberExplore } from "./routeMemory";

describe("route memory", () => {
  it("keeps the Explore query without league and team", () => {
    rememberExplore("?league=a&team=2&p=00-0001&s=rec_yards");
    expect(lastExploreParams().toString()).toBe("p=00-0001&s=rec_yards");
  });

  it("forgets the query when Explore is opened bare", () => {
    rememberExplore("?p=00-0001");
    rememberExplore("");
    expect(lastExploreParams().toString()).toBe("");
  });
});
