import { cn } from "@/lib/utils";
import {
  Confidence,
  DataTableFallback,
  Delta,
  Dumbbell,
  RangeBar,
  Sparkline,
  WinBar,
  sharedDomain,
} from "@/viz";

const ROWS = [
  { name: "Allen", p10: 14.2, p50: 24.1, p90: 33.5, form: [18, 22, 31, 12, 25, 27], win: 0.62 },
  { name: "Goff", p10: 11.0, p50: 19.0, p90: 28.1, form: [20, 15, 19, 22, 17, 21], win: 0.48 },
  { name: "Pacheco", p10: 3.1, p50: 11.3, p90: 19.9, form: [8, 14, 6, 12, 9, 13], win: 0.5 },
  { name: "Mixon (Q)", p10: null, p50: 10.8, p90: null, form: [7], win: 0.31 },
  { name: "No projection", p10: null, p50: null, p90: null, form: [], win: null },
];
const DOMAIN = sharedDomain(ROWS) ?? ([0, 1] as const);
const DELTAS = [4.1, -2.0, 0.4, -0.4, 0.5];

function Panel({ theme }: { theme: "theme-light" | "theme-dark" }) {
  return (
    <div className={cn(theme, "flex-1 card")}>
      <h2 className="mb-2 text-body font-semibold">{theme === "theme-light" ? "Light" : "Dark"}</h2>
      <table className="w-full text-body">
        <thead>
          <tr className="text-left text-caption text-muted">
            <th scope="col">Player</th>
            <th scope="col">Range</th>
            <th scope="col">Form</th>
            <th scope="col">Win</th>
          </tr>
        </thead>
        <tbody>
          {ROWS.map((r) => (
            <tr key={r.name}>
              <td>{r.name}</td>
              <td><RangeBar p10={r.p10} p50={r.p50} p90={r.p90} domain={DOMAIN} /></td>
              <td><Sparkline values={r.form} /></td>
              <td><WinBar fraction={r.win} /></td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-4 flex flex-wrap gap-4">
        {DELTAS.map((d) => <Delta key={d} points={d} />)}
        <span>toss-up: <Delta points={3} confidence="toss-up" /></span>
      </p>
      <p className="mt-2 flex gap-4">
        <Confidence share={0.8} /> <Confidence share={0.6} /> <Confidence share={0.4} />
      </p>
      <p className="mt-2"><Dumbbell before={14} after={19} domain={[0, 30]} measure="Title odds" percent /></p>
      <DataTableFallback
        columns={["Player", "p10", "p50", "p90"]}
        rows={ROWS.map((r) => [r.name, r.p10 ?? "–", r.p50 ?? "–", r.p90 ?? "–"])}
      />
    </div>
  );
}

/** Visual check of every chart part in both themes. */
export default function DevViz() {
  return (
    <section>
      <h1 className="mb-4 text-display font-semibold">Viz gallery</h1>
      <div className="flex flex-col gap-4 lg:flex-row">
        <Panel theme="theme-light" />
        <Panel theme="theme-dark" />
      </div>
    </section>
  );
}
