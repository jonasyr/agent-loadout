# 0027. Repo files follow the agents that are on

- Status: Accepted; its decision line is superseded by [0030](0030-repo-files-follow-the-repos-agents.md) (a repo's files follow the repo's agents, chosen in `.loadout.json`). The rest stands.
- Date: 2026-10-14
- Source: [Design: repo files follow the agents](../superpowers/specs/2026-10-14-repo-follows-agents-design.md)

## Context

`loadout profile`, `loadout init` and `loadout configure new skill --to repo` always wrote Claude Code's repo files: `.claude/settings.json`, `.mcp.json`, `CLAUDE.md`, and a repo skill's real folder in `.claude/skills`, with a link in `.agents/skills` for Codex. With Codex only, a repo got files for an agent nobody there uses (raised by Codex on PR #35). Claude Code loads project skills only from `.claude/skills` ([Claude Code skills](https://code.claude.com/docs/en/skills)), but it follows a skill folder there that is a link. Codex reads `.agents/skills`.

## Decision

A repo gets the files of the agents that are on (`targets.json`), and only those.

| Agents on | A repo skill's real folder | Link |
|---|---|---|
| Both | `.claude/skills/NAME` | `.agents/skills/NAME -> ../../.claude/skills/NAME` |
| Claude Code only | `.claude/skills/NAME` | none |
| Codex only | `.agents/skills/NAME` | none |

- With Claude Code off, loadout writes no `.claude/settings.json`, `.mcp.json`, `CLAUDE.md` or `.claude/settings.local.json` line in `.gitignore`, and says which profile files it left out.
- Every run links each real skill folder into the folder of every other agent that is on. That covers a repo that started with Codex only and now has Claude Code too (`.claude/skills/NAME -> ../../.agents/skills/NAME`), and a teammate's `.claude/skills` in a Codex-only repo.
- Files already in a repo are never moved or deleted, whichever agent they belong to.

## Alternatives considered

- Write Claude Code's files anyway, as normal project files: a Codex-only user gets files for an agent they do not use, and turning Claude Code off would mean nothing in a repo.
- Always keep the real folder in `.agents/skills` and link it from `.claude/skills`: it would change every existing repo with both agents on, and Claude Code's support for linked skill folders would become a requirement even for Claude Code-only users.
- Move the real folders when the agents change: it rewrites committed files in other people's clones; a link does the same job.

## Consequences

- loadout keeps no list of repos, so turning an agent on reaches a repo on the next `loadout profile` or `loadout init` there.
- A repo can have real skill folders in both places; each agent's folder then holds what it uses, and a name in both is reported once.
- With an agent off, its repo skill folder (`.claude/skills` or `.agents/skills`) is read only to link a teammate's skills for the other agent and to leave or refuse a second skill of the same name; nothing is written there. The AGENTS.md rule that nothing reads an agent's files when it is off is about the user's agent folders (`~/.claude`, `~/.codex`), not a repo's shared files.

## In the code

- `cli/loadout/profiles.py` (`repo_skill_dirs`, `copy_skills`, `link_skills`, `repo_off_notes`, `apply_profile`)
- `cli/loadout/project.py` (`add_profile` runs `link_skills` after the commands)
- `cli/loadout/new_skill.py` (`--to repo`)
- `cli/loadout/scaffold.py` (`CLAUDE.md` and the `.gitignore` line)
