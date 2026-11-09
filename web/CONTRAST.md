# Contrast of the design tokens

WCAG 2.x ratios (relative luminance formula) computed on 2026-11-09 from the `--lf-*` hex values in `web/src/index.css` (look F). Chart colours come from the same tokens through `web/src/viz/chartTheme.ts` (`--lf-muted` ticks, `--lf-line` grid, `--lf-faint` bars, `--lf-chart-other` other teams, `--lf-forest` mine). Targets: text 4.5:1, large text and marks 3:1. Borders and rules are decoration only; no meaning rides on them.

Light backgrounds: page `#F1F5F2`, surface `#FFFFFF` (fields, popovers), panel `#E0EEE4` (the key panel, my rows), band `#E8F0EA` (table header rows).

## Failures

Every text pair passes. Eight mark pairs fail 3:1:

- `chart-other` `#A3B0A9` (other teams' lines and bars) on page 2.04:1, panel 1.88:1, surface 2.25:1, and on the `line` track of a win bar 1.71:1. It is recessive on purpose (decisions.md, 2026-11-05), and those charts keep labels and a table view, but it is below 3:1.
- `line` `#D9E3DC` as the opponent's range fill in `RangeBar` (`muted`) on page 1.19:1, panel 1.10:1, surface 1.31:1. The Lineup "Your matchup" panel draws it on the panel.
- `ink` `#13201A` median tick on a `faint` `#5E6A64` range fill in `RangeBar`: 2.98:1. The tick has a page-colour stroke, and page against faint is 5.13:1.

## Text (need 4.5:1)

| Pair | page | surface | panel | band |
|---|---|---|---|---|
| ink `#13201A` | 15.28 | 16.81 | 14.02 | 14.48 |
| label `#2E3A33` | 10.79 | 11.87 | 9.90 | 10.22 |
| muted `#56635C` | 5.72 | 6.30 | 5.25 | 5.42 |
| faint `#5E6A64` | 5.13 | 5.64 | 4.71 | 4.86 |
| forest `#123D2C` | 11.03 | 12.14 | 10.13 | 10.46 |
| focus `#1F5A43` | 7.33 | 8.07 | 6.73 | 6.95 |
| better `#157A3D` | 4.91 | 5.41 | 4.51 | 4.66 |
| worse `#B4261A` | 5.90 | 6.50 | 5.42 | 5.59 |
| warning `#6B4200` | 7.94 | 8.73 | 7.29 | 7.52 |

| Pair | Ratio | Where |
|---|---|---|
| warning/warning-bg `#FFF4DB` | 7.99:1 | data notices |
| ink/warning-bg | 15.38:1 | data notices |
| white/focus | 8.07:1 | buttons, selected pills, pills on the header band |
| white/forest | 12.14:1 | header band, active tab on the phone bar |
| white/chrome-tabs `#1A4A37` | 10.10:1 | active tab |
| chrome-text `#CFE5D9`/forest | 9.17:1 | inactive tabs on the phone bar |
| chrome-text/chrome-tabs | 7.63:1 | inactive tabs |

## Marks (need 3:1)

| Pair | Ratio | Where |
|---|---|---|
| forest/page, panel, surface | 11.03, 10.13, 12.14 | my line and bars |
| faint/page, panel, surface | 5.13, 4.71, 5.64 | neutral bars, range fills, dumbbell line |
| chart-other/page, panel, surface | 2.04, 1.88, 2.25 | other teams (fails) |
| forest/chart-other | 5.40:1 | my series next to the others |
| line/page, panel, surface | 1.19, 1.10, 1.31 | opponent's range fill (fails) |
| forest/line | 9.23:1 | win bar fill on its track |
| faint/line | 4.29:1 | win bar fill on its track |
| chart-other/line | 1.71:1 | win bar fill on its track (fails) |
| ink/faint | 2.98:1 | range bar median tick (fails) |
| muted/line | 4.79:1 | opponent's median tick |
| chrome-accent `#9FE0BC`/chrome-tabs, forest | 6.67, 8.01 | active tab underline |
| focus/page, surface, panel | 7.33, 8.07, 6.73 | focus ring |
| white/forest | 12.14:1 | focus ring on the header band |

## Decoration (no target)

| Pair | Ratio |
|---|---|
| line/page | 1.19:1 |
| panel-line `#C9DBCF`/page | 1.31:1 |
| panel-line/panel | 1.21:1 |
| warning-edge `#F3DFAE`/warning-bg | 1.20:1 |

No pair is large text only: every text pair already passes 4.5:1.
