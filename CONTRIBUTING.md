# Contributing

Thanks for helping. This page covers setup, tests, evals, catalog changes and the pull request flow. How the code fits together is in [Architecture](docs/explanation/architecture.md); the documentation rules are in [Documentation strategy](docs/explanation/documentation-strategy.md).

## Setup

You need git, Python 3.10 or newer and [uv](https://docs.astral.sh/uv/). The CLI uses the Python standard library only, so there is nothing else to install.

```bash
git clone https://github.com/jonasyr/agent-loadout
cd agent-loadout
```

You do not need to run bootstrap to work on the code. If you do run it from your clone, it links your real `~/.claude` to that clone.

## Tests and validation

```bash
uv run --python 3.12 --with pytest pytest -q
claude plugin validate . && claude plugin validate plugins/loadout
```

The tests include static checks of the repo: JSON files parse, catalog entries are well formed, no secrets are tracked, every relative link in the Markdown resolves, and no `CLAUDE.md` exists outside the repo root.

## Test rules

- **Standard library only.** The CLI and the hook scripts import nothing outside the standard library. Tests use pytest and nothing else.
- **Never the real home.** Tests use the `fake_home` fixture (a temporary `HOME` and `USERPROFILE`, `LOADOUT_PERSONAL` unset) and the `fake_runner` fixture (records commands instead of running `claude`, `git`, `npm` and other tools). Both are in `tests/conftest.py`. A test must never read or write the real `~/.claude`, `~/.claude.json` or `~/.config/loadout`, and never run a real installer.
- **Both platforms.** CI runs the suite on Linux and Windows. Mark a test that only makes sense on one platform with a skip that names the reason.

## Skill evals

The plugin's skills have evals in `plugins/loadout/evals/`. Run them only through `run.sh`:

```bash
plugins/loadout/evals/run.sh --case <name>
```

They make real model calls with your own Claude credential and use your plan's usage, so run one case at a time while you iterate. Never run `claude plugin eval` on the plugin directly: `run.sh` puts stubs for `loadout` and browsers first on `PATH`, uses a temporary home and checks that your global state did not change. Details, options and the opt-in browser case: [Run the skill evals](docs/how-to/run-evals.md).

## Changing the catalog

`catalog.json` holds every keep or drop decision with its `reason`. To propose a tool, follow [Add a tool to the catalog](docs/how-to/add-to-catalog.md). The format is in [Catalog format](docs/reference/catalog-format.md).

## Documentation

When you change behaviour, update the page in `docs/` that owns the fact, and link to it from other pages instead of copying it. The index is [docs/README.md](docs/README.md). A decision with alternatives becomes an ADR in [`docs/adr/`](docs/adr/README.md).

## Diagrams

The diagrams in `docs/` are Mermaid sources in [`docs/diagrams/`](docs/diagrams/README.md), rendered to one light and one dark SVG each, so they show on every viewer (phone apps, editor previews, other forges) and fit both colour schemes. To change one:

1. Edit `docs/diagrams/<name>.mmd`. Flowcharts take their colours from classes (`class nodeId kit`, `class SUBGRAPH kitGroup`, `class e4 emph` for an edge written `a e4@--> b`); the colours are in `palette.light.mmd` and `palette.dark.mmd`, the fonts and base colours in `theme.light.json` and `theme.dark.json`. A flowchart ends with the line `%% palette`.
2. Render: `docs/diagrams/render.sh <name>` (no name renders all). It runs a pinned mermaid-cli in a container without network access: podman, or `DIAGRAMS_ENGINE=docker`.
3. Commit the source and both SVGs together.

Each SVG records a hash of its source, palette, theme, `render.sh` and the pinned mermaid-cli image. `tests/test_diagrams.py` fails when an SVG is out of date and names the command that fixes it. It also rejects Mermaid code blocks in the docs. Embed a new diagram like this, with alt text that says what the diagram shows:

```html
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../diagrams/<name>.dark.svg">
  <img alt="What a reader learns from the diagram, in a sentence or two." src="../diagrams/<name>.light.svg">
</picture>

<sub>[Source](../diagrams/<name>.mmd)</sub>
```

## The README demo

`docs/assets/demo.gif` follows the README Quick start: an existing Claude Code setup, the one-liner, `loadout check`, `loadout init`, then real Claude Code running `/loadout:onboard`. It has two parts:

- **The terminal part** is recorded from [`demo/loadout.tape`](demo/loadout.tape) with [VHS](https://github.com/charmbracelet/vhs). `demo/render.sh` runs it in a container without network access (podman, or `DEMO_ENGINE=docker`), so nothing is installed on your machine. The recording runs the real `loadout` and the real `bootstrap.sh` in a new sandbox HOME that `demo/sandbox.sh` fills with fake data and stand-in binaries (`demo/bin/`: `claude`, `curl` and `uv` refuse to run outside the sandbox).
- **The Claude Code part** (`demo/claude-clip.mp4`) is recorded by the maintainer with `demo/record-claude.sh`, because it needs a real Claude Code login. It works in a throwaway project in `/tmp` and uses a little plan usage. Watch the clip before committing it: it shows the recording machine's plugins and paths. `render.sh` appends it when it exists.

Both tapes share [`demo/style.tape`](demo/style.tape) (font, size, theme, window); title cards come from `demo/card.sh`. Re-render when the output of `bootstrap`, `adopt`, `check` or `init` changes, and before each release. Keep the GIF under 5 MB (lower the framerate in `render.sh` before shortening pauses). VHS's `Wait` reads the top of the scrollback, so the tapes pace answers with `Sleep` instead; check a render by looking at frames (`DEMO_KEEP_DIR=DIR demo/render.sh` keeps the mp4).

## Commits and pull requests

- Use [Conventional Commits](https://www.conventionalcommits.org/): `type(scope): subject`, for example `feat(catalog): add <tool>`, `fix(adopt): ...`, `docs: ...`, `test: ...`.
- Work on a branch and open a pull request against `main`. Say what changed and why, and how you tested it.
- CI must be green before a merge: the test suite on Linux and on Windows (including the hook scripts under Git Bash), and `claude plugin validate` for the marketplace and the plugin.

Security problems: do not open a public issue with details. See [SECURITY.md](SECURITY.md).
