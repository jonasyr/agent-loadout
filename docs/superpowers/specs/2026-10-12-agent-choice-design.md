# Choosing the coding agents in bootstrap

Date: 2026-10-12. Status: design approved in conversation, awaiting spec review.

## Why

Since the Codex target (ADR 0022), loadout can set up Claude Code, Codex, or both, but bootstrap still always installs
and configures Claude Code and offers Codex only when `codex` is already installed. On a fresh machine the user should
pick the agents first, and bootstrap should install and set up exactly those.

**Success:** a fresh machine with "Codex only" ends with a working Codex setup (rules, plugins, MCP servers, skills,
hooks, settings) and no Claude Code; "both" gives both; "Claude Code" behaves as today. Existing machines are unchanged.

**Non-goals:** other agents; project profiles and adopt for Codex (PR 2 of the Codex target); removing an agent that was
set up before (switching a target off stops loadout managing it, nothing is uninstalled).

## Design

### The choice

- `<personal>/targets.json` gains a `claude` key: `{"claude": true|false, "codex": true|false}`. A missing `claude` key
  means `true`, so every existing machine keeps Claude Code. At least one agent must be on; `configure` refuses to turn
  the last one off.
- `codex.enabled()` stays as it is; new `targets.claude_enabled()`. The read and write helpers move from `codex.py` into a
  small `cli/loadout/targets.py` (`claude_enabled`, `codex_enabled`, `decided`, `set_target(name, on)`), and `codex.py`
  keeps thin wrappers so PR 1's callers stay valid.
- **Bootstrap's first question** (after the WSL step, before Prerequisites, so the right tools get installed):
  `Which coding agents should loadout set up?  1) Claude Code  2) Codex  3) both  [1]`. It is asked only when
  `targets.json` has neither key (a fresh personal layer or one from before this change that never chose); the default
  is 1, or 3 when `codex` is already on PATH. A cloned personal layer that already has the keys is not asked.
- **Without a terminal:** no question; existing keys, else Claude Code (today's behaviour).
- **Flag:** `bootstrap --agents claude|codex|claude,codex` sets the choice without asking (scripts, CI); it also
  writes `targets.json`.
- `loadout configure set target claude on|off` next to the existing `codex`.

### Installing

- New catalog binary `codex`: `install`/`update` `mise use -g codex` (posix and windows), `needs: ["mise"]`,
  `version.cmd: ["codex", "--version"]`, `version.npm: "@openai/codex"`, `required: true` only while Codex is a target.
- `claude` stays required only while Claude Code is a target.
- `_wanted(entry)` learns a `target` field on binary entries (`"claude"` or `"codex"`): an entry with a target is wanted
  only when that agent is on. `claude` gets `"target": "claude"`, `codex` gets `"target": "codex"`.

### Codex only

With Claude Code off, bootstrap and the daily sync skip every Claude-specific part:

| Part | Claude Code on | Claude Code off |
|---|---|---|
| Installing Claude Code | yes | no |
| Links into `~/.claude/rules`, `~/.claude/skills`, `~/.claude/hooks/personal` | yes | no (Codex gets the rules block and `~/.agents/skills`) |
| Settings merge into `~/.claude/settings.json`, personal MCP via `claude mcp` | yes | no |
| Claude plugins and marketplaces | yes | no (Codex plugins still map from the merged settings, which are computed without writing) |
| Adopt (it reviews a Claude Code setup) | yes | no |
| Secrets file and loader, PATH, launcher | yes | yes |
| `loadout check` | Claude groups | only the agent-neutral and Codex groups |
| Daily sync | settings, MCP, links | Codex refresh only |

`check.run_checks` skips `_links`, `_settings`, `_plugins`, `_connectors`, `_own`, `_mcp_path` when Claude Code is off.
The session-start hook keeps working in Codex (it ships in the plugin's Codex hooks).

### Docs

- Getting started: the first question and the three answers; `--agents`.
- `docs/how-to/codex.md`: "Codex only" and how to add Claude Code later.
- CLI reference (`--agents`, `set target claude`), personal-layer reference (`targets.json` keys), catalog format
  (`target` on binaries), README Quick start (one sentence: bootstrap asks which agents).

## Testing

`fake_home`, `fake_runner`: the question asked only when undecided, defaults (1, or 3 with codex on PATH), non-terminal
behaviour, `--agents` parsing and refusal of an empty choice; `_wanted` with targets; a "Codex only" bootstrap run makes
no `claude` call and writes nothing under `~/.claude` except loadout's state folder; check without Claude groups;
maintenance without Claude parts; `configure set target claude off` refused while Codex is off.
