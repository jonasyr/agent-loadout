# 0040. Serena's reminder skips harmless searches

- Status: Accepted
- Date: 2026-10-23
- Source: [Design: Serena's reminder lets harmless searches through](../superpowers/specs/2026-10-23-serena-remind-non-code-design.md)
- Amends:
  - [ADR 0039](0039-serena-remind-tools-load-upfront-cbm-refresh.md): Serena's `remind` runs behind loadout's guard in both agents, and the guard skips harmless calls;
  - [ADR 0028](0028-serena-codex-hooks-in-hooks-json.md): Codex's `remind` moves from `~/.codex/hooks.json` into the plugin once the installed copy carries it.

## Context

Serena 2.1.0's `remind` counts a shell call as a grep when any invocation is `grep`, `rg` or a relative of them. It looks neither at the paths nor at whether the grep reads from a pipe. Reads are different: there it counts only code files.

The measurement covers the maintainer's Claude Code transcripts from #57 (2026-10-22 17:30 UTC) to 2026-10-23, classified with `cli/loadout/searches.py`'s rules:

| What was denied | Denials | Would Serena have helped? |
|---|---|---|
| grep in docs, YAML, TOML, Markdown or config files (also `.gitignore`) | ~8 | no |
| grep behind a pipe | 3 | no |
| phrase searches over script folders, grep in note files | ~3 | hardly |
| real code searches | ~5 | yes |

That is 19 denials in 9 transcripts, and about two thirds were unnecessary. A reminder that fires on config greps teaches agents to ignore it.

For Codex, `remind` sat in `~/.codex/hooks.json` as Serena documents it, so loadout could not filter it. Codex sends a shell call to its hooks as `tool_name: "Bash"`, `tool_input: {"command": "<line>"}` (codex-rs `exec_command.rs`), so Serena counted every Codex grep as well.

## Decision

- **A harmless call never reaches `remind`.** loadout's guard (`hooks/mcp_guard.py`) asks `hooks/harmless.py` before it runs `serena-hooks remind`.
  - **Which `Bash` line is harmless:** one whose every grep-family search is behind a pipe (not fed by a code-file read), over config, doc or text files, or over files outside the session's folder. It must also read no code file of the project.
  - **Which `Read` or `Grep` tool call is harmless:** one with a non-code path or a path outside the folder.
  - **Anything else goes to Serena:** code files, folders, no path, variables, unknown suffixes, mixed lines, and lines that do not parse.
  - **Only simple lines:** a line with a `cd`, a loop, a group, a subshell or a substitution goes to Serena whole. Codex's review found one shell edge case after another in a classifier that followed `cd`s and compound commands. A strict rule that sends those lines to Serena still covers every class measured above.
  - **How the rules are kept:** they mirror Serena's own shell parsing. Their non-code list equals `loadout usage`'s, and a test keeps the two equal.
- **Codex gets the same filter.** The plugin's `codex.json` runs `mcp_guard.py --agent codex serena serena-hooks remind --client=codex` on `Bash`. With `--agent codex`, the guard decides by Codex's files only. Equivalent hooks count wherever Codex reads them: `hooks.json`, `[hooks]` in `config.toml`, and the project's `.codex/hooks.json`.
- **When `remind` leaves `hooks.json`:** `codex_hooks.apply` removes loadout's own `remind` entry from `hooks.json`, with a backup. It does so only when both hold:
  - the installed Codex copy of `loadout@agent-loadout` carries the guarded hook;
  - `config.toml` switches that plugin on (`enabled = true`).

  This happens in a foreground run, and in the same run as the plugin upgrade. The background sync never moves the entry and never puts it back. With an older copy, or with the plugin off or removed, the entry stays in `hooks.json` or comes back. A user's own `remind` stays theirs. While both exist, the plugin's copy stays silent.
- **Upstream:** a draft issue for oraios/serena proposes path-aware grep counting and no counting for pipe filters. loadout's filter can go once Serena does both.

## Alternatives considered

- **Only report it upstream:** the denials continue until Serena changes. This is a selling point of the kit and cannot wait.
- **Count config files as code, as Serena does for reads:** most config greps were key lookups (`grep -n "^\[section" config.toml`), where `find_symbol` does not apply.
- **Leave Codex as documented:** Serena counts every Codex grep (see Context), so Codex has the same problem.

## Consequences

- Code searches are still reminded. Config, docs, piped output and files outside the project are not.
- The filter runs inside the guard's process. It starts no extra process and adds only a parse of the line.
- In Codex, the move changes the positions Codex keys its hook approvals on. Codex asks once more in `/hooks`, and `loadout update`'s steps say so (`serena_remind_moved`).
- The rules are a copy in the hook folder, because hook scripts cannot import `loadout`.
- To be re-measured around 2026-10-29 with `loadout usage` against ADR 0039's numbers.

## In the code

- `plugins/loadout/hooks/harmless.py`, `plugins/loadout/hooks/mcp_guard.py`, `plugins/loadout/hooks/codex.json`
- `cli/loadout/codex_hooks.py` (`apply`), `cli/loadout/codex.py` (`loadout_copy`, `plugin_runs_remind`, `apply_parts`)
- `cli/loadout/apply.py`, `cli/loadout/steps.py`, `cli/loadout/update.py` (`serena_remind_moved`)
