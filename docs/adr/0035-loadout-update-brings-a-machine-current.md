# 0035. `loadout update` brings a machine current

- Status: Accepted
- Date: 2026-10-19
- Source: [Design: smooth update](../superpowers/specs/2026-10-19-smooth-update-design.md)
- Amends: [ADR 0015](0015-claude-code-installs-synced-plugins.md) (loadout installs new kit plugins on `loadout update`) and [ADR 0024](0024-codex-parity-update-model.md) (`loadout update` covers more than a plugin refresh)

## Context

On 2026-10-19 the maintainer updated his own machine after merging #52. It took five commands and a lot of guessing:

1. `loadout update --yes` ran for over two minutes. One step (a Codex marketplace clone) sat for minutes without output.
2. A `loadout bootstrap` started meanwhile skipped Codex with "another loadout run is setting up Codex right now; run this again when it has finished".
3. The update refreshed plugins and tools but not the rules block in `~/.codex/AGENTS.md`, so `loadout check` failed `Codex instructions` and a second bootstrap was needed.
4. Nothing said that Claude Code needed `/reload-plugins`, that an upgraded MCP server needed a `/mcp` reconnect, or that Codex wanted `/hooks` approval again.
5. The daily sync was paused because the kit checkout had an untracked file and a tool had rewritten a tracked file; the only message was "commit or discard changes".
6. A `~/.codex/hooks.json` in another indent style was left alone, so Serena's hooks were added by hand.

The forces:

- [ADR 0011](0011-tool-binaries-notice-and-deliberate-update.md) wants a deliberate update: a bad upstream release must not land by itself, and each tool command is shown before it runs.
- [ADR 0015](0015-claude-code-installs-synced-plugins.md) left new plugins to Claude Code's own start-up install, and [ADR 0024](0024-codex-parity-update-model.md) made `loadout update` the one deliberate plugin refresh. Neither made update re-apply the setup, so the machine was only half current.
- The daily sync pulls without asking and installs nothing; that is why it is safe to run unattended.
- A friend who installed loadout once and runs `loadout update` weeks later has no maintainer's memory of which follow-up command is needed.

## Decision

We will make `loadout update` the one deliberate command that brings a machine current, and keep the daily sync as it is.

- **Pull, restart, plan, one yes.** `update` pulls the kit and the personal layer first, asking nothing (as the daily sync does). When the kit pull brought commits, it restarts itself into the pulled code (`LOADOUT_UPDATE_PULLED=1`), so old and new modules never mix. It then prints one numbered plan, with each tool's exact command and version change (ADR 0011 stands), and asks once: `Apply all? [Y/n, or the numbers to leave out]`. `--yes` takes all; without a terminal and without `--yes` it changes nothing. `LOADOUT_NO_AUTO_PULL=1` skips update's pull too: the variable is the switch for "no kit code changes without my review".
- **Re-apply, install, refresh.** After the yes, `update` re-applies the setup through the apply steps bootstrap shares (`apply.py`): links, settings merge, personal MCP servers, Codex rules block, `config.toml` entries, Serena's hooks, skills. It installs new kit plugins in Claude Code and Codex and missing required tools, and refreshes the rest. Recommended tools are optional and installed only when the person types their number. Bootstrap's other steps (PATH block, secrets file, adopt review, VS Code switches) stay bootstrap's.
- **The daily sync installs nothing.** It still pulls, merges and refreshes; it installs no plugin or binary and runs no installer.
- **The pull pauses only when git refuses.** There is no clean-tree gate. Untracked files and edits to files the pull does not touch no longer pause it; `git pull --ff-only` refuses on its own when a change would be overwritten, and that refusal (or a diverged branch) is the only pause. It is recorded with the files git named and the command to fix it, in the notice and in `loadout check`. Network failures are not a pause.
- **Say what is left.** The run ends with "What changed" and a numbered "Now do this" per agent (`/reload-plugins`, `/mcp` reconnect, `/hooks` approval, restart Codex), derived from what the run observed. The same steps are saved and shown at that agent's next session start until done.
- **Runs wait for each other.** A foreground command that needs a lock another run holds waits for it and continues by itself (the background job gives up silently). A lock whose holder process is gone is taken over only when host, PID namespace and boot match.

## Alternatives considered

- Make the daily sync install and re-apply everything: the person would not decide when a new binary or plugin arrives, which ADR 0011 rules out.
- Leave `update` as a plugin and tool refresh and document the follow-up commands: that is today's five-command scenario.
- Keep the clean-tree gate and only name the files: a harmless untracked file still stopped the pull; git already knows exactly which changes conflict.
- A second question per category (plugins, tools, re-apply): one plan and one yes is the whole decision for a person who wants to be current.
- Fold bootstrap's remaining steps into `update`: the PATH block, the secrets file and the adopt review ask questions of their own and belong to a first setup.

## Consequences

- Good: one command, one question, a visible progress line per step, and a closing list of what only the person can do.
- Good: untracked files and unrelated edits in the kit checkout no longer stop the pull; a real conflict is named with its files and fix.
- Neutral: the session hook now passes `--agent claude` or `--agent codex`, which changes the plugin's hook file. A Codex user approves the changed hooks in `/hooks` once after this update; the "Now do this" list says so.
- Neutral: a plugin copy from before this change passes no `--agent` and shows notices only, not open steps, until its plugin is refreshed.
- Bad: `update` does more than before, so a first run after a long gap takes longer. Codex marketplaces whose upstream did not change are skipped to keep that short.
- Bad: a dirty kit checkout that used to be skipped is now pulled whenever git allows it. That is the same rule git applies to any `git pull`, and git never overwrites a change.
- ADR 0011 stands: nothing is installed without a yes, and the weekly check only notifies. ADR 0015 still describes Claude Code's own start-up install; update adds an install on the person's command.

## In the code

- `cli/loadout/update.py` (`run`, `build_plan`, `confirm`, `report`), `cli/loadout/apply.py` (the shared apply steps), `cli/loadout/steps.py` ("Now do this"), `cli/loadout/locks.py` (waiting and takeover)
- `cli/loadout/maintenance.py` (`pull`, `session_start`, `update`), `cli/loadout/codex.py` (`unchanged_routes`), `cli/loadout/jsonio.py` and `cli/loadout/codex_hooks.py` (the hooks file in its own style)
- [`loadout update`](../reference/cli.md#loadout-update), [The daily sync](../reference/state-and-sync.md#the-daily-sync)
