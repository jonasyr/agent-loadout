# Codex as a second target

Date: 2026-10-12. Status: design approved in conversation (approach 1, scope widened to full parity, drift option 1,
two PRs), awaiting spec review.

## Why

The user works with Claude Code and OpenAI's Codex CLI on the same machine. Codex has to work exactly as well as Claude
Code with agent-loadout: the same rules and preferences, the same tools (plugins, MCP servers, skills, hooks), the
same per-project setup, installed and configured automatically, kept current by the same daily sync. Today loadout
configures Claude Code only; `docs/explanation/architecture.md` ("Other agents (planned)") already names Codex.

**Success:** with Codex enabled, after bootstrap and every daily sync, a Codex session in any repo has everything a
Claude Code session has (table below), or the documented Codex-only replacement; anything present in only one agent is
reported with the command that fixes it; nothing needs a manual step except Codex's own one-time hook approval.

**Non-goals:** Gemini CLI, Cursor and other agents; copying changes made directly in one agent to the other
automatically (drift is reported instead, see below); changing anything for Claude Code users who do not enable Codex.

## Facts this design rests on

Checked on codex-cli 0.161.0 and 0.162.1 (sources: `codex … --help`, developers.openai.com/codex, the openai/codex
source) and, where marked "sandbox", by runs with a temporary `HOME` and `CODEX_HOME`:

- **Claude marketplaces work in Codex.** `codex plugin marketplace add <kit folder>` and `codex plugin add
  loadout@agent-loadout` installed the kit plugin, and Codex then listed Serena and codebase-memory from its `.mcp.json`
  (sandbox). `codex plugin marketplace add anthropics/claude-plugins-official` made every kit plugin available under its
  usual id (superpowers, context7, microsoft-docs, frontend-design, commit-commands, security-guidance,
  claude-md-management, the LSP plugins); installing them gave Context7 and Microsoft Learn as MCP servers (sandbox).
- **Commands become skills.** Codex migrates a plugin's `commands/` into skills (`source-command-…`) and rewrites
  Claude-specific terms (openai/codex `core-plugins/src/command_migration.rs`).
- **No LSP in Codex.** Plugins that declare `lspServers` install, but Codex does not start language servers (no LSP code
  in openai/codex).
- **Plugin hooks.** A plugin's `.codex-plugin/plugin.json` may set `hooks` to its own file, which replaces the default
  `hooks/hooks.json` discovery for Codex; Claude Code does not read `.codex-plugin/`. Codex sets `PLUGIN_ROOT` and also
  `CLAUDE_PLUGIN_ROOT`. Hooks use the same JSON shape; Codex matches its shell tool as `Bash` and `apply_patch` as
  `Edit|Write`. Every non-managed hook must be approved once in `/hooks` (and again after it changes).
  `rtk hook codex` and `serena-hooks … --client=codex` exist.
- **Instructions.** Global `~/.codex/AGENTS.md` (shadowed by `AGENTS.override.md`); no `@include`, no rules directory.
- **Skills.** Agent Skills format (`SKILL.md`); user skills in `~/.agents/skills`, repo skills in `.agents/skills`;
  symlinks are followed.
- **MCP servers.** `[mcp_servers.NAME]` in `config.toml`; no `${VAR}` interpolation; secrets are forwarded by name with
  `env_vars` (stdio) or `bearer_token_env_var` / `env_http_headers` (HTTP). A user-level `serena` replaces the plugin's
  server of the same name (sandbox). Codex's own writes to `config.toml` drop and move comment lines, so marker comments
  cannot delimit a managed region (sandbox).
- **Plugin refresh.** `codex plugin marketplace upgrade` works only for git marketplaces; `codex plugin add` again
  refreshes the cached copy of a local plugin (sandbox).
- **Settings.** `model_reasoning_effort` (low/medium/high), `tui.notifications`; project `.codex/config.toml` loads only
  in trusted projects.
- **Commit attribution** (`Co-authored-by: Codex`) is an account setting fetched from the ChatGPT backend; no config key.

## Parity

| Kit part | Claude Code | Codex |
|---|---|---|
| Rules, `me.md` | `~/.claude/rules/` links | Managed block in `~/.codex/AGENTS.md` |
| loadout plugin (skills, Serena, codebase-memory) | kit marketplace | The same marketplace and plugin; Serena with `--context=codex` |
| loadout plugin hooks | `hooks/hooks.json` | `hooks/codex.json` via `.codex-plugin/plugin.json`: `rtk hook codex`, `serena-hooks --client=codex`, the session-start notice, the advisor and reload hooks, the type-check hook |
| superpowers, context7, microsoft-docs, frontend-design, security-guidance, claude-md-management, commit-commands | `claude-plugins-official` | The same marketplace and ids |
| impeccable | its marketplace | Its Codex route (verified during the build) |
| LSP plugins | type errors after each edit | Codex-only `PostToolUse` hook running pyright, `tsc --noEmit` or `cargo check` for the changed file; Serena's `get_diagnostics_for_file` on request |
| playwright-cli skills | `~/.claude/skills` | `~/.agents/skills` |
| Settings from preferences | `settings.json` | `model_reasoning_effort` (effort_level), `tui.notifications` (agent_push_notifications); preferences without a Codex equivalent are listed in the how-to |
| Personal MCP servers, skills | `claude mcp add-json`, `~/.claude/skills` | Owned `[mcp_servers.*]` tables, `~/.agents/skills` |
| Project profiles | `.claude/settings.json`, `.mcp.json` | `.codex/config.toml`, `.agents/skills` (PR 2) |
| adopt, drift | existing | Codex-only items in adopt (PR 2); drift reported both ways (PR 1) |
| What stays different | | One-time `/hooks` approval; commit attribution is an account setting; the type check runs per edit instead of a resident language server |

## Design

### Switching it on

- `<personal>/targets.json`: `{"codex": true}`. A file of its own rather than an entry in `preferences.json`, because
  every preference must write a `me.md` line or a setting, and the quick first-run screen would set it without asking.
  It lives in the personal layer, so it follows the user to every machine.
- `loadout configure set target codex on|off`; `loadout configure show` lists it.
- Bootstrap: when `codex` is on PATH and `targets.json` has no `codex` key, it asks once ("Codex found. Set it up with
  loadout too? [y/N]") and records the answer; without a terminal it records nothing and does not enable Codex.
- Without `codex` on PATH the Codex step is skipped with one line.

### `cli/loadout/codex.py` (PR 1)

All Codex-specific code; the Claude modules change only where they call into it.

1. **Instructions.** `render_instructions()` concatenates the kit's `rules/*.md` and the personal layer's `rules/*.md`
   (sorted) under a header naming the sources. `apply_instructions(bk)` writes it between `<!-- loadout:start -->` and
   `<!-- loadout:end -->` in `~/.codex/AGENTS.md`: creates the file if missing; replaces the block if exactly one pair
   exists; appends it if none exists; leaves the file alone and reports if the markers are unbalanced or duplicated.
   Text outside the markers is never changed. The first change to an existing file saves a copy in the backup.
2. **Plugins.** `apply_plugins(bk, refresh=False)` runs through `runner.py`: `codex plugin marketplace add <kit root>`
   and `anthropics/claude-plugins-official` (and the marketplace of each further plugin with a Codex route), then
   `codex plugin add ID@MARKETPLACE` for the loadout plugin and every kit plugin that is enabled in the merged Claude
   settings and has a `codex` field in the catalog. Idempotent: `codex plugin list --json` tells what is installed.
   Newly added items are recorded with their undo (`codex plugin remove`, `codex plugin marketplace remove`). With
   `refresh=True` (after a pull that changed the kit) it runs `codex plugin add loadout@agent-loadout` again.
3. **Config keys and MCP servers.** `apply_config(bk)` edits `~/.codex/config.toml`:
   - **Owned tables.** Each personal MCP server, and `serena` with `--context=codex`, is written as one self-contained
     `[mcp_servers.NAME]` table (nested values as inline tables). Ownership is tracked in
     `~/.claude/.loadout/codex-config.json`, which records the exact text loadout wrote for each table and key. loadout
     replaces or removes only what still matches that record; a table or key the user changed, or a same-named one
     loadout never wrote, is left alone and reported.
   - **Owned keys.** `model_reasoning_effort` and `tui.notifications` from the preferences, written into their table
     (top level, or `[tui]`, created when missing), owned the same way.
   - **Values.** A small writer serialises only strings, booleans, lists of strings and tables of strings (TOML basic
     strings with escapes); anything else in a server config is reported and that server skipped. `${VAR}` becomes
     `env_vars = ["VAR"]` when the variable has the env key's name, `bearer_token_env_var` for an HTTP `Authorization:
     Bearer ${VAR}` header, `env_http_headers` for other headers; a reference under a different name is reported (the
     fix: rename it in `secrets.env`). A plaintext value that looks like a secret (`secrets.looks_secret`) is refused
     for that server, with the fix (move it to `secrets.env`).
   - **Safety.** The new file is parsed with `tomllib` before it replaces the old one when Python is 3.11+; on 3.10 the
     edit runs without that check. The first change to an existing file saves a copy in the backup.
4. **Skills.** The personal layer's `skills/<name>/` and `skills.json` pointers, and playwright-cli's skills, are linked
   into `~/.agents/skills/<name>` with `link.py`'s existing link, copy-mode and backup logic.
5. **Drift report.** `drift()` compares by name: user-scope MCP servers (`~/.claude.json` vs `codex mcp list --json`)
   and user skills (`~/.claude/skills` vs `~/.agents/skills`), ignoring what the kit, the personal layer or a remembered
   "leave" accounts for. It returns lines such as `MCP server "x" only in Claude Code (record it: loadout adopt)`.

### Plugin side (PR 1)

- `plugins/loadout/.codex-plugin/plugin.json` with `"hooks": "./hooks/codex.json"`.
- `plugins/loadout/hooks/codex.json`: the Claude hooks with Codex arguments (`rtk hook codex`, `serena-hooks …
  --client=codex`, the Serena tool matcher in Codex's naming), without the `Grep|Glob` codebase-memory hook (Codex has
  no such tools), plus the type-check hook.
- `plugins/loadout/hooks/typecheck.py`: on `PostToolUse` for `Edit|Write`, finds the changed files in the hook input,
  runs `pyright <file>` for Python, `tsc --noEmit -p <nearest tsconfig>` for TypeScript, `cargo check` for Rust, each
  with a time limit (20 s), and returns the errors to the agent in the hook's feedback format; prints nothing when the
  checker is missing or the file is clean; reports "type check skipped (timeout)" when it runs out of time. Standard
  library only, like the other hooks.

### Catalog (changed while planning)

No catalog field: Codex reads Claude Code marketplaces, so every plugin enabled in the merged Claude settings maps
through its marketplace's GitHub source (`claude-plugins-official` → `anthropics/claude-plugins-official`). A plugin
whose marketplace is not on GitHub is reported by `check` as "no Codex route". playwright-cli installs no skills for
Claude Code, so there is nothing to map.

### Rulings from planning and building

- The `/hooks` reminder is a line in bootstrap's "Still to do" while Codex is enabled, not a failing check: loadout
  cannot see whether the hooks were approved.
- `reload_check.py` is not in the Codex hooks: it compares Claude's `installed_plugins.json`; Codex loads plugins per
  session.
- `config.toml` is edited only with `tomllib` (Python 3.11+): the edit proves that the parsed file minus loadout's own
  entries is unchanged before it writes; on Python 3.10 loadout reports that it needs 3.11 instead of editing.

### Callers (PR 1)

- `bootstrap`: a "Codex" step after "Marketplaces and plugins" when Codex is enabled; one status line in calm mode.
- Daily maintenance: after new commits, `apply_instructions`, `apply_config`, skill links and
  `apply_plugins(refresh=True)`; the drift report is queued as a notice.
- `loadout check`: a Codex group (codex found and version, plugin installed, instruction block current, owned config
  current, skills linked, catalog entries without a Codex route, drift, a reminder about `/hooks`,
  `AGENTS.override.md` shadowing).
- `loadout configure`: `set target codex on|off`, `show`.
- `loadout restore`: replays recorded `codex plugin …` undo commands; the command allowlist (today `claude` only) gets
  exactly `codex` added.

### Projects and adopt (PR 2)

- `loadout init` / `loadout profile`: for a profile's MCP servers, also owned tables in the repo's
  `.codex/config.toml`; for its skills, also `.agents/skills`; the profile's plugins also through `codex plugin add`
  where a Codex route exists. A note says the project must be trusted in Codex for project config to load.
- `loadout adopt`: Codex-only MCP servers and skills appear with the choices "record globally", "leave", "remove".
  Recording writes the personal layer; the next sync applies it to both agents. "leave" is remembered per machine and
  silences that item's drift line. "remove" saves `config.toml` (or moves the skill) into the backup first.

### Errors

- `codex` missing or older than 0.161: skip with one line; Claude Code is unaffected.
- A plugin or marketplace command fails: reported like Claude plugin failures (`failed: …`), retried at the next sync.
- `config.toml` that would not parse after the edit: nothing is written; the message names the file.
- Unbalanced markers in `AGENTS.md`: nothing is written; the message says which file to fix.

### Undo

The first change to `~/.codex/AGENTS.md` and `~/.codex/config.toml` by bootstrap or adopt saves a copy in the backup;
plugin and marketplace installs are recorded with their undo command. `loadout restore` replays them. The routine
re-application by the daily sync is not backed up, like the Claude settings merge.

## What loadout cannot do, and says so

- Codex runs plugin hooks only after the user approves them once in `/hooks`; `check` reminds.
- Commit attribution is an account setting; the how-to says where to turn it off. The kit's rule against AI
  attribution reaches Codex through the instruction block, but cannot stop the account-level trailer.
- Type errors come from a per-edit check, not a resident language server.

## Documentation

- New how-to `docs/how-to/codex.md` ("Use loadout with Codex"): switching it on, the parity table, `/hooks`,
  attribution, drift, preferences without a Codex equivalent.
- `docs/explanation/architecture.md`: "Other agents (planned)" becomes "Codex".
- `docs/reference/cli.md`, `catalog-format.md` (`codex` field), `personal-layer.md` (`targets.json`,
  `codex-config.json`), `hooks.md` (Codex hooks, type check), `docs/explanation/security-and-trust.md` (what loadout
  touches in `~/.codex` and `~/.agents`), README ("What you get", one line), `docs/README.md` index.
- ADR 0022: "Codex as a second target: one source, drift reported, Codex-only replacements".

## Testing

- Unit tests with `fake_home` and `fake_runner` (a fake `codex` answering `--json` commands); never the real `~/.codex`:
  the instruction block (create, replace, append, outside text kept, unbalanced markers); the TOML writer (escaping,
  refusal of unsupported values and plaintext secrets, `env_vars` and header mapping, owned tables and keys,
  user-changed items left alone, idempotence, parse check); plugin commands and their undo records; skill links; the
  type-check hook (finds files in `apply_patch` input, clean file silent, errors reported, timeout, missing checker);
  the Codex hooks file (every Claude hook has a Codex counterpart or a stated reason); drift both ways; `targets.json`
  and `configure set target`; bootstrap and check with and without `codex`; restore of a `codex` undo; PR 2's project
  and adopt paths.
- A maintainer-only sandbox script, never run by CI or agents on the real home, that installs the real plugins into a
  temporary `CODEX_HOME` and lists what Codex sees.
