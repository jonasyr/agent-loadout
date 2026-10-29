# Live tour 2026-10-28 fixes: one honest to-do list, quieter messages, Claude Code extension without its CLI

Status: draft, 2026-10-29. Source: the live tour of cases A–E (backlog section "LIVE TOUR 2026-10-28/29" in `.superpowers/handoff/2026-10-13-hardening-backlog.md`).

## Why

A first-time user reads three things at the end of `loadout bootstrap`: the health check, "Still to do" and "Next". `loadout check` ends with "Now do this". In the tour these disagreed with each other. A FAIL that made the run exit 1 (playwright-cli missing, the loadout plugin missing in Codex) was not in any to-do list. Two rows gave different fixes for one failed marketplace clone. Several lines said the same thing twice, or said nothing useful ("re-run with --install" right after `--install` failed). And a user with only Claude Code's VS Code extension got the Claude Code CLI installed and was told to "run `claude`", while the Codex extension case already treats its CLI as optional.

Success: after any bootstrap or check, the to-do list contains every problem that has a fix, each once, and no line repeats another or contradicts it.

## Goals

### G1. One honest to-do list (findings A3, C1)

- "Still to do" (bootstrap) and "Now do this" (`loadout check`) include every check row that is FAIL or warn **and** has a fix, FAILs first, each with its fix text. (User's choice: every FAIL and warn with a fix.)
- Items already in the list today (gh login, hooks approval, missing Codex plugins, MCP logins, personal repo, git, claude login) stay; a check row that says the same as an existing item is not added a second time. Deduplicate by meaning, not by string: for example the "gh auth" row and the gh-login step are one item, the "Codex hooks" row and the hooks step are one item.
- `optional:` items stay last.
- A failed clone of any Codex marketplace, including `jonasyr/agent-loadout`, is named in the "Codex plugins missing" row and in its to-do line. The "Codex plugin" row (loadout plugin not installed) and "Codex plugins missing" must not give different fixes for the same cause: when the loadout plugin is missing because its marketplace is missing, both point to `loadout update` (it retries), and the to-do list has one line for it.
- `loadout check`'s "Now do this" today shows only saved open steps (`steps.print_pending`). It gains the check rows the same way, so check and bootstrap end with the same kind of list.

### G2. Quieter, truer messages

- **A2 codebase-memory.** When `config get auto_index` fails and a daemon conflict record exists (the data the `codebase-memory-mcp daemon` row reads), say that cause once: bootstrap's codebase-memory line names the conflict, and check shows one row for it (the daemon row), not an auto_index row repeating it with "run … to see why". Without a conflict record the auto_index row stays, but its fix names something to do (for example the command and that its error output says why), not the same command again. Bootstrap prints the codebase-memory problem once, not as status line plus identical indented line.
- **C2 Codex marketplace failure.** "marketplace X: failed: …" shows one readable line: the last meaningful line of git's output (e.g. `RPC failed; curl 56 Recv failure: Connection reset by peer`), never a cut-off path fragment; when the output looks like a network failure, add "network error; `loadout update` retries".
- **B3 failed install.** When `--install` was given and installing a tool failed, Prerequisites says "failed to install X: <reason>" and the missing line says what to do next without "re-run with --install" (e.g. "install it by hand: <manual URL>" from the catalog entry's `manual`, or "fix the error above, then `loadout bootstrap --install`"). The hint "re-run with --install" stays only when `--install` was not given.
- **C3 adopt under `--yes`.** Inside bootstrap with `--yes`, the adopt section does not print "N suggestions … nothing selected". It prints one line naming what is open and the command for it (e.g. "Your existing setup: 4 tool updates and 1 tool to install: `loadout update` / `loadout adopt`"), or nothing when everything is fine. Groups it applies under `--yes` today (remove, migrate, scope-down) keep working and keep their output.
- **A1 This machine.** The "This machine" block does not repeat "X missing and no --install" when Prerequisites will report the same tools in the same run; it keeps the difference only when Prerequisites would not say it (decide by data, not by hiding the difference entirely: the block must still name differences Prerequisites does not show).

### G3. Claude Code's VS Code extension and the Claude Code CLI (findings E1, E2)

User's choice: mirror Codex fully (asked twice; the first question described Codex wrongly, the second settled it).

- When Claude Code is chosen, no `claude` is on PATH, and the extension's bundled `claude` is found, the Claude Code CLI is optional, decided exactly like `codex_cli_choice`:
  - in a terminal without `--yes`: bootstrap asks once whether to also install the Claude Code CLI (default No), parallel to `CODEX_CLI_QUESTION`;
  - with `--yes` or without a terminal: `--install` installs it (today's behaviour);
  - a new flag `--without-claude-cli` skips it (parallel to `--without-codex-cli`, including the warning when it is given but has no effect, and the `recommend.differences` line when a CLI is on PATH anyway);
  - without `--install`: not installed, as today.
- When it is not installed, bootstrap prints one status line parallel to Codex's: "Claude Code CLI not installed (optional): VS Code's Claude Code extension runs its own, and loadout set Claude Code up for it".
- Check mirrors Codex's "Codex CLI" row: a missing `claude` with a bundled one is an ok row with that optional text (today a warn row whose fix says `loadout bootstrap --install`). The `_vscode_surfaces` fixes that say "`loadout bootstrap --install` installs one" stay true and stay as they are.
- E2 "Next": when the Claude Code extension is present, "Next" names it, also when the CLI was installed in the same run: "run `claude` in a new terminal, or open VS Code's Claude Code extension (reload the window if it is open)". Same rule for Codex's extension when its CLI is also there (my call, for symmetry).
- Docs: `--without-claude-cli` in `docs/reference/cli.md`; the setup matrix's Claude Code × VS Code extension cell and `docs/how-to/vscode.md` say the CLI is optional and how the question/flag work. `recommend.FLAGS` stays pinned to the matrix (its test parses the table).

## Decisions after the builder check

- **Fix shown once (user's choice).** A warn/FAIL row whose fix goes into the to-do list is printed in the health block without its `fix:` line; the fix appears only in the numbered list. `--verbose` keeps the `fix:` lines. Rows that stay out of the list (no fix) are unchanged.
- **One list, printed only (my call).** Bootstrap ends with one numbered list ("Still to do"), merging today's `still_to_do` items, the saved open steps it prints today, and the check rows; `loadout check`'s "Now do this" merges saved open steps and its check rows the same way. Check rows are merged at render time and are not written to `open-steps.json`; saved steps, their clearing (`settle`) and the session-start hooks stay as they are.
- **Dedupe (my call).** A check row that has a matching saved step or `still_to_do` item (gh login, hooks approval, missing Codex plugins, MCP logins) is shown once, as the existing item. The mapping lives in one table (row name -> step key), next to `BOOTSTRAP_ROWS` in `steps.py`.
- **"Re-run bootstrap" fixes at the end of bootstrap (my call).** A row whose fix is a bare `loadout bootstrap` is listed as "re-run `loadout bootstrap --verbose` to see why <row> failed"; a fix with specific flags (`--codex-side wsl --vscode-wsl`, `--vscode-path`, `--install` when it was not given) is kept as is. The "Codex plugin" row's fix becomes `loadout update` when the loadout marketplace is missing (G1).

## Non-goals

- `--no-plugins` noise (B1/B2), Serena's pyright download (A4), Serena's per-call approval: backlog, not this PR.
- No change to which checks run, their ok/warn/FAIL level (except the Claude Code CLI row in G3, which mirrors Codex's), or exit codes.
- No change to the Codex CLI's own optional logic beyond reusing it.

## Anti-goals

- A to-do list that grows long with duplicates is worse than today: dedupe is part of G1, not a nice-to-have.
- Hiding a real problem to make output quieter. Every FAIL still appears somewhere with a fix.

## Constraints

- Standard library only; tests with `fake_home`/`fake_runner`; Conventional Commits; no AI attribution.
- The edge-case list in AGENTS.md (Codex-only machines, VS Code Codex without CLI, WSL with Windows Codex, bundled claude as runner, Git Bash).
- Docs: `docs/reference/cli.md` (check output, bootstrap output, new flag), `docs/reference/setup-matrix.md` (Claude Code × VS Code extension cell), `docs/how-to/vscode.md` (Claude Code extension without the CLI), troubleshooting where it quotes the changed lines.

## Code map (from a read-only scout; line numbers approximate)

- G1: `bootstrap.still_to_do` (bootstrap.py ~100) ignores check results; check runs at ~1121 and results only reach `steps.settle`; `steps.derive(set(), [], …)` at ~1137 gets no results. `commands.run_check` → `steps.print_pending` → `steps.block` renders "Now do this" from saved `open-steps.json` only. `codex.missing_routes` drops the loadout plugin's own marketplace on purpose ("left to the Codex plugin row").
- C2: `codex._tail` (~1278) is a fixed `[-300:]` cut; `bootstrap._tail` (~160) already drops the partial first line.
- B3: `bootstrap.check_prereqs` (~281-333), the generic hint at ~318-327 ignores whether `--install` was given or just failed.
- A2: `cbm.apply_auto_index` / `apply.cbm_step` / `bootstrap._report` (duplicate print); `check._cbm_auto_index` and `check._cbm_conflict`.
- C3: `adopt.run(..., yes=True, embedded=True)` → `render_calm` + "nothing selected" (adopt.py ~171, ~517-548).
- A1: `recommend.differences` first rule; `bootstrap._this_machine`.
- G3: `codex_recommended` / `codex_cli_choice` / `CODEX_CLI_QUESTION` (bootstrap.py ~812-834) are the model; bundled claude adds "claude" to `recommended` (~1043, ~943) but `--install` still installs it; `vscode.bundled_claude`, `use_bundled_claude`; "Next" at ~1152-1178.

## Left to the builder

Exact wording of new lines (parallel to existing ones), the dedupe mechanism, whether check rows carry a step key or the mapping lives in `steps.py`, and how "network error" is detected.
