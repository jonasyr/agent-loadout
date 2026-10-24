# 0041. Your own codebase-memory, recognised by its command

- Status: Accepted
- Date: 2026-10-24
- Source: [Design: your own codebase-memory setups, at Serena's level](../superpowers/specs/2026-10-24-own-codebase-memory-design.md)
- Amends:
  - [ADR 0028](0028-serena-codex-hooks-in-hooks-json.md): the own-tool handling it set up for Serena in Codex now covers codebase-memory too;
  - [ADR 0039](0039-serena-remind-tools-load-upfront-cbm-refresh.md): the project pointer stays quiet when your own codebase-memory hooks already run.

## Context

The maintainer asked: "we handle various cases of existing Serena setup … but what about codebase mem if that exists also in various variations?" For Serena, loadout recognises a setup you made yourself in almost every shape and keeps the plugin's copy from doubling it. For codebase-memory-mcp it did so only partly. A recon on 2026-10-24 found these gaps:

- **A Codex server under another name** that starts codebase-memory-mcp went unseen. Codex ran two servers. Worse, `adopt` offered to copy that server into Claude Code, which would have made a second one there as well.
- **The files `codebase-memory-mcp install` writes** (0.12.1) were unknown to loadout:
  - the wrapper scripts `codebase-memory-session.sh` and `codebase-memory-coverage.sh`;
  - `~/.claude/agents/codebase-memory.md`;
  - a block in `~/.codex/AGENTS.md`;
  - Codex hooks.

  Their reminders ran next to loadout's routing and project pointer. The maintainer's machine had the AGENTS.md block and a `SessionStart` `echo` hook in `~/.codex/hooks.json`.
- **Your own codebase-memory hooks** did not silence loadout's pointer.
- **Two binaries in different versions**, or **two cache folders** (one per agent), were noticed only after the daemon had tripped over them.

## Decision

- **Recognised by the command, not the name.** `codex.is_cbm` mirrors `codex.is_serena`: the program is `codebase-memory-mcp` (with or without `.exe`, behind a full path, or behind `npx`, `bunx`, `uvx` or `uv`). It drives:
  - the `Codex MCP NAME` check row;
  - `inventory`/`adopt`, which never copy such a table into Claude Code;
  - `drift`;
  - Claude Code's "second server" row;
  - the Codex hook guard: codebase-memory is available when the plugin's server is on, or when any table of yours that starts it is on.
- **The plugin provides the server, so yours is the second one.** In Codex the plugin's server comes from the plugin, and loadout cannot leave it out the way it leaves out Serena. `adopt` therefore offers "use the kit's", which removes your table with a backup. A table with settings of its own is only named: `env`, `env_vars`, extra `args`, timeouts, `cwd`, tool lists or a fixed path. Removing it could change which index you use.
- **The installer's files are named, and removed only on a yes.** `cli/loadout/cbm_installer.py` finds them for each agent that is on and has the plugin on. `check` names each one. `adopt` offers to remove it with a backup, so `loadout restore` puts it back. Some cases are only named, never removed:
  - an AGENTS.md block whose markers are unclosed or repeated;
  - a `hooks.json` whose style cannot be reproduced;
  - hooks kept inline in `config.toml`;
  - a hook that only resembles the installer's.

  The new script names do not join the legacy names that `loadout update` removes without asking ([ADR 0035](0035-loadout-update-brings-a-machine-current.md)).
- **Your own hooks silence the pointer.** A `SessionStart` or `SubagentStart` hook of yours that *runs* codebase-memory-mcp or one of the wrapper scripts keeps `cbm_project.py` quiet for that event. An `echo` that only names the program does not count: it says nothing about your project.
- **Binaries and cache folders are compared before the daemon trips.** `codebase-memory-mcp binaries` lists the versions on `PATH` when they differ. `codebase-memory cache folders` compares the `CBM_CACHE_DIR` each agent's server actually gets. Codex passes no exported variables to the plugin's server.

## Alternatives considered

- **Leave a user's setup alone and only warn:** both servers keep running, and their tools load twice in every context.
- **Remove the installer's files automatically, like the old `cbm-*` scripts:** the maintainer chose "never without a yes".
- **Match by name only:** this misses every renamed server, which was the gap.

## Consequences

- A machine set up with `codebase-memory-mcp install` sees a few `codebase-memory installer` rows until you run `loadout adopt` or choose to leave them.
- A Codex user's own codebase-memory table under another name is reported. Removing it is one yes away.
- The rules live in two places: `codex.is_cbm`, and an inlined copy in the hook guard, because hooks cannot import loadout. A test keeps the two equal.

## In the code

- `cli/loadout/codex.py` (`is_cbm`, `user_cbm`, `cbm_has_own_settings`, `servers_twice`, `drift`)
- `cli/loadout/inventory.py`, `cli/loadout/adopt.py`, `cli/loadout/cbm_installer.py`, `cli/loadout/check.py`
- `plugins/loadout/hooks/mcp_guard.py`, `plugins/loadout/hooks/cbm_project.py`
