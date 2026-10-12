# Diagrams as code, rendered to SVG

Date: 2026-10-12. Status: design approved in conversation, awaiting spec review.

## Why

The docs hold five Mermaid diagrams as fenced code blocks (architecture ×2, the toolset, documentation strategy,
settings merge). GitHub's website renders them, but many viewers show raw code instead (some mobile apps, editor
previews, offline copies, other forges). Their colours are hard-coded light pastels, so they also look wrong in dark
mode. Goal: every reader sees a finished diagram that fits light and dark mode, the Mermaid source stays the single
source, and nobody can commit a source change without the matching image.

## Design

### Files

```
docs/diagrams/
  README.md                         how to edit and render (short; links to CONTRIBUTING)
  render.sh                         renders every *.mmd (container, pinned image)
  theme.light.json / theme.dark.json  Mermaid config: base theme, colours, font, htmlLabels off
  palette.light.mmd / palette.dark.mmd  classDef lines for the semantic classes (flowcharts only)
  architecture-overview.mmd         + .light.svg + .dark.svg
  architecture-daily-sync.mmd       + …
  toolset-workflow.mmd              + …
  documentation-layers.mmd          + …
  settings-merge.mmd                + …
```

### Sources

- Each diagram moves verbatim (structure, labels, spacing frontmatter such as `look: neo`, `curve`, spacing) into
  `docs/diagrams/<name>.mmd`. Nothing about the content changes.
- Colours leave the sources: `classDef`, `style` and colour values in `linkStyle` are replaced by semantic classes
  (`kit`, `personal`, `claude`, `engine`, `state`, and `kitGroup`/`personalGroup`/`claudeGroup` for subgraphs, plus
  whatever the other diagrams need), assigned with `class`. Subgraphs get classes the same way (Mermaid 11 supports
  `class SUBGRAPH_ID name`). Sequence diagrams keep their `box rgba(…)` tints, which work on both backgrounds.
- A flowchart source ends with the line `%% palette`; render.sh replaces it with the palette file for the theme.

### Themes and palettes

- `theme.<variant>.json`: `{"theme": "base", "themeVariables": {...}, "htmlLabels": false, "flowchart": {"htmlLabels": false}}`.
  Light: near-white surfaces, slate text. Dark: surfaces and text matching the README demo (`#0f1117` background family,
  `#e6e6eb` text), the same violet accent `#a78bfa` for emphasis. Font: a system stack
  (`ui-sans-serif, system-ui, -apple-system, "Segoe UI", Helvetica, Arial, sans-serif`), because an SVG shown through
  `<img>` cannot load web fonts.
- `htmlLabels: false`: labels become SVG `<text>`, not HTML inside `<foreignObject>`, which several image viewers do
  not render. Markdown strings (bold first line) must still render; verified when implementing.
- Palettes: the same class names with variant colours (light: today's pastel fills with saturated strokes; dark: deep
  tinted fills, the same hue strokes, light text). Kit blue, personal green, Claude orange, engine amber, state slate
  stay recognisable in both.
- Background transparent (`-b transparent`), so the page colour shows through.

### Rendering

- `docs/diagrams/render.sh` runs `ghcr.io/mermaid-js/mermaid-cli/mermaid-cli:11.16.0` (pinned; podman, or docker via
  `DIAGRAMS_ENGINE=docker`) with `--network=none`, as the calling user, the repo mounted, for each source and variant:
  compose (source with `%% palette` replaced) → `mmdc -i … -o <name>.<variant>.svg -c theme.<variant>.json -b transparent`.
- After rendering it inserts one comment right after the opening `<svg …>` tag:
  `<!-- diagram-source sha256:<hex> -->`, where `<hex>` is the SHA-256 of the bytes of
  `<name>.mmd` + `palette.<variant>.mmd` + `theme.<variant>.json` + the image reference string, concatenated in that
  order. Any change to the source, its palette, its theme or the renderer version changes the hash.
- `render.sh NAME…` renders only the named diagrams; no argument renders all.

### Keeping images and code in sync

- `tests/test_diagrams.py` (standard library): for every `*.mmd` source (not palettes) both SVGs exist, and each
  SVG's embedded hash equals the hash recomputed from the current files. A failure names the diagram and the fix:
  `docs/diagrams/render.sh <name>`. It also checks: no `.svg` without a source, no fenced ```` ```mermaid ```` block left
  in `docs/` or `README.md` (outside `docs/superpowers/`), every embed points to existing files, and every embed has
  non-empty alt text.
- It runs in normal CI (no Chromium). No pre-commit framework (the repo has none); the test is the gate.

### Embedding

Each former code block becomes:

```html
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../diagrams/architecture-overview.dark.svg">
  <img alt="(a sentence or two describing what the diagram shows)" src="../diagrams/architecture-overview.light.svg">
</picture>
```

followed by a small link line: `<sub>[Source](../diagrams/architecture-overview.mmd)</sub>`. The alt text says what a
sighted reader learns from the diagram, not "diagram of …".

## Documentation

- CONTRIBUTING: a "Diagrams" section (edit the `.mmd`, run `docs/diagrams/render.sh`, commit sources and SVGs
  together; the test explains a stale image).
- `docs/explanation/documentation-strategy.md`: if it says diagrams are Mermaid code blocks, update it.
- AGENTS.md map: `docs/diagrams/`.

## Testing

- New `tests/test_diagrams.py` as above, written first against the current docs (fails: code blocks present, no SVGs).
- The render itself is checked by looking at each SVG in a browser (light and dark) with playwright-cli at 320, 768
  and 1280 px, and on GitHub after pushing.

## Out of scope

Changing what the diagrams show; README polish (next PR); diagrams in `docs/superpowers/` (working documents).
