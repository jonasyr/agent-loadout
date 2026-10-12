# Codex as a second target

Date: 2026-10-12. Status: design approved in conversation (approach 1, scope, structure, drift option 1, errors/undo/tests), awaiting spec review.

## Why

The user works with Claude Code and OpenAI's Codex CLI on the same machine. Both should work the same way: the same
rules and preferences, the same MCP servers, skills and plugins, from the same kit and personal layer, kept current by
the same daily sync. Today loadout configures Claude Code only; `docs/explanation/architecture.md` ("Other agents
(planned)") already names Codex as the first other target.

**Success:** on a machine with `targets` = claude + codex, after bootstrap and every daily sync, Codex has the kit's
and the personal layer's rules, the loadout plugin (skills, hooks, Serena, codebase-memory), the third-party tools that
have a Codex route, the personal MCP servers and skills; anything present in only one agent is reported with the
command that fixes it.

**Non-goals (v1):** Codex settings in `config.toml` (model, effort, approvals, notifications); `loadout adopt` for a
whole existing Codex setup beyond the drift items below; project profiles for Codex (`.codex/config.toml`); global
hooks outside the plugin; Gemini CLI, Cursor; automatic copying between the agents.

## Facts this design rests on

Checked on codex-cli 0.161.0 (sources: `codex … --help`, developers.openai.com/codex, openai/codex source) and, where
marked, by a sandbox run with a temporary `HOME` and `CODEX_HOME`:

- Codex accepts a Claude Code marketplace as is: `codex plugin marketplace add <kit folder>` registered `agent-loadout`,
  `codex plugin add loadout@agent-loadout` installed the plugin into `$CODEX_HOME/plugins/cache/agent-loadout/loadout/local`,
  and `codex mcp list --json` then listed Serena and codebase-memory from the plugin's `.mcp.json` (sandbox run). It
  wrote only `[marketplaces.agent-loadout]` and `[plugins."loadout@agent-loadout"]` into `config.toml`.
- Plugin hooks get `CLAUDE_PLUGIN_ROOT`/`CLAUDE_PLUGIN_DATA`; hooks use the same JSON shape and similar events; every
  non-managed hook must be approved once in `/hooks` (and again after it changes).
- Global instructions: `~/.codex/AGENTS.md` (shadowed by `AGENTS.override.md`); no `@include`, no rules directory.
- Skills: the Agent Skills format (`SKILL.md`); user skills in `~/.agents/skills` (`~/.codex/skills` is deprecated);
  symlinks are followed.
- MCP servers: `[mcp_servers.NAME]` in `config.toml`; no `${VAR}` interpolation; secrets are forwarded by name with
  `env_vars` (stdio) or `bearer_token_env_var` / `env_http_headers` (HTTP); `codex mcp add` takes no JSON and cannot set
  `env_vars`. Codex edits `config.toml` format-preserving (comments survive).
- Commit attribution (`Co-authored-by: Codex`) is an account setting fetched from the ChatGPT backend; no config key.
- Native Codex routes exist for superpowers, Context7 and Microsoft Learn (Codex plugins), rtk (`rtk init -g --codex`),
  playwright-cli (skills into `~/.agents/skills`); Serena and codebase-memory come with the loadout plugin.

## Design

### Switching it on

- New preference `targets` in `preferences.json`: `claude` (default) or `claude,codex`. Stored in the personal layer like
  every preference, so it follows the user to every machine.
- Bootstrap: when `codex` is on PATH and `targets` is unset, it asks once ("Also set up Codex? [y/N]"); without a terminal
  it does not enable Codex. `loadout configure` can change it.
- A machine without `codex` skips the Codex step with one line; nothing else changes.

### `cli/loadout/codex.py`

All Codex-specific code; the Claude modules stay unchanged except for the calls into it.

1. **Instructions.** `render_instructions()` concatenates the kit's `rules/*.md` and the personal layer's `rules/*.md`
   (sorted, each under its file name as a heading) under a one-line header saying the block is managed and where its
   sources are. `apply_instructions(bk)` writes it between `<!-- loadout:start -->` and `<!-- loadout:end -->` in
   `~/.codex/AGENTS.md`: creates the file if missing; replaces the block if exactly one pair of markers exists; appends
   the block if none exists; leaves the file alone and reports if the markers are unbalanced or duplicated. Text
   outside the markers is never changed. If `AGENTS.override.md` exists, `check` warns that it shadows the block.
2. **Plugins.** `apply_plugins()` runs, through `runner.py`: `codex plugin marketplace add <kit root> --json` and
   `codex plugin add loadout@agent-loadout --json`, then each catalog entry with a `codex` field whose tool is wanted.
   Idempotent (Codex reports `alreadyAdded`; `codex plugin list --json` tells what is installed). After a daily pull
   that changed the kit, it refreshes the cached copy of the local plugin (`codex plugin marketplace upgrade
   agent-loadout`, else remove and add; the build verifies which works).
3. **MCP servers.** `apply_mcp(bk)` writes the personal layer's `mcp.json` servers as `[mcp_servers.NAME]` tables into
   `~/.codex/config.toml` between `# loadout:start` and `# loadout:end` comment lines. A small writer serialises only
   strings, lists of strings and tables of strings (basic strings with TOML escapes); anything else in a server config
   is reported and that server skipped. `${VAR}` references become `env_vars = ["VAR"]` (stdio) or
   `bearer_token_env_var` / `env_http_headers` (HTTP `Authorization` and other headers); a plaintext value that looks
   like a secret (`secrets.looks_secret`) is refused for that server, with the fix (move it to `secrets.env`). Before
   writing, the whole new file is parsed with `tomllib` when available (Python 3.11+); on 3.10 the marker edit runs
   without that check. A server name that already exists outside the markers is left alone and reported.
4. **Skills.** The personal layer's `skills/<name>/` and `skills.json` pointers are linked into `~/.agents/skills/<name>`
   with `link.py`'s existing link, copy-mode and backup logic.
5. **Serena context.** The build tests whether a user-level `[mcp_servers.serena]` with `--context=codex` cleanly
   replaces the plugin's `--context=claude-code` server. If yes, `apply_mcp` adds it inside the markers; if not, v1
   keeps the plugin's server and the how-to says so.

### Catalog

Optional `codex` field per entry: `{"plugin": "ID@MARKETPLACE", "marketplace": "SOURCE"}` (a Codex plugin route) or
`{"command": {"posix": [...], "windows": [...]}}` (a tool's own Codex setup, e.g. rtk) or `{"skills": true}` (skills
linked into `~/.agents/skills`). An entry without `codex` is not set up for Codex. `tests/test_repo_static.py` validates
the field.

### Drift (one source, reported both ways)

- `codex.drift()` compares, by name only: user-level MCP servers (`~/.claude.json` user scope vs `codex mcp list --json`),
  user skills (`~/.claude/skills` vs `~/.agents/skills`), and plugins that have a Codex route. Items that come from the
  kit or the personal layer on both sides are not drift.
- The daily sync queues a notice (`drift: MCP server "x" only in Claude Code — record it with loadout adopt`);
  `loadout check` shows the same as warnings.
- `loadout adopt` additionally lists Codex-only MCP servers and skills with the existing choices "record globally" or
  "leave" (and "remove"). Recording writes to the personal layer; the next sync applies it to both agents. A "leave"
  is remembered per machine in `own-decisions.json` and silences that item's drift notice.

### Callers

- `bootstrap`: a "Codex" step after "Marketplaces and plugins" when `codex` is a target: instructions, plugins, MCP,
  skills; one status line in calm mode, like the other steps.
- Daily maintenance: after new commits, re-apply instructions, MCP and skills and refresh the plugin; compute drift.
- `loadout check`: a Codex group: `codex` found, plugin installed, instruction block current, MCP block current, skills
  linked, drift, a reminder that plugin hooks need approval in `/hooks`, `AGENTS.override.md` shadowing.
- `loadout configure`: the `targets` preference.

### Errors

- `codex` missing or older than the tested version (0.161): skip with one line; Claude Code is unaffected.
- A plugin command fails: reported like Claude plugin failures (`failed: …`), retried at the next sync.
- `config.toml` that does not parse after the edit: nothing is written; the message names the file.
- Unbalanced markers in either file: nothing is written; the message says which file to fix.

### Undo

The first change to `~/.codex/AGENTS.md` and `~/.codex/config.toml` by bootstrap or adopt saves a copy in the backup;
plugin installs are recorded with their undo command (`codex plugin remove`, `codex plugin marketplace remove`).
`loadout restore` replays them. The routine re-application of the managed blocks by the daily sync is not backed up,
like the Claude settings merge.

## What loadout cannot do, and says so

- Hooks run only after the user approves them in Codex's `/hooks`; `check` reminds.
- Commit attribution is an account setting; the how-to says where to turn it off. The kit's rule against AI
  attribution reaches Codex through the instruction block, but cannot stop the account-level trailer.

## Documentation

- New how-to `docs/how-to/codex.md` ("Use loadout with Codex"): switching it on, what is mapped, `/hooks`, attribution,
  drift.
- `docs/explanation/architecture.md`: "Other agents (planned)" becomes "Codex" (what is shared, what is mapped).
- `docs/reference/cli.md` (`targets`, Codex step, check group), `docs/reference/catalog-format.md` (`codex` field),
  `docs/reference/preferences-format.md` (`targets`), `docs/explanation/security-and-trust.md` (what loadout touches in
  `~/.codex` and `~/.agents`), README "What you get" (one line), `docs/README.md` index.
- ADR 0022: "Codex as a second target: one source, drift reported".

## Testing

- Unit tests with `fake_home` and `fake_runner` (a fake `codex` answering `--json` commands); never the real `~/.codex`:
  instruction block (create, replace, append, preserve outside text, unbalanced markers, override warning); TOML writer
  (escaping, refusal of non-string values and plaintext secrets, markers, idempotence, parse check); `env_vars` and
  header mapping; plugin commands idempotent; skills links; drift both ways and the "leave" silencing; bootstrap and
  check with and without `codex` on PATH; `targets` preference.
- A maintainer-only sandbox script (`demo/`-style, never run by CI or agents on the real home) that installs the real
  plugin into a temporary `CODEX_HOME`, as done for this design.
