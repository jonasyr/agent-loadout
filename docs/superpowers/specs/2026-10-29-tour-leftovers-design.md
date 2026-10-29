# Tour leftovers: `--no-plugins` without noise, and the small review leftovers

Status: draft, 2026-10-29. Source: live tour 2026-10-28 (case B) and the reviews of #72 (backlog: "LIVE TOUR 2026-10-28/29", "TOUR FIX PR final review — deferred minors", the vscode.md nit).

## Why

In tour case B, `loadout bootstrap --no-plugins` ended with exit 1. Its health check marked "loadout plugin not installed in Codex" as FAIL and listed 11 missing plugins, and gave fixes that undo the user's own choice. That's noise about a decision the user made a minute earlier. The reviews of #72 also left a few small rough edges in the output and one stale doc line.

## Goals

### G1. `--no-plugins` (user's choice: that run only)

- In a `loadout bootstrap --no-plugins` run, check rows that are not ok **only because plugins or marketplaces were not installed** don't show as FAIL or warn, don't become to-do items, and don't make the run exit 1. Examples: the loadout plugin missing in an agent, kit plugins or marketplaces missing in Codex or Claude Code, the Codex marketplace staging row if it is about plugins.
- Instead the health block shows one info line, like the `Setup` line, for example `plugins skipped (--no-plugins): run loadout bootstrap without it to add them`. It shows only when at least one row was actually hidden (user's choice: health block only, no new step heading).
- Hidden rows don't count in "Health check: N of M OK", the status colour or the exit code (user's choice).
- Other rows (binaries, config, hooks and so on) are unchanged.
- Nothing is remembered. A later `loadout check` or `loadout update` reports missing plugins as today.
- A row that also has another cause (for example a plugin present but out of date) is not the builder's to classify perfectly. Hide only rows whose not-ok state is "missing", and leave "stale" or "broken" rows as they are (builder decides by the row's data, never by matching words in its text).

### G2. Small leftovers

- **One line for an ignored CLI flag (user's choice: the Prerequisites line).** When `--without-claude-cli` or `--without-codex-cli` is given while that CLI is on PATH, only the Prerequisites line `--without-…-cli: not used; …` is printed. The "This machine" difference line `--without-…-cli given while a … CLI is on PATH` goes. Remove both rules from `recommend.differences`, together with its now-dead `missing` rule and parameter (bootstrap always passes `[]`). Update `docs/reference/cli.md`, which today names the line that goes.
- **"Next" with an extension next to its CLI (user's choice: two short lines).** Line one: `Next: run `claude` or `codex` in a new terminal.` (as today). Line two, only when an extension is present next to its CLI: `Or open VS Code's Claude Code or Codex extension (reload the window if it is open).`, naming only the extensions that are present. The case where an extension is used without its CLI stays as it is today (`, and open VS Code's Claude Code extension`).
- **Empty adopt step (user's choice: nothing).** Under `bootstrap --yes`, when adopt has nothing to report, apply or warn about (no `yes_line`, no secret findings, nothing applied), bootstrap prints no "Adopt existing setup" step heading and no blank lines.
- **Docs.**
  - `docs/how-to/vscode.md` line ~10 recommends letting `--install` install the Claude Code CLI too. Reword it to match the question: in a terminal, answer y; without one, `--install` installs it unless `--without-claude-cli`.
  - New troubleshooting entry (user's choice: document it). In Codex or Claude Code, Serena says it "could not initialize" or that its language server "terminated" on first use. The cause: on first use, Serena downloads its Python language server (pyright) from PyPI, and it doesn't use the pyright that loadout installed. It needs the network once; retry when online. Link Serena's docs if there is a stable page; otherwise state it plainly.

## Decisions after the builder check

- **To-do items not built from check rows (my call).** `still_to_do` → `codex.open_steps()` adds the missing-plugins item on its own. In a `--no-plugins` run it doesn't (a `plugins` flag through `still_to_do` / `open_steps`). Saved steps (`steps.save`/`settle`) are left alone.
- **Which rows count as "missing" (my call):**
  - Claude Code's "plugins installed" row: hidden when its plugins or marketplaces are only missing. It stays when a marketplace is declared nowhere, or the JSON is invalid (config problems).
  - "Codex plugin" while the Codex in use is too old to install plugins (`no_plugin_command()`): stays.
  - "Codex plugin" (loadout plugin not installed) and "Codex plugins missing": hidden.
  - `loadout plugin (<agent>)` rows: never hidden. They exist only when a copy is installed and say it's stale.
  - "Codex marketplace staging": never hidden. It reports leftover clones, not a missing plugin.
- **"Next" (my call).** The second line replaces the appended "or open VS Code's … extension" in all three variants: "run … in a new terminal", "run … (restart it if it is open)", and the verbose "Then start / Restart …".
- **Windows side.** With Codex set up by `bootstrap.ps1` on Windows, its rows are already out of the list, and no Codex row adds to the info line.

## Non-goals

- Remembering `--no-plugins` across runs.
- Changing Serena's configuration or pointing it at loadout's pyright.
- Codex's per-call approval prompt for `serena_repl`.

## Anti-goals

- Hiding a real plugin problem that `--no-plugins` didn't cause, such as a broken install or a stale copy.
- A bootstrap exit code of 0 when something else failed.

## Constraints

- Standard library only. Tests use `fake_home` and `fake_runner`. Conventional Commits, no AI attribution.
- Edge cases from AGENTS.md: Codex-only machines, VS Code's Codex extension without the CLI, WSL with a Windows Codex, and the bundled `claude`. `--no-plugins` together with the Codex gate on the Windows side must not print the info line for Codex.

## Code map (approximate)

- **Plugin rows:**
  - `check._plugins` (check.py ~69);
  - the `loadout plugin (<agent>)` rows (check.py ~179);
  - `codex.checks` "Codex plugin" and "Codex plugins missing" (codex.py ~2308-2317);
  - `check._codex_staging` (~991).
- **Bootstrap:**
  - the `plugins` flag reaches `_bootstrap`;
  - the health block and the to-do list are at the end of `_bootstrap`;
  - `steps.row_items` and `todo_block` build the list.
- **Other pieces:**
  - `recommend.differences`;
  - bootstrap's "Next" (~1195-1215);
  - `adopt.run(..., embedded=True)` and bootstrap's adopt step (~1105).

## Left to the builder

- How the plugin rows are marked (a `CheckResult` field, or a set of row names plus a "missing" test).
- The exact info-line wording, parallel to the existing lines.
- How the empty adopt step is detected.
