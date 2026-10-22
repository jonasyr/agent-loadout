---
name: diagrams
description: Use when creating or changing a diagram in this repo's docs (docs/diagrams/*.mmd), or when a docs change makes a diagram wrong. Writes Mermaid that follows the palette, renders the light and dark SVGs, and checks them in a browser.
---

# Diagrams in agent-loadout

The rules live in [CONTRIBUTING.md, Diagrams](../../../CONTRIBUTING.md#diagrams) and [docs/diagrams/README.md](../../../docs/diagrams/README.md); read both first. This skill adds the vocabulary and the checks.

## Classes

Colour comes only from classes in `docs/diagrams/palette.light.mmd` and `palette.dark.mmd` (same names in both). Never write `style` lines or inline colours.

| Class | Use for |
|---|---|
| `kit`, `kitGroup` | files and folders of the kit repo |
| `personal`, `personalGroup` | the personal layer |
| `claude`, `claudeGroup` | what lives in Claude Code's configuration |
| `codex`, `codexGroup` | what lives in Codex's configuration |
| `engine`, `engineGroup` | loadout's own processing steps (merge, sync) |
| `state`, `local` | machine-local state and snapshots (dashed) |
| `truth`, `notes`, `notesGroup`, `entry` | the documentation-layers diagram |
| `kit`, `claude`, `engine`, `state` and the `*Group` classes | the toolset-workflow diagram uses its own meaning: `kit` loadout skills, `claude` plugin skills, `engine` tool groups, `state` the start and rtk, groups only tint the stages. The `class` lines in `docs/diagrams/toolset-workflow.mmd` say which node gets which class; change them together with this row |
| `emph`, `truthLink`, `muted` | edges: the main path, the single-source link, background links |

Nodes: `class nodeId kit`. Subgraphs: `class SUBGRAPH kitGroup`. Edges: name them (`a e4@--> b`), then `class e4 emph`. A flowchart's last line is `%% palette`; `render.sh` replaces it with the palette. Sequence diagrams use `box rgba(...)` with the same hues as the palette (as used in architecture-daily-sync: orange your agent, blue loadout, green your machine; teal is free for a Codex-only box).

## Mermaid pitfalls

- Quote labels that contain parentheses, colons or slashes: `n["~/.codex/config.toml"]`.
- Line breaks: Markdown strings (`` "`**bold**\nline`" ``) or `<br/>`, never `\n` in plain labels.
- Keep labels short. Flowcharts set `wrappingWidth` in their front matter (320, toolset-workflow 300); only architecture-overview uses `layout: elk`, the others the default layout. A subgraph with more than six nodes is hard to read on a phone.

## Workflow

1. Edit `docs/diagrams/<name>.mmd`. A new class goes into both palette files with the same name.
2. Render: `docs/diagrams/render.sh <name>` (podman; `DIAGRAMS_ENGINE=docker` for docker). Palette or theme changes: `docs/diagrams/render.sh` renders all.
3. Check the output is a diagram: `grep -l "Syntax error" docs/diagrams/<name>.*.svg` must print nothing.
4. `uv run --python 3.12 --with pytest pytest -q tests/test_diagrams.py tests/test_diagrams_render.py`
5. Look at it: open each SVG with `playwright-cli` on a white and on a dark (`#0d1117`) page at 320 and 1280 px wide; screenshot to disk and read them. Every label fits its box, no edge label sits on a node, arrows point the right way.
6. Embed a new diagram with the `<picture>` snippet from CONTRIBUTING.md and alt text that says what a reader learns.
7. Commit the `.mmd` and both SVGs together (palette changes: all SVGs).
