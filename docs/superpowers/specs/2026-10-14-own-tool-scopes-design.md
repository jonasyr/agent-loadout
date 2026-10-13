# Own-tool scopes (hardening 4c): design

Status: approved in chat 2026-10-14. Implements the backlog section "Own tools / scopes".

## Goal

A tool of your own can live in three places: your personal layer (every machine), a personal profile (repos you apply it to), or committed in one repo (everyone who clones it). Both agents get the same three places, there is a direct way to create a new skill in each, and the docs explain the difference in one table.

## Decisions (from the user)

- New skills get a command: `loadout configure new skill NAME`, used by the `loadout:configure` skill too.
- Tools only Codex has get `project:<profile>` in adopt, for skills and MCP servers.

## 1. `loadout configure new skill NAME [--to WHERE] [--description TEXT]`

`WHERE` uses adopt's words plus `repo`: `global` (default), `project:<profile>`, `repo`.

| `--to` | Writes | Then |
|---|---|---|
| `global` | `<personal>/skills/NAME/SKILL.md` | Links it now for each agent that is on: `~/.claude/skills/NAME` (Claude Code, via `link.link_all`) and `~/.agents/skills/NAME` (Codex, via `codex.apply_skills`). In a terminal, offers the commit/push of the personal layer (`configure.offer_commit`). |
| `project:<p>` | `<personal>/profiles/skills/NAME/SKILL.md`; adds `NAME` to `skills` in `<personal>/profiles/<p>.json` (a kit profile of that name is copied first, with adopt's note) | Reaches a repo through `loadout profile <p>`. Same commit offer. |
| `repo` | `<repo>/.claude/skills/NAME/SKILL.md` in the git repo of the current folder | Links `<repo>/.agents/skills/NAME` → `../../.claude/skills/NAME` when Codex is on (same rule as `init` and `profile`). Nothing is committed; that is your step. |

`SKILL.md` stub:

```markdown
---
name: NAME
description: TEXT (default: "TODO: say when an agent should use this skill.")
---

# NAME

TODO: the instructions.
```

Rules:

- `NAME` matches `^[a-z0-9][a-z0-9-]{0,63}$`; anything else is refused (exit 2) before anything is written.
- Refuse (exit 1), writing nothing, when the target folder exists, or when any link destination for an agent that is on already holds something (folder, file, link, dangling link), naming it. Never overwrite.
- `repo` outside a git repo is refused. The repo root is found by walking up to the first `.git` (folder or file). A `.claude/skills` or `.agents/skills` that is a symlink leading outside the repo is refused (same `_inside` rule as `init`).
- `--description` goes through the secret guard (`secrets` patterns); a match is refused. A multi-line description is refused.
- Every created folder, file and link is recorded in one backup (`record_created`), the profile JSON edit through the existing `_edit_json` backup path, so `loadout restore` undoes the command. The CLI prints the backup folder like the other commands.
- With an agent off, nothing of that agent's is read or written.
- Output: one line per write, e.g. `skill notes: created <personal>/skills/notes/SKILL.md; linked for Claude Code and Codex`, then "Fill in SKILL.md, then restart the agents" (restart line as adopt words it for the agents that are on).

The `loadout:configure` skill: when you ask your agent to make a skill of your own, it asks where it should live (the three scopes), runs this command, then fills in `SKILL.md`. It does not write into the skills folders itself.

## 2. Adopt: `project:<profile>` for tools only Codex has

`own.options(item)` for a Codex item becomes:

- skill that is a folder (not a link) in `~/.agents/skills`: `global`, `project`, `leave`, `remove`
- skill that is a link: `global`, `leave`, `remove` (as today)
- MCP server in `~/.codex/config.toml`: `global`, `project`, `leave`, `remove`

`record_project` for a Codex item:

- Skill: copied into `<personal>/profiles/skills/NAME/` with the existing guards (secret scan of every file, private files, `.git`), `NAME` added to the profile's `skills`. Machine step: the folder moves out of `~/.agents/skills` into the backup.
- MCP server: converted with `codex.to_claude` (same refusals as `global`: keys Claude Code cannot express, a secret that would have to move under another name). `env` and `headers` secrets go to `secrets.env` as `${VAR}`. The server goes into the profile's `mcp.mcpServers`. Machine step: `config.toml` is saved in the backup, then `codex mcp remove NAME` through `runner.run`.

`loadout profile <p>` already brings both into a repo for Codex (`.agents/skills` links, `.codex/config.toml` sections).

## 3. Docs

- `docs/how-to/your-own-tools.md`: new section "Where a tool of yours can live" with one table: rows global / personal profile / committed in one repo; columns where the files are, which machines get it, who else gets it, how Claude Code gets it, how Codex gets it, how to undo. A short "Create a skill" section for the new command. The "Only in Codex" list gains `project`.
- `docs/reference/cli.md`: the new command, its flags and exit codes.
- `docs/reference/personal-layer.md`: only if a row there names how skills get into the layer.
- The `loadout:configure` skill text (`plugins/loadout/skills/configure/`).

## Testing

All with `fake_home` and `fake_runner`, never the real home or real `claude`/`codex`:

- `new skill` for each `--to`, with both agents on, Claude Code only, Codex only (links only for agents that are on).
- Refusals: bad name, existing target, existing link destination (including a dangling link), `repo` outside git, repo skills folder linking outside, secret in `--description`. Nothing written in each case.
- `loadout restore` of the backup removes everything the command created and the profile edit.
- Adopt: a Codex-only skill folder and a Codex-only server to `project:<p>`; a server with a `tools` section refused; `codex mcp remove` called with an argument list after the backup copy; options for a Codex skill link stay without `project`.

## Review focus

- A name that differs only in case from an existing skill on a case-insensitive file system (macOS, Windows): treat an existing entry found case-insensitively as taken.
- The current folder is inside a repo's subfolder or a worktree (`.git` is a file): `repo` finds the right root.
- The profile JSON is damaged or has `skills` that is not a list: refuse with the reason, do not rewrite it.
- Codex-only server whose name is already in the profile's `mcp`: refuse, do not merge.
- Running `new skill` twice: the second run is refused and changes nothing.
