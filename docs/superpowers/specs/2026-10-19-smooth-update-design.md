# Smooth update: one command, clear about what happened and what to do

Date: 2026-10-19. Status: design, approved answers from the maintainer (2026-10-19).

## Why

On 2026-10-19 the maintainer updated his own machine after merging #52, and it took five commands and a lot of guessing:

1. `loadout update --yes` ran for over two minutes. One step ("adding marketplace anthropics/claude-plugins-official, a git clone (3 of 15)") sat for minutes without output while Codex cloned every plugin source of that marketplace, so it looked hung.
2. A `loadout bootstrap` started during it skipped Codex: "another loadout run is setting up Codex right now; run this again when it has finished".
3. The update refreshed plugins and tools but not the rules block in `~/.codex/AGENTS.md`, so `loadout check` failed `Codex instructions` with "fix: loadout bootstrap", and a second bootstrap was needed.
4. Nothing at the end said that Claude Code needed `/reload-plugins`, that codebase-memory's MCP server had dropped because its binary was upgraded (`/mcp` reconnect), or that Codex wanted `/hooks` approval again.
5. The daily sync was paused because the kit checkout had an untracked file and Serena (1.7.0) had rewritten `.serena/project.yml`; the only message was "commit or discard changes in <kit>".
6. Serena's Codex hooks were missing from a `~/.codex/hooks.json` that loadout does not rewrite (4-space indent), so they had to be added by hand.
7. `loadout check` warned "own tools: 1 tool(s) not managed by loadout" for the user's own Serena in `config.toml` (after `serena setup codex`), although loadout treats any Serena as the kit's tool elsewhere (backlog item 22).

If this is bumpy for the developer, it is worse for a friend who installed loadout once and runs `loadout update` a few weeks later.

## Goal

`loadout update` is the one command that brings a machine fully current. While it runs, every step says what it does; when it ends, one short block says what changed and, numbered, the few things only the person can do, per agent. The same steps reach the agent at the next session start until they are done.

Success: on the scenario above, a person runs `loadout update`, answers one question, waits with a visible progress line, and ends with a list like:

```
What changed
  loadout plugin: updated in Claude Code and Codex
  rules: Codex's AGENTS.md block updated
  codebase-memory-mcp 0.11.0 -> 0.12.1
  an installer's 3 hook scripts moved to a backup (undo: loadout restore …)

Now do this
  1. Claude Code: run /reload-plugins, then /mcp and reconnect codebase-memory-mcp (it was upgraded)
  2. Codex: start codex and approve the changed hooks in /hooks
```

and nothing else is needed.

## Non-goals

- Doing what only the person or the agent may do: loadout never runs `/reload-plugins`, reconnects MCP servers, approves Codex hooks, logs in, or trusts a folder. It names them.
- Changing what the daily background sync does beyond the pause rule below (it stays quiet and never installs binaries).
- The CLI's "recommended setup for this machine" (separate backlog item) and the audit's fix PR items other than 22.

## Anti-goals (a failure even if it works)

- An update that changes a user's file it did not record as its own, or rewrites a file it cannot reproduce byte for byte (AGENTS.md "Code Review Rules": exact-text record, parse guard, atomic write, backup first).
- A summary that claims a step is needed when it is not, or misses one that is (the steps come from facts the run observed, not from a fixed list).
- Hiding a failure behind the summary: a failed step is in "What changed" as failed, with its fix.
- A progress display that breaks piped output or CI logs (no carriage-return tricks when stdout is not a terminal).

## Decisions (the maintainer's answers)

1. **Scope: one command for everything.** `loadout update` runs, in order: pull the kit and the personal layer (same rules as the daily sync, see 5; the pull asks nothing, as the daily sync does not), then restarts itself into the pulled code (the existing re-exec pattern, `LOADOUT_REEXEC`, so no old and new modules mix; the restarted run does not pull again), then shows the plan and asks (7), then re-applies the setup as bootstrap's apply steps do for each agent that is on (rules and settings, personal MCP servers, the Codex rules block, `config.toml` entries, Serena's Codex hooks, skill links), refreshes plugins, updates tools, undoes what installers re-registered, then a health check. Nothing else is ever needed afterwards except the steps in "Now do this".
   - **New items (answer 2026-10-19):** what is wanted now but not installed is installed too, and is in the plan: new kit plugins in both agents (Claude Code through bootstrap's `setup_plugins` path, Codex through `apply_plugins` as today) and new required catalog tools; new recommended tools are listed as optional and left out unless the person keeps them. Bootstrap's other steps (the PATH block, the secrets file, `--vscode-path`, the adopt review) stay bootstrap's; when one of them is needed, "Now do this" names `loadout bootstrap`.
2. **After steps: end summary plus agent notice.** "Now do this" lists only the steps that apply, numbered, grouped by agent, each with the reason. The same steps are stored per agent in loadout's state folder (not the one-time notice file, which the first session of either agent consumes) and shown at each session start of that agent only until done. Done means: a Claude Code step (`/reload-plugins`, `/mcp` reconnect) clears at the next Claude Code session start, since a new session loads the new plugins and MCP servers; a Codex `/hooks` step clears when `loadout check` sees the approval (`hooks_status`); a "restart Codex" step clears at the next Codex session start.
3. **Slow steps: skip unchanged, live progress.** A Codex marketplace and each of its plugins are refreshed only when their upstream changed since loadout last refreshed them: for each git source, `git ls-remote` (no clone) gives the remote head, compared with the head recorded at the last refresh in loadout's state folder (with the marketplace's `marketplaceName`, since a skipped `marketplace add` does not return it). Only changed plugins are re-added; anything loadout cannot compare is refreshed as today. (Builder check: a marketplace commit can stay the same while a plugin's source repo changes, so the plugin sources are compared too.) For each step that runs: a line with the step, item n of m and the elapsed seconds, updated in place on a terminal; one line per item when not a terminal. A step that can take minutes says so when it starts ("Codex clones each plugin's source; this can take a few minutes").
4. **Two runs: wait, then continue.** A second loadout run that needs a lock another run holds prints "waiting for the other loadout run (<command>, started <time>)…" with an elapsed timer on a terminal and continues by itself when the lock is free; Ctrl+C stops it with the existing interrupt message. Without a terminal it waits too, with one line, up to a limit (builder's call, a few minutes), then stops with a clear message. This replaces "run this again when it has finished" everywhere it appears.
5. **Sync paused: pull when safe, name files.** Untracked files and local changes that the incoming commits do not touch no longer pause the pull. loadout lets git decide: `git pull --ff-only` refuses on its own when a local change or an untracked file would be overwritten, and that refusal is the only pause. When it pauses, the notice and `loadout check` name the files (escaped) and the exact command (for example "commit or stash .serena/project.yml in <kit>, then run loadout update"). A branch without an upstream, a detached HEAD or a diverged branch is skipped with its own plain reason, as today.
6. **Files in another format: keep the format, add with a backup.** For `~/.codex/hooks.json` (and any other file where loadout today says "loadout does not rewrite a file in another format"): if loadout can serialize the parsed file back to exactly the bytes on disk with a detected style (indent width 2 or 4, ensure_ascii or not, LF or CRLF, final newline, key order as parsed), it adds the missing entries in that style after a backup copy and records them as its own. Only when no detected style reproduces the bytes does it list the entries for the person, as today.
7. **Asking: one plan, one yes.** After the pull and restart (1), update prints the numbered plan (re-apply, plugins to install or refresh, each tool with its versions and command source, Codex marketplaces to refresh or skip) and asks once: `Apply all? [Y/n, or the numbers to leave out, e.g. 3 5]`. `--yes` takes all; without a terminal and without `--yes` it shows the plan and changes nothing (today's non-interactive rule). A tool update left out (by number or by n) is recorded as declined for that version, so the weekly notice stays quiet until a newer version than the one offered appears; this extends `_remember_refused`, which today records only an update that installed nothing newer. A wrong answer asks again (as the restore picker does).
8. **Explain: short summary, details with `--verbose`.** The raw commands and per-item lines move behind `--verbose`; the default output is the progress lines, "What changed" (one plain line per change, with its undo where a backup was made) and "Now do this".

## What triggers each "Now do this" step

From facts of this run (the builder names the exact detection):

- Claude Code plugins changed (any `claude plugin update` that updated, or the loadout plugin copy differs afterwards): "Claude Code: run /reload-plugins (or restart it)".
- An MCP server's binary that a plugin or personal entry starts was upgraded in this run (codebase-memory-mcp, serena, or any catalog binary that is an MCP command): "Claude Code: run /mcp and reconnect <name>"; for Codex: "restart Codex" (Codex starts MCP servers per session).
- Codex plugins or loadout's Codex hooks changed, or Serena's hooks were added: "Codex: start codex and approve the changed hooks in /hooks".
- Rules or settings changed while a session may be open: covered by the restart line; no separate step.
- A step that failed: listed under "What changed" as failed with its fix; not under "Now do this" unless the fix is the person's.

## Bug 22 (in this change)

`inventory._codex_items` must skip `config.toml` server tables that start Serena (`codex.is_serena`), as `codex` drift already does, so a Serena set up with `serena setup codex` is not an "own tool".

## Constraints

- Python 3.11+, standard library only; external commands only through `runner.run` with argument lists.
- With an agent off, nothing reads or changes that agent's files (ADR 0030 rule in AGENTS.md).
- Every destructive change is undoable (backup step before it acts); the summary names the undo.
- Output follows `out.py` (calm status lines, `--verbose`); every printed path or name from files is escaped with `out.printable`.
- Tests use `fake_home` and `fake_runner`; Windows and WSL CI must pass (host binary helpers, POSIX-only tests skip on Windows).
- Docs: `docs/reference/cli.md` (`loadout update`), `docs/reference/state-and-sync.md` (the pause rule), `docs/how-to/troubleshooting.md` (the paused-sync and waiting rows), `docs/explanation/architecture.md` if the update's place changes; an ADR if decision 1 or 5 changes an accepted ADR's decision (the builder checks 0011, 0015, 0024).

## Left to the builder

- How update reuses bootstrap's apply steps (a shared function, not a copy).
- The marketplace "changed upstream" check and where its record lives (loadout's state folder).
- The wait limit without a terminal and the lock-holder description.
- The exact wording of every line, in the style of the existing output.
- How "Now do this" steps are marked done (which check rows clear which step).
