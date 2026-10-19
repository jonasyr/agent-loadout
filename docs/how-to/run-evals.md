# Run the skill evals

Use this page to check that the plugin's skills (onboard, configure, docs-audit, docs-sync, execution-advisor, usage) still behave after you changed them. The evals are in `plugins/loadout/evals/`. Each case has a prompt, a scaffold that builds a fixture repo, and graders.

## Run them

Only through `run.sh`:

```bash
plugins/loadout/evals/run.sh
plugins/loadout/evals/run.sh --case 'onboard-*' --runs 2 -j 3
```

Options after the script go to `claude plugin eval`. The useful ones:

| Option | Meaning |
|---|---|
| `--case <glob>` | Run only the cases whose name matches. |
| `--runs N` | Runs per case. Without it, a case's own `runs:` applies, and `claude plugin eval` uses 3 when the case sets none. |
| `-j N` | Run up to N agent runs at once. They share one rate limit. |
| `--keep-temp` | Keep the scaffold directories, to see what the agent saw. |
| `--ablation none` | Skip the no-plugin baseline runs (about half the cost; no score delta). |
| `--max-cost-usd USD` | Stop when the estimated cost (at API prices) reaches the ceiling. |

Results land in `plugins/loadout/evals/results/<timestamp>/`, which git ignores (with `--eval-dir evals-browser`: in `plugins/loadout/evals-browser/results/`, also ignored). The HTML report is not published (`run.sh` passes `--no-publish`).

## What it costs

The runs are real model calls with your own Claude credential: on a subscription they count against your plan's usage limits, with an API key they are billed. A full run is every case three times (no case sets a different `runs:`), plus a baseline run without the plugin for each (`claude plugin eval`'s default `--ablation with-without`, since `run.sh` passes the plugin's path). While you iterate, run one case with `--case`, and add `--ablation none` to skip the baseline.

## Never run `claude plugin eval` on the plugin directly

Every scaffold sources `evals/lib/common.sh`, which refuses to run unless `run.sh` set up its safety rails:

- **Stubs first on `PATH`.** `loadout` is replaced by a stub, because the real one reads and writes your setup and its session hook can start `loadout maintenance` (a `git pull` of the kit and your personal layer).
- **Browsers are stubbed.** `playwright-cli` is a logging stand-in, and `chromium`, `chromium-browser`, `google-chrome`, `google-chrome-stable`, `firefox` and `playwright` fail with exit 127 and log the call to `./.browser-calls.log`. A real browser crashes inside the run's sandbox and leaves core dumps. The cases grade the tool choice and the calls, not screenshots.
- **A temporary home.** The scaffold refuses to run unless `HOME` is a temporary eval home, never your real one.
- **A global-state check.** `run.sh` takes a checksum of your `~/.claude/settings.json`, `~/.claude/CLAUDE.md`, the MCP servers in `~/.claude.json` and your personal layer (at the default path `~/.config/loadout/personal`, not a `LOADOUT_PERSONAL` folder) before and after. If anything changed it prints the difference and exits with 3.

## The browser case

The routing check for the UI-verification rule is opt-in, because a `PATH` stub cannot stop an agent that calls a browser by absolute path:

```bash
plugins/loadout/evals/run.sh --eval-dir evals-browser
```

Run it only on a machine where a crashing headless browser is acceptable.

## Add or change a case

A case is a folder under `plugins/loadout/evals/` with `case.yaml` or `prompt.md`, `scaffold.sh` and `graders/*.md`. A regex grader that anchors with `^` or `$` on a multi-line target needs `flags: m`. `tests/test_evals_static.py` checks the structure without model calls; run it with the normal test suite.
