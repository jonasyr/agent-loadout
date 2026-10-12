# Diagrams

Sources and rendered images of the diagrams in the docs. Each `<name>.mmd` has a `<name>.light.svg` and a `<name>.dark.svg`; never edit an SVG by hand.

| File | Holds |
|---|---|
| `<name>.mmd` | the diagram (Mermaid) |
| `palette.light.mmd`, `palette.dark.mmd` | the colour classes flowcharts use |
| `theme.light.json`, `theme.dark.json` | fonts and base colours (mermaid-cli config) |
| `render.sh` | renders the SVGs: `docs/diagrams/render.sh [NAME...]` |

How to edit, render and embed: [CONTRIBUTING.md](../../CONTRIBUTING.md#diagrams).
