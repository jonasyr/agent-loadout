# Run the skill evals

Use this page to check that the plugin's skills (onboard, configure, docs-audit, docs-sync, execution-advisor) still behave after you changed them. The evals are in `plugins/loadout/evals/`. Each case has a prompt, a scaffold that builds a fixture repo, and graders.

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
| `--runs N` | Runs per case (the default comes from the case, usually 3). |
| `-j N` | Run up to N agent runs at once. They share one rate limit. |
| `--keep-temp` | Keep the scaffold directories, to see what the agent saw. |
| `--max-cost-usd USD` | Stop when the cost ceiling is reached. |

Results land in `plugins/loadout/evals/results/<timestamp>/`, which git ignores. The HTML report is not published (`run.sh` passes `--no-publish`).

## What it costs

The runs are real model calls with your own Claude credential, so they use your plan's usage. A full run is expensive: an earlier estimate was about $8 at API prices. Run one case with `--case` while you iterate.

## Never run `claude plugin eval` on the plugin directly

Every scaffold sources `evals/lib/common.sh`, which refuses to run unless `run.sh` set up its safety rails:

- **Stubs first on `PATH`.** `loadout` is replaced by a stub, because the real one reads and writes your setup and its session hook can start `loadout maintenance` (a `git pull` of the kit and your personal layer).
- **Browsers are stubbed.** `playwright-cli` is a logging stand-in, and `chromium`, `chromium-browser`, `google-chrome`, `google-chrome-stable`, `firefox` and `playwright` fail with exit 127 and log the call to `./.browser-calls.log`. A real browser crashes inside the run's sandbox and leaves core dumps. The cases grade the tool choice and the calls, not screenshots.
- **A temporary home.** The scaffold refuses to run unless `HOME` is a temporary eval home, never your real one.
- **A global-state check.** `run.sh` takes a checksum of your `~/.claude/settings.json`, `~/.claude/CLAUDE.md`, the MCP servers in `~/.claude.json` and your personal layer before and after. If anything changed it prints the difference and exits with 3.

## The browser case

The routing check for the UI-verification rule is opt-in, because a `PATH` stub cannot stop an agent that calls a browser by absolute path:

```bash
plugins/loadout/evals/run.sh --eval-dir evals-browser
```

Run it only on a machine where a crashing headless browser is acceptable.

## Add or change a case

A case is a folder under `plugins/loadout/evals/` with `case.yaml` or `prompt.md`, `scaffold.sh` and `graders/*.md`. A regex grader that anchors with `^` or `$` on a multi-line target needs `flags: m`. `tests/test_evals_static.py` checks the structure without model calls; run it with the normal test suite.
