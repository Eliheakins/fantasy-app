/** Shared look for the Recharts charts, from the dashboard rules: tokens only, ranges and
 * non-semantic bars grey, my series the one strong mark, a caption on the value axis. */

const CHART_FONT_SIZE = 12;
/** --text-muted: at least 4.5:1 on page and surface in both themes (see web/CONTRAST.md). */
export const TICK_COLOR = "var(--text-muted)";
const GRID_COLOR = "var(--border)";
/** Bars that carry no good/bad meaning. */
export const BAR_FILL = "var(--range)";
export const OTHER_LINE = "var(--range)";
export const MY_LINE = "var(--tick)";

const TICK = { fill: TICK_COLOR, fontSize: CHART_FONT_SIZE };

/** Spread onto XAxis / YAxis. */
export const AXIS = { tick: TICK, stroke: GRID_COLOR, tickLine: false } as const;

/** Spread onto CartesianGrid: horizontal rules only. */
export const GRID = { vertical: false, stroke: GRID_COLOR } as const;

/** The value-axis caption, rotated along the axis. Units go in the text: "Chance (%)". */
export function axisCaption(text: string) {
  return {
    value: text,
    angle: -90,
    position: "insideLeft",
    offset: 8,
    style: { fill: TICK_COLOR, fontSize: CHART_FONT_SIZE, textAnchor: "middle" },
  } as const;
}
