# Contrast of the design tokens

WCAG 2.x ratios (relative luminance formula) computed from the hex values in `web/src/index.css`. Targets: text 4.5:1, marks 3:1. Borders are decoration only; no meaning rides on them.

The app uses the Graphite set. The `.theme-light` set used only by /dev/viz keeps the earlier measured values (text 15.80, muted 6.11, range/page 3.29, range/surface 3.09).

Failures found and fixed while choosing the sets:
- A `--range` `#5d6471` was 2.80:1 on the surface (< 3:1) -> `#656d7b`
- Semantic colours were checked on both page and surface (cards), not only the page.

## Graphite

| Pair | Ratio | Need |
|---|---|---|
| text/page | 15.62:1 | 4.5:1 |
| text/surface | 14.14:1 | 4.5:1 |
| muted text/page | 7.04:1 | 4.5:1 |
| muted text/surface | 6.38:1 | 4.5:1 |
| mark-muted (noise delta)/surface | 6.38:1 | 4.5:1 |
| accent/page | 8.74:1 | 4.5:1 |
| accent/surface | 7.91:1 | 4.5:1 |
| accent-fg on accent button | 8.91:1 | 4.5:1 |
| positive/page | 8.32:1 | 4.5:1 |
| positive/surface | 7.53:1 | 4.5:1 |
| negative/page | 6.46:1 | 4.5:1 |
| negative/surface | 5.84:1 | 4.5:1 |
| warning/page | 8.63:1 | 4.5:1 |
| warning/surface | 7.81:1 | 4.5:1 |
| warning/warning-bg | 7.28:1 | 4.5:1 |
| range fill/page (mark) | 3.53:1 | 3:1 |
| range fill/surface (mark) | 3.20:1 | 3:1 |
| tick/range fill (mark) | 4.75:1 | 3:1 |
| border/surface (decoration) | 1.24:1 | - |
