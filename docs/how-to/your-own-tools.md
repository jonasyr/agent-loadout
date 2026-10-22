# Handle your own tools

Use this page when `loadout adopt` or `loadout check` lists tools that loadout does not manage, and you want them to follow you to other machines, live in one project, stay put, or go away.

`loadout adopt` looks at every user-scope plugin, marketplace, MCP server (`~/.claude.json`, `~/.claude/.mcp.json`), skill (`~/.claude/skills`) and hook (`~/.claude/settings.json`) of Claude Code. With Codex on, it also lists the MCP servers in `~/.codex/config.toml` and the skills in `~/.agents/skills` that only Codex has ([details](../reference/own-tools.md#tools-only-one-agent-has)). With Claude Code turned off, bootstrap skips its adopt step. What the [catalog](../reference/catalog-format.md) does not know is listed under **Your own tools: loadout doesn't know these** (`--verbose`: **YOUR OWN TOOLS**). Items already in your personal layer show as keep, and so does a plugin that a personal profile holds while it is disabled globally. Project-level config is not inspected.

`loadout configure own` lists the same items. Flags and exit codes of the commands are in the [CLI reference](../reference/cli.md#loadout-adopt).

## You installed a tool yourself

You found a skill, MCP server or plugin and installed it with its own installer (`npx ...`, `claude mcp add`, `codex mcp add`, `/plugin install`). loadout never records or moves it on its own; it waits for your answer.

1. **Where it landed decides who sees it.** Claude Code reads skills from `~/.claude/skills` (every project) and a repo's `.claude/skills` (that repo). Codex reads `~/.agents/skills` and a repo's `.agents/skills`. An installer writes to one of these; an MCP server goes to one agent's config. So right after the install, only that agent has it, and only on this machine.
2. **loadout notices it** when you run `loadout check` or `loadout adopt`: it is listed under your own tools, and with both agents on as `skill "x" only in Claude Code` (or `only in Codex`).
3. **Decide where it lives** with `loadout adopt` (or `loadout configure set own x CHOICE`): `global` for every machine and both agents, `project:<profile>` for some repos, `leave` to keep it here only, `remove` to take it away. The table in [Where a tool of yours can live](../reference/own-tools.md#where-a-tool-of-yours-can-live) shows what each one means; [Choices](../reference/own-tools.md#choices) has the prompts and rules. As a rule: `global` for a tool you want in every project (most skills and general MCP servers); `project:<profile>` for a tool that fits only some repos (a language server, a database server); `leave` while you are still trying it out.
4. **Installed into one repo** (`.claude/skills` in that repo): adopt does not look there. Commit it to share it with the repo; `loadout profile <profile>` (or `loadout init` when it applies a profile) links it into `.agents/skills` so Codex sees it too, and links a repo's `.agents/skills` into `.claude/skills` for Claude Code, for the agents the repo is for ([`.loadout.json`](../reference/cli.md#loadoutjson)).

To write a new skill yourself instead, see [Create a skill of your own](#create-a-skill-of-your-own).

## Create a skill of your own

```bash
loadout configure new skill notes --description "Use when taking meeting notes."
loadout configure new skill db-tips --to project:db
loadout configure new skill release --to repo
```

The command writes a `SKILL.md` stub (name, description, a short body to fill in) and links it for the agents that are on. It refuses, writing nothing, when the name is taken in a place it would write or link (also in another case, as a dangling link, or for `global` as a pointer in `skills.json`), and when the description is empty, has a line break or looks like a secret. The description is stored as a quoted string, so `Use when: ...` is fine. `--to repo` works in a git repo, but not when that repo is your home folder (a dotfiles repo); commit the new folder yourself. It first shows a plan and asks `Apply these changes? [y/N]`; without a terminal it writes only with `--yes`. It writes the repo's `.claude/skills` and, when the repo is for both agents, links `.agents/skills` to it; for a Codex-only repo it writes `.agents/skills` and nothing under `.claude` (the repo's agents are in [`.loadout.json`](../reference/cli.md#loadoutjson); the same rule as [profiles](../reference/profile-format.md#skills), [ADR 0030](../adr/0030-repo-files-follow-the-repos-agents.md)). Every folder and link it creates is in a backup, so `loadout restore` removes it. For `global` and `project:<profile>` it ends with the commit offer, like adopt.

## Be asked again about a left item

Choose another answer with `loadout configure set own NAME CHOICE` (recommended: it records the change with a backup). The fallback is to delete its entry (or the whole file) in `~/.local/state/loadout/own-decisions.json` by hand; then you are asked again at the next `loadout adopt`. `loadout configure own --all` lists the left items too.

## Without a terminal

```bash
loadout adopt --apply --own "foo@bar=global,my-db=project:mydb,notes=leave"
loadout configure set own foo@bar global
```

Items not named stay as they are. `--groups own` is refused; use `--own`. Use names as `loadout configure own` prints them; how hooks are named (`PreToolUse:Bash`, `Stop:`, `#n`, `<kind>:`) is in [Hooks](../reference/hooks.md#naming-hooks-of-your-own-tools).

Exit codes: [`loadout adopt`](../reference/cli.md#loadout-adopt) and [`loadout configure`](../reference/cli.md#loadout-configure) in the CLI reference.

## Sync to other machines

`global` and `project` choices reach another machine only when your personal layer is a git repo and you commit and push. The other machine pulls it daily (see [Sync](../reference/personal-layer.md#sync)).

- Interactive adopt offers this at the end, when you chose anything other than `leave`. It shows the changes and asks `commit and push your personal layer? [y/N]`. It refuses, without asking, when a private file would be committed.
- After `--own` or `configure set own` nothing is committed. Run it yourself:

```bash
cd ~/.config/loadout/personal      # or $LOADOUT_PERSONAL
git status --short
git add -A && git commit -m "chore: record own tools" && git push
```

`leave` decisions stay on the machine where you made them.

On the second machine, the [daily sync](../reference/state-and-sync.md#the-daily-sync) links the pulled skills (for Codex into `~/.agents/skills`) and hook scripts, merges the hooks, and Claude Code installs the plugins at its next start. Hooks you recorded as global are a Claude Code feature; Codex does not receive them.

## Options and rules

Where a tool can live, what each choice changes, tools only one agent has, the secret guard, hooks and the known limits are in [Your own tools: options and rules](../reference/own-tools.md).
