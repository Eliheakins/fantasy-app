import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { ApiState } from "@/api/envelope";
import { ApiBoundary } from "./ApiBoundary";

const show = (state: ApiState<string>) => render(<ApiBoundary state={state}>{(d) => <p>{d}</p>}</ApiBoundary>);

describe("ApiBoundary", () => {
  it("loading is a busy status that reserves height", () => {
    show({ kind: "loading" });
    const status = screen.getByRole("status");
    expect(status).toHaveAttribute("aria-busy", "true");
    expect(status.className).toContain("min-h-");
    expect(screen.getByText("Loading…")).toBeInTheDocument();
  });

  it("error is an alert with a retry that calls retry", async () => {
    const retry = vi.fn();
    show({ kind: "error", error: { message: "HTTP 500", code: null }, retry });
    expect(screen.getByRole("alert")).toHaveTextContent("This did not load.");
    expect(screen.queryByRole("status")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(retry).toHaveBeenCalledOnce();
  });

  it("error without a retry offers no button", () => {
    show({ kind: "error", error: { message: "x", code: null } });
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("running keeps its wording", () => {
    show({ kind: "running", startedAt: null });
    expect(screen.getByRole("status")).toHaveTextContent("Working. This page updates when it finishes.");
  });

  it("no data names the command in code", () => {
    show({ kind: "no_data", message: "" });
    expect(screen.getByText("make refresh").tagName).toBe("CODE");
  });
});
