import { Section } from "@/components/Section";
import { type Column, ResponsiveTable } from "@/components/ResponsiveTable";
import { HBar } from "@/features/league/PowerRankings";
import { cn } from "@/lib/utils";
import { formatNumber } from "@/viz";
import {
  EMPTY_TEXT,
  type Line,
  MODELS,
  MODEL_LABEL,
  type Model,
  SMALL_N,
  type ScorecardData,
  leftOutText,
  positionLines,
  tierLines,
  weekLines,
  weeksText,
} from "./logic";

function signed(v: number | null | undefined): string {
  if (v == null) return "–";
  const text = formatNumber(Math.abs(v));
  return v < -0.05 ? `−${text}` : v > 0.05 ? `+${text}` : text;
}

function maeCell(model: Model) {
  return (line: Line) => {
    const c = line.cells[model];
    if (!c || c.mae == null) return <span className="text-muted">–</span>;
    const best = line.best === model;
    const own = c.n !== line.n ? ` (n ${c.n})` : "";
    return (
      <span className={cn(best && "font-semibold")}>
        {formatNumber(c.mae)}
        {best && " best"}
        {own}
      </span>
    );
  };
}

function biasCell(model: Model) {
  return (line: Line) => <span>{signed(line.cells[model]?.bias)}</span>;
}

function columns(first: string): Column<Line>[] {
  return [
    { label: first, role: "primary", render: (l) => l.label },
    {
      label: "Player-games (n)",
      numeric: true,
      render: (l) => (l.small ? `${l.n}, small sample` : String(l.n)),
    },
    ...MODELS.map((m) => ({ label: `${MODEL_LABEL[m]} error (pts)`, numeric: true, render: maeCell(m) })),
    ...MODELS.map((m) => ({
      label: `${MODEL_LABEL[m]} bias (pts)`,
      numeric: true,
      role: "detail" as const,
      render: biasCell(m),
    })),
  ];
}

function LineTable({ caption, first, lines }: { caption: string; first: string; lines: Line[] }) {
  return <ResponsiveTable caption={caption} columns={columns(first)} rows={lines} rowKey={(l) => l.key} />;
}

/** Error by week as grey bars, one per model, once there is more than one week. */
function WeekBars({ lines }: { lines: Line[] }) {
  const max = Math.max(0, ...lines.flatMap((l) => MODELS.map((m) => l.cells[m]?.mae ?? 0)));
  return (
    <ul aria-label="Average error by week" className="space-y-3">
      {lines.map((l) => (
        <li key={l.key}>
          <div className="text-body font-medium">{l.label}</div>
          {MODELS.filter((m) => l.cells[m]?.mae != null).map((m) => (
            <div key={m} className="grid grid-cols-[5rem_1fr_3rem] items-center gap-2">
              <span className="text-caption text-muted">{MODEL_LABEL[m]}</span>
              <HBar fraction={max ? (l.cells[m]?.mae ?? 0) / max : 0} label={`${MODEL_LABEL[m]} ${formatNumber(l.cells[m]?.mae)} points`} />
              <span className="text-right tabular-nums">{formatNumber(l.cells[m]?.mae)}</span>
            </div>
          ))}
        </li>
      ))}
    </ul>
  );
}

export function EmptyScorecard({ data }: { data: ScorecardData }) {
  return (
    <div className="card">
      <p className="text-body">{EMPTY_TEXT}</p>
      <p className="mt-2 text-caption text-muted">
        Archived now: {weeksText(data.weeks_archived)}. Scored: none yet.
        {data.excluded.games > 0 && ` ${data.excluded.games} player-games archived. ${leftOutText(data.excluded)}`}
      </p>
    </div>
  );
}

const METHOD = (
  <>
    <p>
      Each player-game uses the last projection we saved before that team&apos;s kickoff (Eastern times from the schedule); later saves are
      ignored. A game counts once it has final points. Teams with no kickoff time are left out and counted.
    </p>
    <p className="mt-2">
      Error is the average gap in fantasy points between the projection and what the player scored, ignoring direction. Bias is the average
      of projection minus actual: above zero means the model runs high. Projections under 0.5 are raised to 0.5, as in the backtest. Size
      tiers are projection thirds, with edges from the 2019 to 2023 seasons, the same as the backtest.
    </p>
    <p className="mt-2">
      Sleeper is scored from its own projections saved before kickoff only, under each league&apos;s scoring. We cannot show any Sleeper
      projection fetched after kickoff to be clean, so those are not used. Sleeper&apos;s archive starts later than ours, so its n can be
      smaller (shown beside it). Our saves hold the mean only, so there is no interval coverage here.
    </p>
  </>
);

export function ScorecardView({ data }: { data: ScorecardData }) {
  if (data.rows.length === 0) return <EmptyScorecard data={data} />;
  const weeks = weekLines(data.rows);
  const positions = positionLines(data.rows);
  const tiers = tierLines(data.rows);
  const anySmall = [...weeks, ...positions, ...tiers].some((l) => l.small);
  const noSleeper = !data.rows.some((r) => r.model === "sleeper");
  return (
    <>
      <p className="measure text-caption text-muted">
        Lower error is better; points are fantasy points per player-game. {data.excluded.scored} of {data.excluded.games} archived
        player-games scored ({weeksText(data.weeks_scored)}). {leftOutText(data.excluded)}
      </p>
      {anySmall && (
        <p role="note" className="mt-2 rounded-md border border-border px-3 py-2 text-caption text-warning">
          Warning: some rows have fewer than {SMALL_N} player-games. Treat gaps between models there as noise.
        </p>
      )}
      <p className="measure mt-2 text-caption text-muted">
        {noSleeper
          ? "Sleeper: not clean, no projection of theirs was saved before kickoff for these games."
          : data.excluded.sleeper_missing > 0
            ? `Sleeper: ${data.excluded.sleeper_missing} scored games had no Sleeper projection saved before kickoff and are left out of its column.`
            : "Sleeper: scored from projections saved before kickoff only."}
      </p>
      <div className="mt-6 space-y-8">
        <Section title="By week" caption="Average error per player-game, all positions." howCalculated={METHOD}>
          <LineTable caption="Error by week" first="Week" lines={weeks} />
          {weeks.length > 1 && (
            <div className="mt-4">
              <WeekBars lines={weeks} />
            </div>
          )}
        </Section>
        <Section title="By position" caption="All weeks scored so far.">
          <LineTable caption="Error by position" first="Position" lines={positions} />
        </Section>
        <Section title="By size of projection" caption="Thirds of the baseline projection, so stars and bench players are not mixed.">
          <LineTable caption="Error by projection size" first="Size" lines={tiers} />
        </Section>
      </div>
    </>
  );
}
