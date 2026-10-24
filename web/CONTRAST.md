# Contrast of the design tokens

WCAG 2.x ratios (relative luminance formula) computed from the hex values in `src/index.css`. Targets: text 4.5:1, marks 3:1. Borders are decoration only; no meaning rides on them.

Three dark directions are being compared (temporary ThemeSwitcher). The `.theme-light` set used only by /dev/viz keeps the earlier measured values (text 15.80, muted 6.11, range/page 3.29, range/surface 3.09).

Failures found and fixed while choosing the sets:
- A `--range` `#5d6471` was 2.80:1 on the surface (< 3:1) -> `#656d7b`
- B `--range` `#6e6357` was 2.94:1 on the surface (< 3:1) -> `#756a5e`
- Semantic colours were checked on both page and surface (cards), not only the page.

## A Graphite

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

## B Copper

| Pair | Ratio | Need |
|---|---|---|
| text/page | 15.22:1 | 4.5:1 |
| text/surface | 14.06:1 | 4.5:1 |
| muted text/page | 7.09:1 | 4.5:1 |
| muted text/surface | 6.56:1 | 4.5:1 |
| mark-muted (noise delta)/surface | 6.56:1 | 4.5:1 |
| accent/page | 6.92:1 | 4.5:1 |
| accent/surface | 6.39:1 | 4.5:1 |
| accent-fg on accent button | 6.90:1 | 4.5:1 |
| positive/page | 8.88:1 | 4.5:1 |
| positive/surface | 8.21:1 | 4.5:1 |
| negative/page | 6.65:1 | 4.5:1 |
| negative/surface | 6.15:1 | 4.5:1 |
| warning/page | 9.34:1 | 4.5:1 |
| warning/surface | 8.63:1 | 4.5:1 |
| warning/warning-bg | 8.04:1 | 4.5:1 |
| range fill/page (mark) | 3.53:1 | 3:1 |
| range fill/surface (mark) | 3.27:1 | 3:1 |
| tick/range fill (mark) | 4.58:1 | 3:1 |
| border/surface (decoration) | 1.37:1 | - |

## C Terminal

| Pair | Ratio | Need |
|---|---|---|
| text/page | 14.83:1 | 4.5:1 |
| text/surface | 13.93:1 | 4.5:1 |
| muted text/page | 6.40:1 | 4.5:1 |
| muted text/surface | 6.01:1 | 4.5:1 |
| mark-muted (noise delta)/surface | 6.01:1 | 4.5:1 |
| accent/page | 8.98:1 | 4.5:1 |
| accent/surface | 8.44:1 | 4.5:1 |
| accent-fg on accent button | 8.88:1 | 4.5:1 |
| positive/page | 10.10:1 | 4.5:1 |
| positive/surface | 9.49:1 | 4.5:1 |
| negative/page | 7.02:1 | 4.5:1 |
| negative/surface | 6.59:1 | 4.5:1 |
| warning/page | 10.00:1 | 4.5:1 |
| warning/surface | 9.40:1 | 4.5:1 |
| warning/warning-bg | 8.68:1 | 4.5:1 |
| range fill/page (mark) | 3.32:1 | 3:1 |
| range fill/surface (mark) | 3.12:1 | 3:1 |
| tick/range fill (mark) | 5.23:1 | 3:1 |
| border/surface (decoration) | 1.45:1 | - |

