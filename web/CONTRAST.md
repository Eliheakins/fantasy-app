# Contrast of the design tokens

WCAG 2.x ratios computed from the hex values in `src/index.css`. Targets: text 4.5:1, marks 3:1.

Adjusted from the spec after measuring:
- light `--mark-muted` `#6e7781` -> `#636c76` (was 4.27:1 on the surface, under 4.5:1 for the noise-delta text)
- light `--range` `#9aa5b1` -> `#848f9b` (was 2.50:1 on the page, under 3:1 for the bar fill)

Everything else passes as specified. Borders (about 1.5:1) are decoration only; no meaning rides on them.


## Light

| Pair | Ratio |
|---|---|
| text/page | 15.80:1 |
| muted text/page | 6.11:1 |
| muted text/surface | 5.74:1 |
| mark-muted (noise delta text)/page | 5.33:1 |
| mark-muted/surface | 5.01:1 |
| accent/page | 9.08:1 |
| positive/page | 5.08:1 |
| negative/page | 5.36:1 |
| warning/warning-bg | 4.52:1 |
| range fill/page (mark 3:1) | 3.29:1 |
| range fill/surface (mark 3:1) | 3.09:1 |
| tick/range fill | 4.80:1 |
| border/page (non-essential) | 1.45:1 |

## Dark

| Pair | Ratio |
|---|---|
| text/page | 16.02:1 |
| muted text/page | 6.15:1 |
| muted text/surface | 5.62:1 |
| mark-muted (noise delta text)/page | 6.15:1 |
| mark-muted/surface | 5.62:1 |
| accent/page | 8.79:1 |
| positive/page | 7.45:1 |
| negative/page | 5.65:1 |
| warning/warning-bg | 6.21:1 |
| range fill/page (mark 3:1) | 4.16:1 |
| range fill/surface (mark 3:1) | 3.80:1 |
| tick/range fill | 3.85:1 |
| border/page (non-essential) | 1.55:1 |
