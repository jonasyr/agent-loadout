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

## Commits and pull requests

- Use [Conventional Commits](https://www.conventionalcommits.org/): `type(scope): subject`, for example `feat(catalog): add <tool>`, `fix(adopt): ...`, `docs: ...`, `test: ...`.
- Do not add `Co-Authored-By` or any other attribution trailer to commits or pull requests.
- Work on a branch and open a pull request against `main`. Say what changed and why, and how you tested it.
- CI must be green before a merge: the test suite on Linux and on Windows (including the hook scripts under Git Bash), and `claude plugin validate` for the marketplace and the plugin.

Security problems: do not open a public issue with details. See [SECURITY.md](SECURITY.md).
