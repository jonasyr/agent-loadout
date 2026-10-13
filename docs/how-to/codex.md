# Use loadout with Codex

Most of loadout works the same in both agents: the kit, your personal layer, the daily sync and the commands do not depend on which agent you use. This page holds what only applies to Codex: how to switch it on, the version it needs, its hook approval and the places where it stays different. What Codex receives is listed per file in the [personal layer](../reference/personal-layer.md), per setting in the [hooks](../reference/hooks.md) and [profile](../reference/profile-format.md#in-codex) references.

## Switch it on

On a new machine, bootstrap first asks which coding agents to set up: Claude Code, Codex, or both. With Codex and `--install`, it installs Codex too (through mise); without `--install` it reports Codex as missing. Scripts can pass the choice: `bootstrap.sh --install --agents codex` (or `claude`, or `claude,codex`). On a machine set up before this choice existed, bootstrap asks only when `codex` is on your PATH. A personal layer you clone that already holds a choice (`targets.json`) wins over the answer, and bootstrap says so; `--agents` wins over both ([bootstrap flags](../reference/cli.md#loadout-bootstrap)).

To switch an agent on or off later:

```bash
loadout configure set target codex on
loadout configure set target claude off
```

One agent must stay on. Switching an agent off uninstalls nothing; loadout just stops setting it up. The choice is stored in your personal layer (`targets.json`), so it follows you to every machine. loadout needs codex 0.161 or newer.

**Codex only.** Without Claude Code, bootstrap does not install Claude Code and skips everything that belongs to it: the links under `~/.claude`, the Claude settings, its plugins and `adopt`. `loadout check` and the daily sync then look at Codex only. Codex still gets the plugins the kit enables, the rules, your personal layer and the tools. Add Claude Code later with `loadout configure set target claude on`; if Claude Code is not installed yet, it tells you to run `loadout bootstrap --install`, which installs and sets it up.

The first run clones each plugin marketplace into Codex, which can take a few minutes on a slow connection; a progress line names each step (with `--verbose`, or without a terminal, one line each). Ctrl+C is safe: run the command again and it continues where it stopped. Only one loadout run sets up Codex at a time.

Then approve loadout's hooks once in Codex: start `codex` and run `/hooks`. Codex runs plugin hooks only after you approve them, and again after they change ([which hooks](../reference/hooks.md)).

## What Codex gets

The same kit and personal layer reach Codex. Where each part goes (the instruction block in `~/.codex/AGENTS.md`, `config.toml`, `~/.agents/skills`) is in [Personal layer](../reference/personal-layer.md#files); the plugins it installs are in [Included tools](../reference/included-tools.md); the type-check hook that stands in for Claude Code's LSP plugins is in [Hooks](../reference/hooks.md). Claude Code settings without a Codex equivalent (thinking mode, auto mode, the permission list) have no effect on Codex.

## What stays different

- **Hooks need your approval once** in `/hooks` (see above).
- **Commit attribution.** Codex adds `Co-authored-by: Codex` to commits when your ChatGPT account has commit attribution turned on. That is an account setting, not a config key: turn it off in your ChatGPT account settings. loadout's rule against AI attribution reaches Codex through the instruction block, but cannot remove the trailer.
- **Context7 without a login.** The plugin's Context7 address asks Codex for an OAuth login; loadout sets the plain address for Codex instead, which works without one. Anonymous use has Context7's lower rate limit, so loadout lists an optional `codex mcp login context7` until you log in.
- **Logins and approvals are named where you work.** Bootstrap's "Still to do", `loadout configure set target codex on` and `loadout check` list what is still open in Codex: the hook approval in `/hooks` (until you approved them, and again after loadout's hooks change) and any MCP server that waits for a login (`codex mcp login NAME`). loadout does not approve hooks for you: that approval is Codex's safety gate.
- **MCP tools load on demand in Codex.** Codex shows the model Serena's, codebase-memory's and the other servers' tools only when it searches for them, so a session can claim "Serena is not available" without looking. loadout's instruction block tells Codex to search first; if it still does not use them, ask for them by name ("use Serena's find_symbol").
- **Type checks run per edit** instead of a language server that keeps running. Large TypeScript projects can take a few seconds; after 20 seconds the check reports itself as skipped.

## Project trust

With Codex on, `loadout init` and `loadout profile NAME` also set up Codex in the repo ([what each profile field becomes](../reference/profile-format.md#in-codex)). Codex reads a repo's `.codex/config.toml` only in a trusted project. Until you trust it, loadout prints the step: start `codex` in the repo once and accept the trust question. loadout never trusts a project for you.

## Where to read more

- What loadout changes in `~/.codex`, and what it never touches: [Security and trust](../explanation/security-and-trust.md).
- Record a Codex-only MCP server or skill (`loadout adopt`): [Handle your own tools](your-own-tools.md#tools-only-one-agent-has).
- Undo and remove: [Undo what loadout changed](undo-and-restore.md#codex) and [Uninstall](uninstall.md#codex). Turning Codex off with `loadout configure set target codex off` removes nothing.
