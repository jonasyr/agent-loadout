# Repo files follow the agents that are on (hardening 4d): design

Status: approved in chat 2026-10-14. Implements the backlog section "4d: repo skill folder follows the agents that are on". Raised by Codex on PR #35 (thread 4265049172).

## Goal

A repo gets the files of the agents that are on (`targets.json`), and only those. With Codex only, `loadout profile`, `loadout init` and `loadout configure new skill --to repo` write nothing under `.claude`, no `.mcp.json` and no `CLAUDE.md`. With both agents on, every result stays byte for byte what it is today.

## Decisions (from the user)

- Scope is all Claude Code repo files, not only skills: with Claude Code off, no `.claude/…`, no `.mcp.json`.
- Separate PR from #35.

## Facts this rests on

- Claude Code loads project skills only from `.claude/skills/<name>/SKILL.md`; its docs (code.claude.com/docs/en/skills) do not mention `.agents/skills`. They do allow a skill entry to be a symlink to a folder elsewhere ("Claude Code reads SKILL.md from the target"). One older report (2.0.73) says `/skills` did not list symlinked skills; the live tour checks this on the current version.
- Codex reads a repo's `.agents/skills`.
- loadout keeps no list of repos, so "turning an agent on later" takes effect on the next `loadout profile` or `loadout init` in that repo, as Codex's links do today.

## Rules

1. Files already in a repo are never moved or deleted, whichever agent they belong to.
2. A rerun after turning an agent on adds that agent's files (the merges and the scaffold only add what is missing).
3. Reading a repo's `.claude/skills` with Claude Code off is allowed only to link a skill that already exists there (a teammate's) for Codex; nothing is written there.

## 1. Where a repo skill's real folder goes

New helper in `profiles.py`:

```python
def repo_skill_dirs(project: Path) -> tuple[Path, Path | None]:
    """(where a new skill's real folder goes, the other agent's folder that gets a link, or None)."""
```

| Agents on | Real folder | Link |
|---|---|---|
| Both | `.claude/skills/NAME` (as today) | `.agents/skills/NAME -> ../../.claude/skills/NAME` |
| Claude Code only | `.claude/skills/NAME` | none |
| Codex only | `.agents/skills/NAME` | none |

## 2. `loadout profile` / `init`: copying and linking

- `profiles.copy_skills` copies into the real folder from the helper. A skill whose name already exists in either `.claude/skills` or `.agents/skills` (as a folder or a link) is left as is, with today's "exists, left as is" line naming the path found.
- The link-outside guard applies to the folder it writes (today it is always `.claude/skills`; with Codex only it is `.agents/skills`, and its message names `.agents`).
- `codex_project.skills` becomes `profiles.link_skills(project, dry_run)`, called from `project.add_profile` for every agent setting (today it runs only inside `codex_project.apply`):
  - Codex on: every real folder in `.claude/skills` gets `.agents/skills/NAME -> ../../.claude/skills/NAME` (today's behaviour, today's lines).
  - Claude Code on: every real folder in `.agents/skills` gets `.claude/skills/NAME -> ../../.agents/skills/NAME`, line `linked skill NAME for Claude Code -> .claude/skills/NAME`.
  - Links are made only from a real folder, never from a link (no link chains), only for an agent that is on, and only when the name is missing in the target folder. A different item already there stays and is reported (today's wording, with the agent's name).
  - The existing guards cover both directions: a target folder (or its parent) that points outside the repo gets one "not linked" line; `os.symlink` failing (Windows without the right) gets one line per skill.
- `codex_project.apply` no longer links; its `has_codex_parts` (the trust note) still counts `.agents/skills`.
- The calm summary and the problem classification in `add_profile` keep today's words; the new Claude Code link line is a good line, "left as is" and "not linked" stay problems.

## 3. `loadout configure new skill NAME --to repo`

`new_skill._repo` uses the helper: it writes `SKILL.md` into the real folder and, only with both agents on, the link into `.agents/skills` (as today). The "name taken" check looks in both folders whatever is on, so it never creates a second skill of the same name. The link and not-a-folder guards apply to each folder it writes. The output line says where it went (`created .agents/skills/NAME/SKILL.md (commit it …)`).

## 4. Claude Code files with Claude Code off

- `profiles.apply_profile` skips `.claude/settings.json` and `.mcp.json`. `add_profile` prints one info line per skipped file, not a problem: `Claude Code is off: .mcp.json not written (turn it on and run loadout profile NAME again)`. Calm mode shows it under the status line as a step, not as a warning; the exit code is unchanged.
- `loadout init` (`scaffold.scaffold`) skips the `CLAUDE.md` template, and `scaffold.ensure_gitignore` skips the `.claude/settings.local.json` line (`.serena/cache/` stays). No extra line: init's output already names what it created.
- The `project.py` install step already installs Claude Code plugins only with Claude Code on; unchanged.

## 5. Not in scope

- `loadout check` has no per-repo checks; the guards above and the profile/init lines report repo problems where they happen.
- Moving an existing repo's real skill folders between `.claude/skills` and `.agents/skills`.
- A list of repos loadout has touched.

## 6. Docs

- ADR 0027 "Repo files follow the agents that are on": the table in §1, rules 1–3, why the real folder for Codex only is `.agents/skills` (Claude Code reads only `.claude/skills` but follows a link), why existing files are never moved. It supersedes the sentence in `profile-format.md` "With Codex only, the Claude Code parts of a profile … are still written".
- `docs/reference/profile-format.md` (skills section and "In Codex"), `docs/reference/cli.md` (`--to repo`, the profile table row), `docs/how-to/write-a-profile.md`, `docs/how-to/uninstall.md` (links in `.claude/skills` that point to `../../.agents/skills/NAME`), `docs/how-to/undo-and-restore.md`, `docs/adr/README.md`, AGENTS.md (ADR range 0001-0027).

## 7. Tests (`fake_home`, `fake_runner`; `targets.set_agents` per case)

- `repo_skill_dirs` for the three settings.
- `copy_skills`: Codex only copies into `.agents/skills` and creates no `.claude`; a name present in the other folder is left as is.
- `link_skills`: both on links `.claude → .agents` exactly as today; Codex only with a teammate's real `.claude/skills/x` links it for Codex and writes nothing under `.claude`; Codex only → both on, then `profile` again links `.claude/skills/NAME -> ../../.agents/skills/NAME`; a link is never linked again; a different item in the target stays and is reported; a target folder that points outside the repo gets one line.
- `new skill --to repo`: Codex only writes `.agents/skills/NAME/SKILL.md` and no `.claude`; a name in `.claude/skills` is refused with Codex only; both on unchanged.
- `apply_profile` / `add_profile`: Codex only writes no `.claude/settings.json` or `.mcp.json`, prints the info line, exits 0; Claude Code on afterwards writes them.
- `init`: Codex only creates no `CLAUDE.md` and no `.claude/settings.local.json` line; both on unchanged.
- Existing tests for both agents on pass unchanged.
