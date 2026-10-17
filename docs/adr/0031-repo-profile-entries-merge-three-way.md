# 0031. Profile entries in repo files merge three-way against a record

- Status: Accepted
- Date: 2026-10-17
- Source: [Design: repos for chosen agents](../superpowers/specs/2026-10-16-repo-agents-and-careful-ux-design.md), Part 2
- Supersedes: the merge rule of [ADR 0007](0007-tiered-scoping-with-profiles.md) (settings and MCP servers "merged" with the profile's value winning)

## Context

`loadout profile` merged a profile into the repo's `.claude/settings.json` and `.mcp.json` with a deep merge in which the profile's value won. In a repo shared by two loadout users, a re-run reversed a value a teammate had changed, and an entry someone had removed came back. A profile update could not be told apart from a teammate's change, because loadout did not know what it had written.

## Decision

- `.loadout.json` (committed) records, per profile and file, the entries the profile wrote: `"profiles": {"web": {".claude/settings.json": {"env/MODE": "fast", "permissions/allow": ["Bash(npm test)"]}}}`. Paths are JSON-pointer style; lists record the entries loadout added; an MCP server definition is one entry; a value that looks like a secret is recorded as `sha256:<hex>`.
- A re-run compares the record, the file and the profile per entry. The file still has the recorded value: the profile's update applies. Someone changed it: the value stays; when the profile has a new value, loadout lists these entries and asks once (`Use the profile's values for these? [y/N]`; without a terminal they stay unless `--take-profile`). The offer is recorded, so the same value is not asked again. A list entry someone removed stays removed. An entry the profile dropped is removed only when the file still has loadout's value and no other profile recorded it.
- Without a record (a repo from before this change), only missing entries are added; an existing different value stays and is reported.
- `.codex/config.toml` keeps its owned-text rule (tables are only added); its entries are recorded the same way, so a removed table is not added back.
- `loadout explain <file>` reads the record and shows each entry's state.

## Alternatives considered

- Keep "the profile wins": simple, but a re-run silently undoes a teammate's change.
- Record in a local, uncommitted state file: the other user's runs would not see it, so their runs could not tell an update from a change.
- Ask about every differing entry on every run: safe, but a declined value would be asked again on every run.

## Consequences

- Two users with different agents can re-run profiles on one repo; neither run reverses the other's changes without a yes.
- `.loadout.json` changes when a profile writes new entries; it is committed with them.
- A `.loadout.json` whose layout loadout cannot reproduce gets no record (the plan says so); the repo then behaves as one without a record.

## In the code

- `cli/loadout/repo_merge.py` (`merge`, `stored`, `matches`)
- `cli/loadout/repo_config.py` (`records`, `record_text`, `plan_record`)
- `cli/loadout/profiles.py` (`apply_profile`), `cli/loadout/codex_project.py` (`config`), `cli/loadout/project.py` (`chooser`)
- `cli/loadout/explain.py`
