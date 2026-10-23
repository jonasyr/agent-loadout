# Design: Serena's reminder lets harmless searches through

- Date: 2026-10-23
- Status: Approved (2026-10-23)
- Builds on: [ADR 0039](../../adr/0039-serena-remind-tools-load-upfront-cbm-refresh.md) (Serena's `remind` for Claude Code), [ADR 0028](../../adr/0028-serena-codex-hooks-in-hooks-json.md) (Serena's hooks in Codex's `hooks.json`)

## Why

Since #57, the plugin runs Serena's `remind` hook (Serena 2.1.0). It denies the 3rd grep in a row that was made without a Serena symbolic tool in between. It is meant to push agents from grep to Serena when they look for code. In practice it also denies searches where Serena cannot help.

Measured in the Claude Code transcripts on the maintainer's machine since #57 (2026-10-22 17:30 UTC to 2026-10-23), with a scratch script that uses `cli/loadout/searches.py`'s rules:

| What was denied | Denials | Would Serena have helped? |
|---|---|---|
| grep in docs, YAML, TOML, Markdown or config files (also `.gitignore`) | ~8 | no |
| grep behind a pipe (`gh … \| grep`, `loadout check --verbose \| grep`) | 3 | no |
| phrase searches over script folders, grep in note files | ~3 | hardly |
| real code searches (`class FakeRunner`, `def _tail`, `PLUGINS_EXTENSION`, grep in a `.py` file) | ~5 | yes |

That is 19 denials in 9 transcripts, and about two thirds were unnecessary. Each one costs a turn and teaches the agent that the reminder is noise. The maintainer's goal is that Serena and the code graph get used for code. A reminder that fires on config greps works against that goal.

What Serena counts (read from `serena/hooks.py`, 2.1.0, `PreToolUseRemindAboutSymbolicToolsHook`):

- **Greps:** any shell invocation whose program is `grep`, `rg`, `ag`, `ack`, `fgrep`, `egrep`, `ugrep` or `ug`, also behind a pipe. It also counts a native `grep`/`search_for_pattern` tool. It ignores the paths. The grep counter resets after 1000 s without a grep, or when a Serena symbolic tool is used.
- **Reads:** reads count only for files with a code suffix, wherever the file lies. Reads inside the project are therefore fine. Reads outside it are part of this design (goal 3).

## Goals

1. **What passes:** a shell call (Claude Code `Bash`, Codex shell) made up only of harmless searches never reaches Serena's `remind`. It is neither denied nor counted. Harmless means each grep-family invocation in the line is one of these (the maintainer's choice, all four):
   - **behind a pipe:** it filters another command's output (`gh pr view 59 | grep …`). This does not hold when that pipeline reads a code file (see "Edge rules");
   - **config files:** every path operand is a config file (`.toml`, `.json`, `.yaml`, `.yml`, `.ini`, `.cfg`, `.env`, `.lock`, and extensionless config names such as `.gitignore`);
   - **docs and text:** every path operand is a doc or text file (`.md`, `.rst`, `.txt`, `.log`, `.csv`, `.html`, `.xml`, `.jsonl`), or the search is limited to such types (`-t md`, `--include='*.yml'`, `-g '*.json'`);
   - **outside the project:** every path operand lies outside the session's project folder (`~/.codex/config.toml`, `/tmp/…`, `~/.claude/…`).
2. **What still reaches Serena:** everything else goes to `remind` unchanged, so code searches are still reminded:
   - a grep with a code file, a folder or no operand at all;
   - a mixed line that contains any non-harmless grep.
3. **Reads outside the project** (added at the maintainer's approval): a read of a file outside the session's project folder never reaches `remind`, whatever its suffix. This covers Claude Code's `Read` tool with a `file_path` outside the project. It also covers a shell line whose every Serena-counted read and every grep is outside the project or otherwise harmless. Serena does not index those files, so a reminder cannot help. Observed: a `.rs` file from Codex's source in a scratch folder was denied.
4. **Both agents:** the filter applies in Claude Code and in Codex (the maintainer's choice).
5. **An upstream issue:** a draft for oraios/serena, with the measured examples, so the filter can go once Serena filters by itself. The draft is shown to the maintainer. It is posted only after their yes.

## Non-goals

- Changing Serena's thresholds, its messages, or how it counts reads.
- Filtering reads inside the project (Serena already counts only code files there), or Serena's other hooks.
- Re-implementing `remind`. loadout only decides whether to call it.

## Anti-goals (a failure even if it technically works)

- **Code searches get through.** If an agent can grep for `def foo` in `.py` files without a reminder, the change has failed. When in doubt, the call goes to Serena (the maintainer's choice for the edge cases).
- **The hook gets slower or noisier.** `remind` already adds about 0.5 s to each Bash call. The filter must not add a process start: it runs inside the existing `mcp_guard.py` process, in Python, using the standard library only.
- **A user's own Serena hooks change.** A Serena hook the user wrote stays byte for byte. When the user runs their own `remind`, the plugin's copy stays silent, as it does today for Claude Code (two reminders would share one counter).

## Edge rules (the maintainer confirmed: "when in doubt, Serena")

- **Mixed lines:** one non-harmless grep anywhere in the line sends the whole call to Serena.
- **Pipes from code:** a pipe counts as harmless only when no command earlier in that pipeline has a code-file operand. `cat x.py | grep foo` and `sed -n 1,80p a.ts | grep bar` are code searches.
- **Folders and stdin:** a folder operand (`grep -rn X src/`, `grep -r X .`) is code. So is a grep with no operand that is not behind a pipe.
- **Code reads elsewhere in the line:** if the line also reads a code file with a command Serena counts as a read (its `_READ_SHELL_COMMANDS`: `cat`, `head`, `tail`, `sed` without `-i`, `awk`, `less` and others), the whole call goes to Serena, even outside the grep's pipeline (`sed -n 1,80p a.py; grep -n x notes.md`). Serena's combined counter must keep seeing such reads. *(Builder check; my call, following "when in doubt, Serena".)*
- **Unparseable lines:** a line the shell lexer cannot parse goes to Serena.
- **Command substitution:** a grep inside `$(...)` or backticks is classified like any other invocation. Its operands decide.

## Constraints

- **A positive list:** a path is harmless only when its suffix or name is on the non-code list (`searches.py`'s `NON_CODE` plus the extensionless names). Any other suffix goes to Serena, including suffixes neither list knows (`.vue`, `.sql`, `.tf`, `.css`). Serena 2.1.0 counts *reads* of `.json`, `.yaml`, `.yml`, `.toml` and `.html` as code reads. For *greps* in those files, loadout deliberately decides otherwise: the maintainer chose config files as harmless. *(Builder check.)*
- **Hooks cannot import loadout.** Hook scripts in `plugins/loadout/hooks/` run from the installed plugin (AGENTS.md "External commands"). The classification rules are therefore a small copy inside the hook. A test asserts that the hook's suffix lists match `cli/loadout/searches.py`'s `NON_CODE` and `CODE_EXT`, plus the extensionless names this design adds, so the two cannot drift.
- **No process start:** the filter runs before the guard starts `serena-hooks`, in the same process.
- **Agent isolation:** with Codex off, nothing reads or changes `~/.codex`. With Claude Code off, nothing reads or changes `~/.claude` (AGENTS.md "User files").
- **Undo:** loadout removes its own `remind` entry from `~/.codex/hooks.json` only on the existing backed-up path (`bk.save_copy` before the rewrite). `loadout restore` puts the file back. The user's entries stay byte for byte.
- **Tests:** they use `fake_home` and `fake_runner` only.

## How (decided parts)

### Claude Code

`hooks.json` already runs `mcp_guard.py serena serena-hooks remind --client=claude-code` for `Bash|Read|Grep|Glob` and Serena's tools. The guard gains one check for the `remind` subcommand: when the call is a `Bash` call whose command is harmless by the rules above, the guard exits silently without running `serena-hooks`. Every other call is unchanged.

**Builder's choice:** whether to also filter Claude Code's native `Grep` tool. Claude Code on Linux has no Grep tool (ADR 0039), and Serena counts a tool named `grep`. If it is done, the rule is the same: the `path` is non-code or outside the project, or `glob`/`type` limits the search to doc types.

### Codex

Today loadout writes `serena-hooks remind --client=codex` straight into `~/.codex/hooks.json` (`cli/loadout/codex_hooks.py`, `SERENA_HOOKS`), as Serena documents it. That entry cannot be filtered. Changes:

1. **Plugin hook:** `plugins/loadout/hooks/codex.json` gets a `PreToolUse` hook on `Bash` that runs `mcp_guard.py --agent codex serena serena-hooks remind --client=codex`, with the same 5 s timeout Serena documents.
   Codex's payload, read from codex-rs (`core/src/tools/handlers/unified_exec/exec_command.rs`, `hooks/src/events/pre_tool_use.rs`): `tool_name` is `"Bash"`, and `tool_input` is `{"command": "<the shell line as one string>"}`. This is the same `command` Serena reads, so Serena 2.1.0 counts every Codex grep today. The guard reads `tool_input.command` (falling back to `cmd`, as Serena does) and, for robustness, also accepts an argv list the way `searches._words` does.
2. **Guard for Codex:** with `--agent codex`, the guard decides by Codex's files only:
   - **availability:** the binary on PATH and `codex_server_enabled` (already there);
   - **equivalence:** a `serena-hooks remind --client=codex` in `~/.codex/hooks.json` (or `$CODEX_HOME`), in `[hooks]` inside `config.toml`, or in `<cwd>/.codex/hooks.json`. In any of these, the plugin's copy stays silent. This is the same equivalence rule Claude Code uses.

   Without `--agent`, the guard behaves as today (Claude Code).
3. **Migration:** `codex_hooks.apply` stops wanting `remind` in `hooks.json` once Codex runs loadout's plugin hooks. The gate is all of these *(builder check; my call)*:
   - the installed Codex copy of `loadout@agent-loadout` (its folder in Codex's plugin cache) has a `hooks/codex.json` with the guarded `remind`. This is a version check, so an old copy (for example after a failed marketplace upgrade, #59) keeps `remind` in `hooks.json`;
   - that plugin is not switched off in `config.toml` (`[plugins."loadout@agent-loadout"] enabled = false`).

   The check is the same with or without the Codex CLI (VS Code's extension loads the same plugin cache, ADR 0038). In `apply_parts` the hooks part runs before the plugins part. When the gate becomes true only through this run's plugin install or upgrade, `apply_parts` runs `codex_hooks.apply` once more after the plugins part, so one `update` finishes the migration. When the gate later turns false again (plugin removed, switched off, or downgraded), the next run adds `remind` back to `hooks.json`.

   With the gate true, its existing loop removes loadout's own `remind` entry, with a backup. The other five Serena hooks stay in `hooks.json`. If loadout's plugin is not installed for Codex, `remind` stays in `hooks.json` as today. `keep=True` (the background sync) never removes, as today, so the migration happens on the next foreground `bootstrap` or `update`.
4. **No double runs during the migration:** until loadout's old entry is removed, the guard sees it as an equivalent hook and stays silent. It must not count as the user's hook for anything else. It stays loadout's own entry in the record.
5. **Re-approval:** removing an entry shifts the positions Codex keys its hook approvals on. Codex will ask again in `/hooks`. `update`'s existing "approve the changed hooks in /hooks" step covers this. The docs say so.

### Docs

- **A new ADR 0040:** "Serena's reminder skips harmless searches". It amends ADR 0039 (the reminder for both agents now runs through the guard) and ADR 0028 (`remind` moves from `hooks.json` into the plugin when the plugin is installed).
- **Updated pages:** `docs/reference/hooks.md` (the guard's new rule, Codex's table of Serena hooks), `docs/reference/setup-matrix.md` if a row changes, and `rules/tooling.md`'s sentence about the reminder ("it skips searches in config, docs, piped output and files outside the project").

### The upstream issue

A draft in the PR description or a scratch file. It covers:

- the counting rule in 2.1.0 (path-blind grep counting);
- the four example classes, with real anonymised commands from the measurement;
- the proposal: apply the same path check `is_read_code_file_call` already does for reads to grep operands as well, and skip greps that read from a pipe.

## Upstream issue: what it proposes

The issue does not ask Serena to adopt loadout's config list. It asks for two things Serena can judge for itself:

1. **Path-aware greps:** check grep operands the way `is_read_code_file_call` checks read operands, so a grep whose every operand is a non-code file is not counted.
2. **No counting for pipe filters:** a grep behind a pipe filters another command's output, so it is not counted.

It mentions that Serena's code suffixes include `.json`, `.yaml`, `.toml` and `.html`, and asks whether greps over config files should count. loadout's own filter stays either way.

## What is left to the builder

- **Where the classifier lives:** inside `mcp_guard.py` or a sibling module the guard imports (hooks can import siblings in their own folder).
- **The extensionless config names:** at least `.gitignore`, `.gitattributes`, `.editorconfig`, `.env*`, `.npmrc`, `.dockerignore`, `Makefile`, `Dockerfile`, `LICENSE` and `CODEOWNERS`. Extend the list where it is obvious.
- **How "outside the project" resolves:** `~`, relative paths against the payload's `cwd`, and `..`. The project folder is the payload's `cwd`. No git calls.
- **The Grep tool:** whether to filter Claude Code's native `Grep` tool (see above).
- **Tests:** shapes and naming, in the existing style of `tests/test_mcp_guard.py` and `tests/test_codex_hooks.py`.

## Success

- **Re-measured:** around 2026-10-29, with `loadout usage` and the same scratch measurement. Most denials hit real code searches. "Sessions with a Serena reminder" may fall. Serena and code-graph use per session should not fall against the backlog's "Before" numbers.
- **No new prompts:** none beyond the one-time Codex `/hooks` re-approval.
