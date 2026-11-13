import { copyText } from "./clipboard";

describe("copyText", () => {
  it("uses the clipboard when it works", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    expect(await copyText("hi")).toBe(true);
    expect(writeText).toHaveBeenCalledWith("hi");
  });
  it("falls back to execCommand when the clipboard is missing or rejects", async () => {
    const exec = vi.fn().mockReturnValue(true);
    document.execCommand = exec;
    vi.stubGlobal("navigator", { clipboard: { writeText: vi.fn().mockRejectedValue(new Error("no")) } });
    expect(await copyText("hi")).toBe(true);
    expect(exec).toHaveBeenCalledWith("copy");
    vi.stubGlobal("navigator", {});
    expect(await copyText("hi")).toBe(true);
  });
  it("puts focus back where it was after the fallback", async () => {
    document.execCommand = vi.fn().mockReturnValue(true);
    vi.stubGlobal("navigator", {});
    const button = document.createElement("button");
    document.body.appendChild(button);
    button.focus();
    await copyText("hi");
    expect(document.activeElement).toBe(button);
    button.remove();
  });
  it("reports failure when nothing works", async () => {
    document.execCommand = vi.fn().mockReturnValue(false);
    vi.stubGlobal("navigator", {});
    expect(await copyText("hi")).toBe(false);
  });
});
