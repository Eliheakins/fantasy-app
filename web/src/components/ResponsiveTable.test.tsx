import { render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { type Column, ResponsiveTable } from "./ResponsiveTable";

type Row = { name: string; pts: number; note: string };
const COLUMNS: Column<Row>[] = [
  { label: "Player", render: (r) => r.name, role: "primary" },
  { label: "Points", render: (r) => r.pts, numeric: true },
  { label: "Note", render: (r) => r.note, role: "detail" },
];
const ROWS: Row[] = [{ name: "Ann", pts: 12.5, note: "hamstring" }];
const table = () => <ResponsiveTable caption="Players" columns={COLUMNS} rows={ROWS} rowKey={(r) => r.name} />;

afterEach(() => vi.unstubAllGlobals());

function stubWidth(matches: boolean) {
  vi.stubGlobal("matchMedia", () => ({ matches, addEventListener: () => {}, removeEventListener: () => {} }));
}

describe("ResponsiveTable", () => {
  it("renders a table with a row header and right-aligned numbers when wide", () => {
    stubWidth(true);
    render(table());
    expect(screen.getByRole("rowheader", { name: "Ann" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "12.5" })).toHaveClass("text-right");
  });

  it("renders a card with the identity as header and detail folded under More when narrow", () => {
    stubWidth(false);
    render(table());
    const card = screen.getByRole("listitem");
    expect(within(card).getByText("Ann")).toBeInTheDocument();
    expect(within(card).getByText("Points")).toBeInTheDocument();
    expect(within(card).getByText("More").closest("details")).not.toHaveAttribute("open");
    expect(screen.queryByRole("table")).toBeNull();
  });
});
