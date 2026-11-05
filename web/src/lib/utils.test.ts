import { cn } from "./utils";

describe("cn", () => {
  it("keeps a text colour next to the theme's font sizes (text-body is a size, not a colour)", () => {
    expect(cn("text-white", "text-body")).toBe("text-white text-body");
    expect(cn("text-ink text-h1 text-section text-caption text-heading text-title text-display")).toContain("text-ink");
  });
  it("still lets a later colour or size win", () => {
    expect(cn("text-muted", "text-ink")).toBe("text-ink");
    expect(cn("text-body", "text-caption")).toBe("text-caption");
  });
});
