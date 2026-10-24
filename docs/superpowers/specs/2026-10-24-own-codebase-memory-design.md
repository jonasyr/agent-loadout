# Design: your own codebase-memory setups, at Serena's level

- Date: 2026-10-24
- Status: Draft
- Builds on:
  - [ADR 0028](../../adr/0028-serena-codex-hooks-in-hooks-json.md) and [ADR 0036](../../adr/0036-codex-tool-approvals-and-serena-approval.md) (Serena already set up);
  - [ADR 0035](../../adr/0035-loadout-update-brings-a-machine-current.md) (exact duplicates removed by update);
  - [ADR 0039](../../adr/0039-serena-remind-tools-load-upfront-cbm-refresh.md) (the cbm project pointer and refresh);
  - the backlog TODO of 2026-10-22.

## Why

The maintainer asked (2026-10-22): "we handle various cases of existing Serena setup … but what about codebase mem if that exists also in various variations?" For Serena, loadout recognises a setup you made yourself in almost every shape, leaves it yours, and keeps the plugin's copy from doubling it. For codebase-memory-mcp (cbm) it does so only partly.

A recon on 2026-10-24 (code read at file:line level) found that these are already handled for cbm:
- your own server in Claude Code (user scope, local or project scope, a repo `.mcp.json`) next to `plugin:loadout:codebase-memory-mcp`, which gives the `codebase-memory servers` check row; exact copies are removed by `loadout update`;
- your own `hook-augment` hooks (a warn row);
- the Codex table under the plugin's own name (the `Codex MCP <name>` row);
- the daemon conflict;
- PATH visibility;
- the installer's skills.

These are missing, and the maintainer chose to cover all of them:

- **(a) A Codex server under another name.** It is a `[mcp_servers.<any name>]` table whose command runs `codebase-memory-mcp`, and Codex then runs two cbm servers. loadout neither sees nor names it. `servers_twice` and `mcp_guard.codex_server_enabled` compare names only. Worse, `inventory` lists the table as adoptable and `drift()` says "only in Codex (record it with loadout adopt…)". Adopting it would add a *second* cbm to Claude Code.
- **(c) The installer's own files.** `codebase-memory-mcp install` (0.12.1, run by the user; loadout's own install passes `--skip-config`) writes several files that loadout does not know:
  - Claude Code hooks (`PreToolUse` on Grep/Glob/Bash with `hook-augment`, `PostToolUse` on Read, and `SessionStart`/`SubagentStart`);
  - wrapper scripts `~/.claude/hooks/codebase-memory-session.sh` and `codebase-memory-coverage.sh`;
  - probably `~/.claude/agents/codebase-memory.md`;
  - a block between `<!-- codebase-memory-mcp:start -->` and `<!-- codebase-memory-mcp:end -->` in `~/.codex/AGENTS.md`;
  - `[[hooks.SessionStart]]` and `[[hooks.SubagentStart]]` entries for Codex, plus its MCP table.

  loadout knows only the old script names (`cbm-*`, `LEGACY_SCRIPTS`). On the maintainer's machine, the AGENTS.md block and a cbm `SessionStart` `echo` hook in `~/.codex/hooks.json` are present. Their reminders run next to loadout's routing block and project pointer. That doubles tokens and can contradict loadout's routing.
- **Your own cbm hooks do not silence loadout's.** When you run cbm's session or subagent hooks yourself, `cbm_project.py` still prints its pointer. Serena's hooks have this silencing through `mcp_guard`; cbm's do not.
- **(d) Several binaries.** Several `codebase-memory-mcp` binaries on PATH may have different versions. loadout looks at the first only.
- **(e) The cache folder per agent.** `CBM_CACHE_DIR` may differ between the agents' servers. That is noticed only after the daemon trips over it, as the `codebase-memory-mcp daemon` row reading the conflict log. With two folders, the pointer can also name a project that the other server does not have.

## Goals

1. **Recognise cbm by command, not by name.** A shared rule `is_cbm(command, args)` mirrors `codex.is_serena`: the program's basename is `codebase-memory-mcp`, with or without `.exe`, also behind `npx`/`uvx`-style launchers. It is used for:
   - Codex tables;
   - Claude Code servers (`check._is_cbm_server` already does this; reuse it, keep one home);
   - adopt's catalog match: `mcp-codebase-memory` gains a `command` match, as `mcp-serena` matches `start-mcp-server`.
2. **(a) Codex, a table under another name:**
   - **`check`:** one warn row, `Codex MCP <name>: runs codebase-memory-mcp next to the loadout plugin's; Codex starts two`. The fix is to remove your table, since the plugin provides the server, or to turn the loadout plugin off in Codex.
   - **`inventory`/`drift`:** they no longer offer to record it for Claude Code.
   - **`adopt`:** it offers "use the kit's", which removes the table with a backup, as for any own tool the kit provides. It acts only after your yes.
     - **A table with settings of its own:** a table that carries `env`/`env_vars`, extra `args` beyond the server's own, or a pinned binary path is only *named*. Removing it could silently change which index the user gets ("when in doubt, not removed"). *(Builder check; my call.)*
     - **The order in `inventory.classify`:** today it sends every Codex item to "own" before any catalog match. A cbm table must be recognised before that, so the new rule takes effect. *(Builder check.)*
   - **`mcp_guard`:** with `--agent codex`, cbm is available when it is available for either reason *(builder check; my call)*:
     - the plugin's server is on: loadout's Codex plugin is installed and not switched off (`[plugins."loadout@agent-loadout"] enabled = false`), and no `[mcp_servers.codebase-memory-mcp] enabled = false` switches the name off;
     - a cbm table of the user's under any name is enabled.

     A switched-off table of the user's never hides a working plugin server.
3. **(c) The installer's files.** Each of them, when present and loadout's plugin is on for that agent, gets a check row that names the file and why it doubles loadout's. The fix is `loadout adopt`, which offers to remove it with a backup (undo with `loadout restore`). Nothing is removed without your yes (the maintainer's choice). The artefacts:
   - **Claude Code:** settings hooks that run `codebase-memory-mcp hook-augment` or one of the wrapper scripts (old `cbm-*` names and the new `codebase-memory-*.sh` names);
   - **Claude Code:** the wrapper script files, once nothing references them. Unlike the old `cbm-*` names (in `duplicates.LEGACY_SCRIPTS`, which `loadout update` removes without a question under ADR 0035), the new names do **not** join `LEGACY_SCRIPTS`. Their hooks and files are removed only through `adopt` after a yes, and `update`'s "resembles a kit item … left alone" note stays quiet for them. *(Builder check: the maintainer chose "never without a yes".)*
   - **Claude Code:** `~/.claude/agents/codebase-memory.md`;
   - **Codex:** the `<!-- codebase-memory-mcp:start/end -->` block in `~/.codex/AGENTS.md`. It is removed exactly between its markers; text outside stays byte for byte;
   - **Codex:** cbm hook entries in `~/.codex/hooks.json` and in `[hooks]` of `config.toml`, recognised by a command that runs `codebase-memory-mcp` or one of the wrapper scripts, or by an `echo` whose text names codebase-memory-mcp. The maintainer's machine has the `echo` form.
   - The installer's skills stay as they are (already handled: copied for Codex).
4. **Your own cbm hooks silence loadout's pointer.** When your settings (Claude Code), or `hooks.json` and `[hooks]` (Codex), *run* codebase-memory-mcp, or one of its wrapper scripts, as a `SessionStart` or `SubagentStart` hook, loadout's `cbm_project.py` pointer stays silent for that event. An `echo`/`printf` that only names codebase-memory-mcp does not silence it: such a hook prints a generic reminder without the project name, and loadout's pointer is more useful. That hook is handled by goal 3, which names it and offers removal. *(Builder check; my call.)* This is the same equivalence rule as `mcp_guard.users_hook_runs` and `codex_users_hook_runs`. The check row for the installer's hooks (goal 3) still names them, so you can choose loadout's instead.
5. **(d) Several binaries:** a check row `codebase-memory-mcp binaries`. It is OK with one. It warns when several on PATH report different versions, listing each path and version, and the fix names the one loadout uses first and how to remove the others. Each binary's version comes from `<path> --version`, run through `runner.run`.
6. **(e) Cache folders:** the check compares the `CBM_CACHE_DIR` each agent's cbm server actually gets *(builder check; my call)*:
   - **Claude Code:** an own server's `env.CBM_CACHE_DIR`, else the inherited environment. `check`'s own environment stands in for it; the row says so.
   - **Codex:** a cbm table's `env.CBM_CACHE_DIR` (or `env_vars` naming it), else unset. Codex starts MCP servers with a short default variable list plus the table's `env`, so an exported `CBM_CACHE_DIR` does not reach the plugin's Codex server.

   It warns only when the two resolved folders differ ("two cache folders: … and …; servers and the project pointer see different indexes"). The fix: leave `CBM_CACHE_DIR` unset everywhere (the default folder for both), or set the same value on both sides. The plugin's server files cannot be edited.

## Non-goals

- Changing how loadout installs cbm (it keeps `--skip-config`), or the plugin's own cbm server.
- Running `codebase-memory-mcp install`, `update` or `uninstall`, ever.
- Handling a user's own Serena on the Claude Code side beyond what exists (a separate backlog item).
- Removing the installer's skills.

## Anti-goals

- **Changing user files without a yes.** loadout changes a file of yours only through `adopt` after a yes, with a backup first (AGENTS.md "User files": P1). `check` only reads.
- **Agent isolation:** with an agent off, nothing of that agent's files is read or changed.
- **Removing the wrong thing:** an AGENTS.md edit outside the installer's exact markers, or a hook that only resembles cbm's, must never be removed. When unsure, `check` names it and `adopt` does not offer removal.
- **Slow `check`:** the binary comparison runs `--version` once per distinct binary, with a timeout, and only when cbm is in the kit for an agent that is on.

## Constraints

- Stdlib only in `cli/loadout/`; hook scripts stdlib only and unable to import loadout (`cbm_project.py`, `mcp_guard.py`).
- External commands only through `runner.run` with argv lists and timeouts.
- Tests use `fake_home` and `fake_runner`. The conftest guard (#63) fails any real program run.
- Every removal through `adopt` is undoable via `loadout restore` (backup step before the write).
- Docs:
  - a "codebase-memory already set up?" section next to "Serena already set up?" in `docs/how-to/codex.md`, or in `docs/how-to/your-own-tools.md`, wherever the Serena one lives;
  - rows in `docs/how-to/troubleshooting.md` for every new check row;
  - `docs/reference/setup-matrix.md` and `docs/reference/own-tools.md` if they list Serena variants;
  - an ADR if a decision is new: likely "cbm recognised by command; the installer's files offered for removal".

## Left to the builder

- **Where the shared `is_cbm` lives:** for example next to `is_serena` in `codex.py`, with `check` and `inventory` importing it.
- **Match details for the installer's hooks:** the exact patterns, verified against the strings in the 0.12.1 binary (`strings $(which codebase-memory-mcp)`, read-only) and against the maintainer's real files. Check those by keys and booleans only, never printing content.
- **Order and wording of the check rows:** within the existing tool-setup group.
- **How `adopt` presents removals:** in its existing groups and choices.
