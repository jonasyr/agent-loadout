# Use loadout with Codex

Use this page when you also work with OpenAI's Codex CLI and want it set up exactly like Claude Code: the same rules and preferences, plugins, MCP servers, skills and hooks, from the same kit and personal layer, kept current by the same daily sync.

## Switch it on

Bootstrap asks once when it finds `codex` on your PATH. To switch it on or off later:

```bash
loadout configure set target codex on
```

The choice is stored in your personal layer (`targets.json`), so it follows you to every machine. loadout needs codex 0.161 or newer.

The first run clones each plugin marketplace into Codex, which can take a few minutes on a slow connection; it prints every step. Ctrl+C is safe: run the command again and it continues where it stopped. Only one loadout run sets up Codex at a time.

Then approve loadout's hooks once in Codex: start `codex` and run `/hooks`. Codex runs plugin hooks only after you approve them, and again after they change.

## What Codex gets

| Kit part | In Codex |
|---|---|
| The kit's rules and your `me.md` | A block between `<!-- loadout:start -->` and `<!-- loadout:end -->` in `~/.codex/AGENTS.md`; your own text in that file stays as it is |
| The loadout plugin: skills, Serena, codebase-memory | The same plugin from the same marketplace; Serena runs in its Codex mode |
| The plugins you have enabled for Claude Code | The same plugins from the same marketplaces (Codex reads Claude Code marketplaces) |
| Type errors after each edit (Claude Code's LSP plugins) | A Codex-only hook runs pyright, `tsc --noEmit` or `cargo check` on the changed files and reports the errors; Serena's diagnostics tool works on request |
| Your personal MCP servers | Sections in `~/.codex/config.toml`; secrets only as variable names (`env_vars`) |
| Your personal skills | Links in `~/.agents/skills` |
| Effort and notifications | `model_reasoning_effort` and `tui.notifications` |

Preferences that live in `me.md` (answer language, commit style and so on) reach Codex through the instruction block. Claude Code settings without a Codex equivalent (thinking mode, auto mode, the permission list) have no effect on Codex.

## What stays different

- **Hooks need your approval once** in `/hooks` (see above).
- **Commit attribution.** Codex adds `Co-authored-by: Codex` to commits when your ChatGPT account has commit attribution turned on. That is an account setting, not a config key: turn it off in your ChatGPT account settings. loadout's rule against AI attribution reaches Codex through the instruction block, but cannot remove the trailer.
- **Context7 without a login.** The plugin's Context7 address asks Codex for an OAuth login; loadout sets the plain address for Codex instead, which works without one. Anonymous use has Context7's lower rate limit, so loadout lists an optional `codex mcp login context7` until you log in.
- **Logins and approvals are named where you work.** Bootstrap's "Still to do", `loadout configure set target codex on` and `loadout check` list what is still open in Codex: the hook approval in `/hooks` (until you approved them, and again after loadout's hooks change) and any MCP server that waits for a login (`codex mcp login NAME`). loadout does not approve hooks for you: that approval is Codex's safety gate.
- **MCP tools load on demand in Codex.** Codex shows the model Serena's, codebase-memory's and the other servers' tools only when it searches for them, so a session can claim "Serena is not available" without looking. loadout's instruction block tells Codex to search first; if it still does not use them, ask for them by name ("use Serena's find_symbol").
- **Type checks run per edit** instead of a language server that keeps running. Large TypeScript projects can take a few seconds; after 20 seconds the check reports itself as skipped.

## Keep both the same

Everything that comes from the kit and your personal layer reaches both agents. Something you add directly in one agent lives only there: the daily sync and `loadout check` report it, for example `MCP server "x" only in Claude Code`.

- **Only in Claude Code:** run `loadout adopt` and record it globally; the next sync puts it into both.
- **Only in Codex:** add it to your personal layer (`mcp.json` or `skills/`); the next sync puts it into both.

## What loadout changes in `~/.codex`

- `~/.codex/AGENTS.md`: only its own marked block.
- `~/.codex/config.toml`: only the `[mcp_servers.*]` sections and keys it wrote itself. It records what it wrote in `~/.claude/.loadout/codex-config.json` and never changes a section or key you edited or wrote yourself.
- Plugins and marketplaces through `codex plugin` commands.

The first change to an existing `AGENTS.md` or `config.toml` saves a copy in the backup; `loadout restore` brings it back and removes the plugins loadout installed. Turn it off with `loadout configure set target codex off`; what was set up stays until you remove it.
