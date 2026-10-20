# Contributing

Thanks for helping. This page covers setup, tests, evals, catalog changes, issues and the pull request flow. Everyone taking part follows the [Code of Conduct](CODE_OF_CONDUCT.md). How the code fits together is in [Architecture](docs/explanation/architecture.md), and which file does what in [Modules](docs/reference/modules.md); the documentation rules are in [Documentation strategy](docs/explanation/documentation-strategy.md).

## Setup

You need git, Python 3.11 or newer and [uv](https://docs.astral.sh/uv/). The CLI uses the Python standard library only, so there is nothing else to install.

```bash
git clone https://github.com/jonasyr/agent-loadout
cd agent-loadout
```

Run the CLI from the clone with `bin/loadout` (for example `bin/loadout check --help`); `python -m loadout` from `cli/` works too. You do not need to run bootstrap to work on the code. If you do run it from your clone, it links your real `~/.claude` to that clone (and with Codex on, it writes your real `~/.codex` and `~/.agents/skills` from it).

## Tests and validation

```bash
uv run --python 3.12 --with pytest pytest -q
claude plugin validate . && claude plugin validate plugins/loadout
```

`dev/codex-sandbox.sh` runs loadout's Codex setup against the real `codex` CLI in a temporary home and shows what Codex sees (needs codex and network; never touches your `~/.codex`).

The tests include static checks of the repo: JSON files parse, catalog entries are well formed, no secrets are tracked, every relative link in the Markdown resolves, and no `CLAUDE.md` exists outside the repo root except in `templates/` and the eval fixtures.

## Test rules

- **Standard library only.** The CLI and the hook scripts import nothing outside the standard library. Tests use pytest and nothing else.
- **Never the real home.** Tests use the `fake_home` fixture (a temporary `HOME` and `USERPROFILE`, `LOADOUT_PERSONAL` and `CODEX_HOME` unset, no real WSL detection) and the `fake_runner` fixture (records commands instead of running `claude`, `git`, `npm` and other tools). Both are in `tests/conftest.py`, next to an automatic fixture that gives every test a throwaway `HOME` even without `fake_home`; it is a safety net, not a replacement. A test must never read or write the real `~/.claude`, `~/.claude.json`, `~/.codex` or `~/.config/loadout`, and never run a real installer.
- **Both platforms.** CI runs the suite on Linux, on Windows and inside WSL 2. Mark a test that only makes sense on one platform with a skip that names the reason.

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

Agents: use the `diagrams` skill (`.claude/skills/diagrams`).

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

`docs/assets/demo.gif` follows the README Quick start: an existing Claude Code setup (the demo shows Claude Code), the one-liner, `loadout check`, `loadout init`, then real Claude Code running `/loadout:onboard`. It has two parts:

- **The terminal part** is recorded from [`demo/loadout.tape`](demo/loadout.tape) with [VHS](https://github.com/charmbracelet/vhs). `demo/render.sh` runs it in a container without network access (podman, or `DEMO_ENGINE=docker`), so nothing is installed on your machine. The recording runs the real `loadout` and the real `bootstrap.sh` in a new sandbox HOME that `demo/sandbox.sh` fills with fake data and stand-in binaries (`demo/bin/`: `claude`, `curl` and `uv` refuse to run outside the sandbox).
- **The Claude Code part** (`demo/claude-clip.mp4`) is recorded by the maintainer with `demo/record-claude.sh`, because it needs a real Claude Code login. It works in a throwaway project in `/tmp` and uses a little plan usage. Watch the clip before committing it: it shows the recording machine's plugins and paths. It always uses the folder `/tmp/loadout-demo/my-app`, so Claude Code asks only once whether to trust it; that answer is stored in your real `~/.claude.json` (under `projects`), where you can remove it after recording. `render.sh` appends it when it exists.

Both tapes share [`demo/style.tape`](demo/style.tape) (font, size, theme, window); title cards come from `demo/card.sh`. Re-render when the output of `bootstrap`, `adopt`, `check` or `init` changes (`init` prints a plan and asks before it writes), and before each release. Keep the GIF under 5 MB (lower the framerate in `render.sh` before shortening pauses). VHS's `Wait` reads the top of the scrollback, so the tapes pace answers with `Sleep` instead; check a render by looking at frames (`DEMO_KEEP_DIR=DIR demo/render.sh` keeps the mp4).

The hero's wordmark (`docs/assets/wordmark.light.svg` and `.dark.svg`) is generated with the letters as outlines: `uv run --with fonttools docs/assets/wordmark.py` (needs JetBrains Mono Bold installed, or pass its `.ttf` path).

## Issues

Open an issue with one of the forms on the [New issue](https://github.com/jonasyr/agent-loadout/issues/new/choose) page; each one asks only for what is needed to act on it:

| Form | Use it for | Asks for |
|---|---|---|
| Bug report | Something does not work as documented | What happened, steps, platform, `loadout --version`, which agents and editors you use (CLI or VS Code extension) and optionally their versions, the output of `loadout check --verbose`; optionally the failing command's output with `--verbose` |
| Feature request | An idea for the CLI, bootstrap or the plugin | The problem or use case; optionally a solution and alternatives |
| Propose a tool for the catalog | Adding, replacing or dropping a tool | Kind, why, what it overlaps, license, install method, maintenance (what a [catalog](docs/how-to/add-to-catalog.md) decision needs) |
| Docs problem | A wrong, missing or unclear page | The page and the problem; optionally a fix |
| Question | Anything else | Your question, what you tried and what you read; optionally your platform |

Blank issues are off. Read command output before you paste it, and replace tokens and private paths. Security problems never go in an issue: use the private advisory form linked on the New issue page (details in [SECURITY.md](SECURITY.md)).

## Commits and pull requests

- Use [Conventional Commits](https://www.conventionalcommits.org/): `type(scope): subject`, for example `feat(catalog): add <tool>`, `fix(adopt): ...`, `docs: ...`, `test: ...`. The PR title follows the same format.
- Work on a branch and open a pull request against `main`. The [template](.github/pull_request_template.md) asks for three things: a summary with the issue it fixes, how you tested it (only what you actually ran, and on which platform), and which docs page you updated or why none was needed.
- Whatever tools you use to write a change, you must understand it and have tested it yourself.
- When Codex's GitHub review quota is used up, ask Claude Code to "run the codex-reviewer agent on this branch" (it applies Codex's open-source review rubric, see [`.claude/agents/codex-reviewer.md`](.claude/agents/codex-reviewer.md)). Post its findings and the fixes as PR comments, and repeat until it reports no findings.
- CI must be green before a merge: the test suite on Linux and on Windows (including the hook scripts under Git Bash), the suite plus a WSL 2 smoke test inside WSL 2, and `claude plugin validate` for the marketplace and the plugin. Pull requests that touch the CLI (`cli/loadout/`), bootstrap, the catalog, templates, rules, the base settings or the hooks also run `fresh-machine`, which installs for real on a clean Ubuntu container and on Windows (experimental, allowed to fail); it also runs weekly.
- Issue forms show only from the default branch and only to signed-in users, so validate them before merging: `uvx check-jsonschema --builtin-schema vendor.github-issue-forms .github/ISSUE_TEMPLATE/[0-9]-*.yml`.
