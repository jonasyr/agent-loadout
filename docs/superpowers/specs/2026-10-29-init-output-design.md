# `loadout init` and `loadout profile`: a short plan and a short result

Status: approved, 2026-10-29 (after the builder check). Source: the user's live run in `~/Documents/Code/starlink-dash` (backlog: "UX (2026-10-29 …): `loadout init` / `profile` plan and result output"). The user's words: "looks terrible and insanely cluttered".

## Why

A fresh `loadout init` with the profiles web and db printed a plan of about 30 lines, most of which wrapped:
- `.loadout.json`'s internal record, key by key, with escaped keys (`profiles.web.\.mcp\.json.mcpServers/…`);
- every key of every new file;
- reasons appended to each line;
- the dbhub skip three times.

Then it asked a second "Apply these changes?" just to link a skill. The result said "applied with problems" for a skip that was planned. Running `loadout profile web` and `profile db` right after `init` (which had already applied both) showed the plans again and asked again.

Success: a fresh init with two profiles shows a plan of about 10 lines, asks once, and ends with a status line plus a numbered to-do list in which each item appears once.

## Goals (the user's choices)

### G1. Plan: one line per file

In calm mode (no `--verbose`), each file appears once, with a few words on what it holds. There are no `+ key: value` lines for a file that is being **created**. Target shape:

```
Plan for starlink-dash (init + web, db; agents: Claude Code, Codex)
  create  AGENTS.md, CLAUDE.md, docs/README.md, docs/adr/README.md, .gitignore
  create  .mcp.json              chrome-devtools (web, off until /mcp), dbhub (db)
  create  .claude/settings.json  keeps chrome-devtools off
  create  .codex/config.toml     web
  create  .loadout.json          what loadout wrote here (commit it)
  run     playwright-cli install --skills  (restore can't undo it)
  skip    dbhub for Codex: Codex can't read ${DATABASE_URL} in args
Apply? [y/N]
```

- Init's own scaffold files (AGENTS.md, CLAUDE.md, the docs READMEs, `.gitignore`) share one `create` line.
- An MCP file names its servers (and the profile that adds each) instead of their keys.
- `.loadout.json` is one line, whatever it records.
- A `run` line keeps "restore can't undo it", shortened, and doesn't repeat the profile's description.
- A planned skip becomes one `skip` line in the plan. It isn't a `note`.
- The title stays on one line. The full project path may become the folder name when the plan names it once.
- `--verbose` shows today's full detail (every key, the full reasons).

### G2. Result: a status line and numbered to-dos

```
✓ Init        applied (web, db)
Still to do:
  1. Set DATABASE_URL in ~/.config/loadout/secrets.env (read-only user)
  2. Start `codex` here once and trust the folder
  3. Start `claude` here and run /loadout:onboard
undo: loadout restore ~/.local/state/loadout/backups/loadout-…
```

- Each to-do appears once per run. These all become items:
  - the Codex trust note;
  - the profile notes;
  - the "next" line;
  - "Claude Code / Codex is off for you, install with loadout profile here";
  - "no longer needed for this repo's agents (yours to remove)";
  - the WSL repo note;
  - the skill-link notes that ask the user to act.
- **Planned skips (user's choice: only "not possible for this agent").** These become one calm `skip` line in the plan and count as ✓ with exit 0: a part that can't be expressed for one of the repo's agents, such as dbhub for Codex (`${…}` in args) or a Claude-only part in a repo that has Codex. They aren't repeated in the result.
- **Still problems (`!`, exit 1, as today):** every other plan-time skip, for example:
  - a profile entry that is not a `name@marketplace` id, or a command that is not a list of words;
  - a `.codex/config.toml` that doesn't parse;
  - a link or `.gitignore` that points outside the repo;
  - skills not copied, links not made or left as is;
  - a `repo_config.Invalid`.
- **Runtime failures stay problems:** a failed write, a failed command, a file changed since the plan, a failed plugin install (including "not named in .codex/config.toml, its install failed").
- **Undo lines.** Codex's own `backup: …` undo line stays visible next to `undo: loadout restore …` (my call: an undo path is never hidden).
- The cryptic note ".loadout.json: the record of profile web's .codex/config.toml entries is written after the Codex plugin installs, naming only what was added" doesn't appear in calm mode.

### G3. No second question for skill links

When the profile commands add skills, loadout links them for the repo's other agent without asking again. The first yes covers it. The link is undoable, since it's backed up like every repo write. The result names it in one line (verbose) or only counts it (calm; builder's choice). The `--yes`, `--dry-run` and decline paths keep their meaning: a `--dry-run` doesn't link, and a declined plan doesn't link.

### G4. A profile that is already applied (user's choice: only when this machine is done too)

Re-running `loadout profile <name>` is also how someone installs the parts that live outside the repo:
- a teammate who cloned an already set-up repo;
- the user after switching Claude Code or Codex on (`CLAUDE_OFF`, the Codex note in `_plan_profile`, `troubleshooting.md` "run `loadout profile NAME` again").

So "already applied" needs more than unchanged repo files:

- **Repo files.** The profile is recorded in `.loadout.json`, and the plan has no file changes.
- **This machine.** Its per-user parts are in place for every agent that is on for the user and for the repo:
  - the Claude Code plugins (`--scope project`) are installed;
  - the Codex plugins are installed in the user's Codex;
  - the skills a profile command installs exist (e.g. `.claude/skills/playwright-cli` for `playwright-cli install --skills`). The builder decides how each command's result is detected, for example by the paths the profile declares (`touches`) or a per-profile marker. A command whose result can't be detected counts as done once the profile is recorded. Say so in the docs.

When both hold, it prints one line, for example `profile web: already applied here (nothing to change)`. It exits 0, with no plan and no question.

When the repo files are unchanged but this machine lacks something, the plan lists only the missing installs and commands, and asks once.

A new flag (e.g. `--refresh`; the builder names it) runs the whole profile again, with the plan and the question as today.

`--dry-run` on an already-applied profile prints the same one line.

## Non-goals

- Changing what init or a profile writes.
- Changing `loadout update`, `bootstrap` or `adopt` output.
- Changing `configure new skill --to repo` beyond what the shared renderer changes.

## Anti-goals

- **Hiding a change to an existing file.** For a file that **changes** (`change` lines), especially an entry someone else changed in a repo file (ADR 0031), today's per-key lines stay in calm mode. Only new files get the one-line form. The one exception is `.loadout.json` (my call): it is loadout's own record, so it's one line whether it's created or changed, with its keys under `--verbose`.
- **Hiding a `run` step,** or the fact that restore can't undo it.
- **Hiding a secret-looking value.** It wouldn't show anyway, but `--verbose` keeps today's masking.
- **Exit 0 when something really failed.**

## Constraints

- Standard library only. Tests use `fake_home` and `fake_runner`. Conventional Commits, no AI attribution.
- The edge cases from AGENTS.md: a Claude-only repo, a Codex-only repo, Codex turned off for the user, no terminal (`--yes` / `--dry-run`, as used by `install-with-an-agent.md` and the configure skill), and `"manage": false`.
- The docs that show plan output (`docs/reference/cli.md`, the getting-started tutorial, `docs/how-to/` pages on init and profiles) are updated to the new shape.

## Code map (approximate)

- `cli/loadout/repo_writes.py`: `RepoWrites.render` (the per-change lines, `_json_diff` for created JSON files).
- `cli/loadout/project.py`:
  - `_show` (title, notes);
  - `_after_apply` (the second plan for skill links, the Codex trust note, profile notes);
  - `_report` (status, problems vs notes);
  - `add_profile`, `init`, `_calm` (`out.VERBOSE`).
- `codex_project.config` and the plan both report the dbhub skip, which is where the duplicate comes from.
- `repo_config.plan_record` (the `.loadout.json` record lines).

## Left to the builder

- How the "what it holds" words come about for each file. They could be the MCP server names, a profile's short label, or a fixed phrase for init's files.
- The exact wording of `skip`, the already-applied line and the flag name.
- Whether the calm result mentions the skill link.
