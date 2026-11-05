import { lineupWhy, waiverWhy } from "./explain";
import { slotShareWhy } from "@/features/lineup/explain";

describe("explain texts", () => {
  it("lineup share is about wins between two lineups, not points", () => {
    const text = lineupWhy(0.64).points ?? "";
    expect(text).toContain("only one of the two lineups beats your opponent");
    expect(text).toContain("64%");
    expect(lineupWhy(null).points).not.toContain("%");
  });
  it("waiver text says the drop is applied and the same draws are used", () => {
    expect(waiverWhy("X", "Y").playoff).toMatch(/dropping Y.*same random draws/);
  });
  it("slot share names the alternative and the tie rule", () => {
    expect(slotShareWhy(0.6)).toMatch(/tie counts half.*highest expected points/);
  });
});
