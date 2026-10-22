# 0030. Repo files follow the repo's agents

- Status: Accepted
- Date: 2026-10-16
- Source: [Design: repos for chosen agents](../superpowers/specs/2026-10-16-repo-agents-and-careful-ux-design.md), Parts 0 and 1
- Supersedes: the decision line of [ADR 0027](0027-repo-files-follow-the-agents.md) ("A repo gets the files of the agents that are on")
- Amends: [ADR 0012](0012-destructive-actions-dry-run-confirm-backup.md) (repo writes are previewed and backed up)

## Context

ADR 0027 made a repo's files follow the agents that are on for whoever runs loadout. In a repo shared by a user with both agents and a teammate with Codex only, the teammate's runs never kept Claude Code's files current, and a user with both agents could not keep a repo Codex-only. Repo writes had no preview and no backup: `loadout restore` did not undo them, and `--dry-run` left out the settings.

## Decision

- A committed `.loadout.json` at the repo root names the repo's agents (`"agents": ["claude", "codex"]`). `init`, `profile` and `configure new skill --to repo` write the files of those agents, whichever agents are on for the user. Without the file, the user's agents decide, and the first `init` or `profile` adds the file to its plan.
- Commands and installs follow the user: a repo agent that is off for the user gets its files, not its installs; loadout says which.
- `"manage": false` makes every loadout command refuse to write in the repo; it prints the plan instead.
- Every repo write is a plan first. In a terminal loadout asks `Apply these changes? [y/N]`; without one it writes only with `--yes`. Applying saves a copy of every changed file and records every created one in a backup that names the repo; `loadout restore` undoes it.
- A repo JSON file is rewritten only in the exact layout it has (indentation, line endings); any other file is left and its entries printed.

## Alternatives considered

- Keep 0027: the teammate case and Codex-only repos stay impossible.
- A per-machine record of repo agents: each teammate's loadout knows only their own agents.
- Grow the committed list with every run: a Codex-only repo stops being Codex-only once a both-agents user runs loadout there.

## Consequences

- Narrowing a repo's agents removes nothing; loadout lists the files no longer needed.
- A profile's `commands` change what they change, and they run after all file changes. The plan says restore cannot undo them; the same holds for the `git init` that `init` plans in a folder that is not a repo yet.
- Restore removes a folder loadout created only when it is empty; otherwise it keeps the folder and prints a `kept` line.
- A write that would go through a link that leads outside the repo is refused. Secret values are masked in the plan.
- A conflict (a file loadout cannot use, a problem while applying) ends the run with exit code 1; a declined plan, a plan without a terminal and `manage: false` end with 0.
- The rest of ADR 0027 stands (one real skill folder, links between them, nothing moved or deleted).

## In the code

- `cli/loadout/repo_config.py`, `cli/loadout/repo_writes.py`
- `cli/loadout/project.py` (`add_profile`, `init`, `approver`), `cli/loadout/profiles.py`, `cli/loadout/scaffold.py`, `cli/loadout/codex_project.py`, `cli/loadout/new_skill.py`
